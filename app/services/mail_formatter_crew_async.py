"""
Async mail formatter crew with event callbacks for WebSocket streaming.
"""

import asyncio
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from crewai import Agent, Crew, LLM, Process, Task
from crewai.hooks import (
    register_before_llm_call_hook,
    register_after_llm_call_hook,
    LLMCallHookContext,
)
from crewai.project import CrewBase, agent, crew, task

import time

from app.core.logging_config import get_logger
from app.core.metrics import (
    agent_events_total,
    agent_progress as agent_progress_metric,
    job_duration_seconds,
    jobs_completed_total,
    jobs_in_progress,
    llm_request_duration_seconds,
    llm_request_errors_total,
    llm_requests_total,
    llm_tokens_total,
)
from app.models.enums import AgentEventStatusEnum, AgentNameEnum, AgentRoleEnum, JobStatusEnum
from app.models.schemas import AgentEvent, EmailResponse
from app.services.redis_service import RedisService

logger = get_logger(__name__)


def _load_yaml(name: str) -> dict:
    path = Path(__file__).resolve().parent.parent / "config" / f"{name}.yaml"
    logger.debug(f"Loading YAML config: {path}")
    try:
        with open(path) as f:
            config = yaml.safe_load(f)
        logger.debug(f"Successfully loaded {name}.yaml")
        return config
    except Exception as e:
        logger.error(f"Failed to load {name}.yaml: {e}")
        raise


def _get_llm():
    """Build LLM from .env environment variables."""
    logger.info("Initializing LLM configuration from environment variables")
    
    # Required parameters
    model = os.getenv("MODEL_NAME", "gpt-4")
    api_key = os.getenv("API_KEY", "")
    base_url = os.getenv("BASE_URL")
    
    # Optional parameters with defaults
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    timeout = int(os.getenv("LLM_TIMEOUT", "60"))
    
    # Ensure BASE_URL ends with /v1 for OpenAI-compatible APIs if not empty
    if base_url and not base_url.endswith("/v1") and not base_url.endswith("/v1/"):
        # Remove trailing slash if present, then add /v1
        base_url = base_url.rstrip("/") + "/v1"
        logger.warning(f"BASE_URL adjusted to include /v1: {base_url}")
    
    logger.info(f"LLM Model: {model}")
    logger.info(f"LLM Base URL: {base_url or 'default (OpenAI)'}")
    logger.info(f"LLM API Key: {'*' * 10 if api_key else 'NOT SET'}")
    logger.info(f"LLM Temperature: {temperature}")
    logger.info(f"LLM Max Tokens: {max_tokens}")
    logger.info(f"LLM Timeout: {timeout}s")
    
    if not api_key:
        logger.warning("API_KEY is not set! LLM calls will fail.")
    
    if not base_url:
        logger.warning("BASE_URL is not set! Using default OpenAI endpoint.")
    
    llm_instance = LLM(
        model=model,
        api_key=api_key,
        base_url=base_url or None,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    
    # Store model name on LLM instance for metrics tracking
    llm_instance._model_name = model
    
    return llm_instance


class AsyncMailFormatterCrew:
    """Crew with event callbacks for WebSocket streaming."""

    def __init__(
        self, 
        job_id: str, 
        redis_service: RedisService,
        tone: str = "professional",
        translation: str = "none",
        audience: str = "general",
        language: str = "en",
    ):
        self.job_id = job_id
        self.redis_service = redis_service
        self.tone = tone
        self.translation = translation
        self.audience = audience
        self.language = language
        logger.info(f"Initializing AsyncMailFormatterCrew for job: {job_id} (tone={tone}, translation={translation}, audience={audience}, language={language})")
        self._llm = _get_llm()
        self.agent_progress = {
            AgentNameEnum.EMAIL_PLANNER.value: 0,
            AgentNameEnum.TONE_SPECIALIST.value: 0,
            AgentNameEnum.GRAMMAR_SPECIALIST.value: 0,
            AgentNameEnum.DICTATION_SPECIALIST.value: 0,
            AgentNameEnum.RESPONSE_FORMATTER.value: 0,
        }
        # Track which agents have actually started processing (not just initialized)
        self.agents_started = set()
        logger.debug(f"Agent progress mapping configured for job {job_id}")
        
        # Store timing for LLM calls (key: (agent_name, model), value: start_time)
        self._llm_call_times = {}
        
        # Register LLM hooks for this crew instance to track usage, duration, and errors
        self._register_llm_hooks()

    def _emit_event(
        self,
        agent_name: AgentNameEnum | str,
        agent_role: AgentRoleEnum | str,
        status: AgentEventStatusEnum | str,
        message: str,
        output: str | None = None,
        thinking: str | None = None,
    ):
        """Emit an event to Redis."""
        # Convert string to enum if needed
        if isinstance(agent_name, str):
            try:
                agent_name = AgentNameEnum(agent_name)
            except ValueError:
                logger.warning(f"Unknown agent name: {agent_name}, using SYSTEM")
                agent_name = AgentNameEnum.SYSTEM
        
        if isinstance(agent_role, str):
            try:
                agent_role = AgentRoleEnum(agent_role)
            except ValueError:
                logger.warning(f"Unknown agent role: {agent_role}, using SYSTEM")
                agent_role = AgentRoleEnum.SYSTEM
        
        # Convert status string to enum if needed
        if isinstance(status, str):
            try:
                status = AgentEventStatusEnum(status)
            except ValueError:
                logger.warning(f"Unknown status: {status}, using PROCESSING")
                status = AgentEventStatusEnum.PROCESSING
        
        # Calculate progress based on agent status
        agent_name_str = agent_name.value if isinstance(agent_name, AgentNameEnum) else str(agent_name)
        
        # Update progress based on agent status
        if status == AgentEventStatusEnum.STARTED:
            # Agent started - set to 0% (will be updated when processing/completed)
            self.agent_progress[agent_name_str] = 0
        elif status == AgentEventStatusEnum.PROCESSING:
            # Agent processing - set to 50%
            self.agent_progress[agent_name_str] = 50
        elif status == AgentEventStatusEnum.COMPLETED:
            # Agent completed - set to 100%
            self.agent_progress[agent_name_str] = 100
        
        # Calculate overall progress (average of all agents)
        total_agents = 5  # email_planner, tone_specialist, grammar_specialist, dictation_specialist, response_formatter
        total_progress = sum(self.agent_progress.values())
        overall_progress = (total_progress / total_agents)
        
        event = AgentEvent(
            job_id=self.job_id,
            agent_name=agent_name,
            agent_role=agent_role,
            status=status,
            progress=overall_progress,  # Always use overall progress for UI
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
            output=output,
            thinking=thinking,
        )
        
        # Get string values for logging
        status_str = status.value if isinstance(status, AgentEventStatusEnum) else str(status)
        
        logger.debug(f"Job {self.job_id}: Emitting event - {agent_name_str} - {status_str} (progress: {overall_progress:.1f}%)")
        
        # Update metrics
        agent_events_total.labels(agent_name=agent_name_str, status=status_str).inc()
        agent_progress_metric.labels(agent_name=agent_name_str, job_id=self.job_id).set(overall_progress)
        
        self.redis_service.add_event(event)
        self.redis_service.publish_event(event)

    def _create_step_callback(self, agent_name: str, agent_role: str):
        """Create a step callback for an agent."""
        def callback(step_output):
            # Map agent_name string to enum
            agent_name_enum = AgentNameEnum(agent_name) if isinstance(agent_name, str) else agent_name
            
            # Extract thinking/reasoning from step_output if available
            # CrewAI exposes reasoning in various ways depending on version and configuration
            # When reasoning=True, the reasoning plan is typically embedded in the execution output
            # Based on CrewAI AgentFinish objects, reasoning is often in the 'thought' attribute
            thinking = None
            
            if step_output is not None:
                if hasattr(step_output, 'output'):
                    thought_value = getattr(step_output, 'output')
                    if thought_value and str(thought_value).strip() and str(thought_value).strip().lower() != 'none':
                        thinking = str(thought_value)
                        logger.debug(f"Job {self.job_id}: Found reasoning in step_output.thought: {thinking[:100]}...")
            
            if thinking:
                logger.debug(f"Job {self.job_id}: Extracted thinking for {agent_role}: {thinking[:100]}...")
            else:
                logger.debug(f"Job {self.job_id}: No thinking found in step_output for {agent_role}")
            
            # Emit processing event - the check for agents_started is done in tracked_step_callback
            # This ensures the event is emitted when the step callback is actually called
            self._emit_event(
                agent_name=agent_name_enum,
                agent_role=agent_role,
                status=AgentEventStatusEnum.PROCESSING,
                message=f"{agent_role} is working on the task...",
                thinking=thinking,
            )
        return callback

    def _create_task_callback(self, agent_name: str, agent_role: str):
        """Create a task callback for an agent."""
        def callback(task_output):
            output_text = task_output.raw if hasattr(task_output, "raw") else str(task_output)
            self._emit_event(
                agent_name=agent_name,
                agent_role=agent_role,
                status=AgentEventStatusEnum.COMPLETED,
                message=f"{agent_role} completed their task.",
                output=output_text[:500] if output_text else None,  # Limit output length
            )
        return callback

    def _register_llm_hooks(self):
        """Register LLM hooks to track requests, duration, tokens, and errors."""
        job_id = self.job_id
        call_times = self._llm_call_times
        
        def before_llm_hook(context: LLMCallHookContext) -> None:
            """Track LLM call start time before each LLM call."""
            try:
                if not hasattr(context, 'agent') or not context.agent:
                    return
                
                agent_role = getattr(context.agent, 'role', 'unknown')
                agent_name_map = {
                    'Email Strategy Planner': AgentNameEnum.EMAIL_PLANNER.value,
                    'Tone and Style Specialist': AgentNameEnum.TONE_SPECIALIST.value,
                    'Grammar and Syntax Expert': AgentNameEnum.GRAMMAR_SPECIALIST.value,
                    'Spelling and Word Choice Specialist': AgentNameEnum.DICTATION_SPECIALIST.value,
                    'Response Formatter and Analysis Specialist': AgentNameEnum.RESPONSE_FORMATTER.value,
                }
                agent_name_str = agent_name_map.get(agent_role, agent_role.lower().replace(' ', '_'))
                
                model_name = getattr(context.llm, "_model_name", None) or getattr(context.llm, "model", "unknown")
                
                # Store start time for duration calculation
                call_key = (agent_name_str, model_name)
                call_times[call_key] = time.time()
                logger.debug(f"Job {job_id}: Before LLM hook - {agent_name_str} - model: {model_name}")
                
            except Exception as e:
                logger.warning(f"Error in before LLM hook: {e}", exc_info=True)
        
        def after_llm_hook(context: LLMCallHookContext) -> None:
            """Track LLM usage, duration, and errors after each LLM call."""
            try:
                # Get agent name from context
                if not hasattr(context, 'agent') or not context.agent:
                    return
                
                agent_role = getattr(context.agent, 'role', 'unknown')
                # Map agent role to agent name enum
                agent_name_map = {
                    'Email Strategy Planner': AgentNameEnum.EMAIL_PLANNER.value,
                    'Tone and Style Specialist': AgentNameEnum.TONE_SPECIALIST.value,
                    'Grammar and Syntax Expert': AgentNameEnum.GRAMMAR_SPECIALIST.value,
                    'Spelling and Word Choice Specialist': AgentNameEnum.DICTATION_SPECIALIST.value,
                    'Response Formatter and Analysis Specialist': AgentNameEnum.RESPONSE_FORMATTER.value,
                }
                agent_name_str = agent_name_map.get(agent_role, agent_role.lower().replace(' ', '_'))
                
                # Get model name from LLM instance
                model_name = getattr(context.llm, "_model_name", None)
                if not model_name:
                    # Try to get from LLM instance attributes
                    model_name = getattr(context.llm, "model", "unknown")
                    if hasattr(context.llm, "model_name"):
                        model_name = context.llm.model_name
                
                call_key = (agent_name_str, model_name)
                start_time = call_times.pop(call_key, None)
                duration = time.time() - start_time if start_time else 0
                
                # Track LLM request
                llm_requests_total.labels(model=model_name, agent_name=agent_name_str).inc()
                logger.debug(f"Job {job_id}: LLM request tracked - {agent_name_str} - model: {model_name}")
                
                # Track request duration
                if duration > 0:
                    llm_request_duration_seconds.labels(model=model_name, agent_name=agent_name_str).observe(duration)
                    logger.debug(f"Job {job_id}: LLM duration tracked - {agent_name_str} - duration: {duration:.2f}s")
                else:
                    logger.warning(f"Job {job_id}: LLM duration is 0 or missing start time for {agent_name_str}")
                
                # Try to extract token usage from LLM instance
                # Different LLM backends store this differently
                prompt_tokens = 0
                completion_tokens = 0
                
                # Check various possible locations for usage information
                usage_info = None
                if hasattr(context.llm, "last_usage"):
                    usage_info = context.llm.last_usage
                elif hasattr(context.llm, "_last_usage"):
                    usage_info = context.llm._last_usage
                elif hasattr(context.llm, "usage_metadata"):
                    usage_info = context.llm.usage_metadata
                elif hasattr(context.llm, "_usage_metadata"):
                    usage_info = context.llm._usage_metadata
                
                if usage_info:
                    # Try different attribute names for token counts
                    prompt_tokens = (
                        getattr(usage_info, "prompt_tokens", None) or
                        getattr(usage_info, "input_tokens", None) or
                        getattr(usage_info, "total_input_tokens", None) or
                        getattr(usage_info, "promptTokens", None) or
                        0
                    )
                    completion_tokens = (
                        getattr(usage_info, "completion_tokens", None) or
                        getattr(usage_info, "output_tokens", None) or
                        getattr(usage_info, "total_output_tokens", None) or
                        getattr(usage_info, "completionTokens", None) or
                        0
                    )
                
                # If still no tokens, estimate from content (rough approximation: 1 token ≈ 4 characters)
                if prompt_tokens == 0 and context.messages:
                    total_chars = sum(len(str(msg.get("content", ""))) for msg in context.messages)
                    prompt_tokens = max(1, total_chars // 4)  # Rough estimate
                    logger.debug(f"Job {job_id}: Estimated prompt tokens from content: {prompt_tokens}")
                
                if completion_tokens == 0 and context.response:
                    response_chars = len(str(context.response))
                    completion_tokens = max(1, response_chars // 4)  # Rough estimate
                    logger.debug(f"Job {job_id}: Estimated completion tokens from response: {completion_tokens}")
                
                # Track tokens
                if prompt_tokens > 0:
                    llm_tokens_total.labels(model=model_name, agent_name=agent_name_str, type="prompt").inc(prompt_tokens)
                if completion_tokens > 0:
                    llm_tokens_total.labels(model=model_name, agent_name=agent_name_str, type="completion").inc(completion_tokens)
                if prompt_tokens > 0 or completion_tokens > 0:
                    total_tokens = prompt_tokens + completion_tokens
                    llm_tokens_total.labels(model=model_name, agent_name=agent_name_str, type="total").inc(total_tokens)
                
                logger.debug(f"Job {job_id}: LLM call tracked - {agent_name_str} - model: {model_name} - duration: {duration:.2f}s - tokens: {prompt_tokens}+{completion_tokens}={prompt_tokens+completion_tokens}")
                
            except Exception as e:
                # Track error
                try:
                    agent_role = getattr(context.agent, 'role', 'unknown') if hasattr(context, 'agent') and context.agent else 'unknown'
                    agent_name_map = {
                        'Email Strategy Planner': AgentNameEnum.EMAIL_PLANNER.value,
                        'Tone and Style Specialist': AgentNameEnum.TONE_SPECIALIST.value,
                        'Grammar and Syntax Expert': AgentNameEnum.GRAMMAR_SPECIALIST.value,
                        'Spelling and Word Choice Specialist': AgentNameEnum.DICTATION_SPECIALIST.value,
                        'Response Formatter and Analysis Specialist': AgentNameEnum.RESPONSE_FORMATTER.value,
                    }
                    agent_name_str = agent_name_map.get(agent_role, agent_role.lower().replace(' ', '_'))
                    model_name = getattr(context.llm, "_model_name", None) or getattr(context.llm, "model", "unknown") if hasattr(context, 'llm') else "unknown"
                    error_type = type(e).__name__
                    llm_request_errors_total.labels(model=model_name, agent_name=agent_name_str, error_type=error_type).inc()
                except:
                    pass
                logger.warning(f"Error tracking LLM usage in hook: {e}", exc_info=True)
        
        # Register both hooks
        register_before_llm_call_hook(before_llm_hook)
        register_after_llm_call_hook(after_llm_hook)
        logger.debug(f"Job {self.job_id}: LLM hooks registered (before and after)")
    
    def _track_llm_usage(self, agent_name: str, duration: float, prompt_tokens: int = 0, completion_tokens: int = 0, error: str = None):
        """Track LLM usage metrics (legacy method, kept for backward compatibility)."""
        model_name = getattr(self._llm, "_model_name", "unknown")
        
        if error:
            llm_request_errors_total.labels(model=model_name, agent_name=agent_name, error_type=error).inc()
        else:
            llm_requests_total.labels(model=model_name, agent_name=agent_name).inc()
            if duration > 0:
                llm_request_duration_seconds.labels(model=model_name, agent_name=agent_name).observe(duration)
            
            if prompt_tokens > 0:
                llm_tokens_total.labels(model=model_name, agent_name=agent_name, type="prompt").inc(prompt_tokens)
            if completion_tokens > 0:
                llm_tokens_total.labels(model=model_name, agent_name=agent_name, type="completion").inc(completion_tokens)
            if prompt_tokens > 0 or completion_tokens > 0:
                total_tokens = prompt_tokens + completion_tokens
                llm_tokens_total.labels(model=model_name, agent_name=agent_name, type="total").inc(total_tokens)
    
    def _create_agent(self, agent_key: str, agent_name: str) -> Agent:
        """Create an agent with callbacks."""
        config = _load_yaml("agents")[agent_key]
        role = config.get("role", agent_name)
        
        # Map agent_name to enum for tracking
        try:
            agent_name_enum = AgentNameEnum(agent_name) if isinstance(agent_name, str) else agent_name
            agent_name_str = agent_name_enum.value if isinstance(agent_name_enum, AgentNameEnum) else str(agent_name_enum)
        except ValueError:
            agent_name_str = str(agent_name)
        
        # Create step callback that tracks LLM usage and emits events
        original_step_callback = self._create_step_callback(agent_name, role)
        
        def tracked_step_callback(step_output):
            # Log step_output structure for debugging
            logger.debug(f"Job {self.job_id}: Step callback received for {role}, step_output type: {type(step_output)}")
            if step_output is not None:
                if hasattr(step_output, '__dict__'):
                    logger.debug(f"Job {self.job_id}: step_output attributes: {list(step_output.__dict__.keys())}")
                elif isinstance(step_output, dict):
                    logger.debug(f"Job {self.job_id}: step_output keys: {list(step_output.keys())}")
            
            # Only emit processing event on the first step for this agent
            # This ensures agents show as "processing" only when they actually start working
            if agent_name_str not in self.agents_started:
                self.agents_started.add(agent_name_str)
                original_step_callback(step_output)
            
            # Note: LLM token tracking is now handled by LLM hooks registered in _register_llm_hook()
            # This is more reliable than trying to extract from step_output
        
        # Add language instruction to agent config for reasoning
        if isinstance(config, dict):
            thinking_language = "Persian (فارسی)" if self.language == "fa" else "English"
            if "backstory" in config:
                config["backstory"] = config["backstory"] + f"\n\nIMPORTANT: When providing reasoning or thinking, write it in {thinking_language}."
            elif "goal" in config:
                config["goal"] = config["goal"] + f"\n\nIMPORTANT: When providing reasoning or thinking, write it in {thinking_language}."
        
        return Agent(
            config=config,
            llm=self._llm,
            verbose=True,
            allow_delegation=False,
            step_callback=tracked_step_callback,
        )

    def _create_task(self, task_key: str, agent: Agent, context_tasks: list[Task] = None) -> Task:
        """Create a task with callback."""
        config = _load_yaml("tasks")[task_key].copy()  # Make a copy to avoid modifying original
        agent_role = agent.role if hasattr(agent, "role") else "Agent"
        
        # Map task_key to agent name enum
        agent_name_map = {
            "plan_email_improvement": AgentNameEnum.EMAIL_PLANNER,
            "improve_tone": AgentNameEnum.TONE_SPECIALIST,
            "fix_grammar": AgentNameEnum.GRAMMAR_SPECIALIST,
            "fix_dictation": AgentNameEnum.DICTATION_SPECIALIST,
        }
        agent_name_enum = agent_name_map.get(task_key, AgentNameEnum.SYSTEM)
        
        # Note: Translation instructions and other inputs are passed via crew.kickoff(inputs={...})
        # CrewAI will automatically replace template variables like {translation_instruction} in tasks.yaml
        # We only handle non-template replacements here (like adding preferences)
        
        # Inject user preferences into task description (these are appended, not template variables)
        if isinstance(config.get("description"), str):
            description = config["description"]
            
            # Append user preferences to description
            preferences = []
            if self.tone != "professional":
                preferences.append(f"Desired tone: {self.tone}")
            if self.translation != "none":
                preferences.append(f"Translation: {self.translation}")
            if self.audience != "general":
                preferences.append(f"Target audience: {self.audience}")
            
            # Add language instruction for thinking/reasoning
            thinking_language = "Persian (فارسی)" if self.language == "fa" else "English"
            description += f"\n\nIMPORTANT: When providing your reasoning or thinking process, write it in {thinking_language}. Your reasoning should match the user's language preference."
            
            if preferences:
                description += f"\n\nUser Preferences:\n" + "\n".join(f"- {p}" for p in preferences)
            
            config["description"] = description
        
        # Don't emit started event here - agents should show as "pending" until they actually start
        # The step callback will emit "processing" when the agent actually begins working
        
        task = Task(
            config=config,
            agent=agent,
            context=context_tasks or [],
        )
        
        # Create callback for this task
        def task_callback(task_output):
            output_text = task_output.raw if hasattr(task_output, "raw") else str(task_output)
            
            # Extract thinking/reasoning from task_output using comprehensive method
            thinking = None
            if task_output is not None:
                logger.debug(f"Job {self.job_id}: Task callback received for {agent_role}, task_output type: {type(task_output)}")
                if hasattr(task_output, '__dict__'):
                    logger.debug(f"Job {self.job_id}: task_output attributes: {list(task_output.__dict__.keys())}")
                elif isinstance(task_output, dict):
                    logger.debug(f"Job {self.job_id}: task_output keys: {list(task_output.keys())}")
                
                # Method 1: Check for 'thought' attribute first (CrewAI AgentFinish objects)
                if hasattr(task_output, 'thought'):
                    thought_value = getattr(task_output, 'thought')
                    if thought_value and str(thought_value).strip() and str(thought_value).strip().lower() != 'none':
                        thinking = str(thought_value)
                        logger.debug(f"Job {self.job_id}: Found reasoning in task_output.thought")
                
                # Method 2: Try multiple ways to extract reasoning/thinking
                if not thinking:
                    for attr in ['reasoning', 'thinking', 'reasoning_text', 'thoughts', 'plan', 'reasoning_plan']:
                        if hasattr(task_output, attr):
                            value = getattr(task_output, attr)
                            if value and str(value).strip():
                                thinking = str(value)
                                logger.debug(f"Job {self.job_id}: Found reasoning in task_output.{attr}")
                                break
                
                # Method 3: Dictionary access
                if not thinking and isinstance(task_output, dict):
                    # Check 'thought' first (CrewAI AgentFinish)
                    if 'thought' in task_output and task_output['thought']:
                        thought_value = task_output['thought']
                        if str(thought_value).strip().lower() != 'none':
                            thinking = str(thought_value)
                            logger.debug(f"Job {self.job_id}: Found reasoning in task_output['thought']")
                    
                    # Then check other keys
                    if not thinking:
                        for key in ['reasoning', 'thinking', 'reasoning_text', 'thoughts', 'plan', 'reasoning_plan']:
                            if key in task_output and task_output[key]:
                                thinking = str(task_output[key])
                                logger.debug(f"Job {self.job_id}: Found reasoning in task_output['{key}']")
                                break
                
                # Check raw output for reasoning markers
                if not thinking and output_text:
                    reasoning_markers = ['reasoning:', 'thinking:', 'plan:', 'analysis:']
                    for marker in reasoning_markers:
                        if marker.lower() in output_text.lower():
                            parts = output_text.split(marker, 1)
                            if len(parts) > 1:
                                thinking = parts[1].strip()
                                logger.debug(f"Job {self.job_id}: Extracted reasoning from task_output raw using marker '{marker}'")
                                break
            
            if thinking:
                logger.debug(f"Job {self.job_id}: Extracted thinking for {agent_role}: {thinking[:100]}...")
            else:
                logger.debug(f"Job {self.job_id}: No thinking found in task_output for {agent_role}")
            
            self._emit_event(
                agent_name=agent_name_enum,
                agent_role=agent_role,
                status=AgentEventStatusEnum.COMPLETED,
                message=f"{agent_role} completed their task.",
                output=output_text[:500] if output_text else None,
                thinking=thinking,
            )
        
        task.callback = task_callback
        return task

    def run(self, email: str) -> EmailResponse:
        """Run the crew workflow with event streaming."""
        logger.info(f"Job {self.job_id}: Starting crew workflow")
        logger.debug(f"Job {self.job_id}: Email length: {len(email)} characters")
        
        # Import here to avoid circular dependency
        from app.models.schemas import EmailResponse
        
        # Create agents
        logger.debug(f"Job {self.job_id}: Creating agents")
        email_planner = self._create_agent("email_planner", "email_planner")
        tone_specialist = self._create_agent("tone_specialist", "tone_specialist")
        grammar_specialist = self._create_agent("grammar_specialist", "grammar_specialist")
        dictation_specialist = self._create_agent("dictation_specialist", "dictation_specialist")
        response_formatter = self._create_agent("response_formatter", "response_formatter")
        logger.info(f"Job {self.job_id}: All agents created")

        # Create tasks
        plan_task = self._create_task("plan_email_improvement", email_planner)
        tone_task = self._create_task("improve_tone", tone_specialist, [plan_task])
        grammar_task = self._create_task("fix_grammar", grammar_specialist, [plan_task, tone_task])
        dictation_task = self._create_task("fix_dictation", dictation_specialist, [plan_task, tone_task, grammar_task])
        
        # Format response task with output_pydantic
        # Note: Translation instructions are passed via crew.kickoff(inputs={...})
        format_task_config = _load_yaml("tasks")["format_response"].copy()
        
        format_task = Task(
            config=format_task_config,
            agent=response_formatter,
            context=[plan_task, tone_task, grammar_task, dictation_task],
            output_pydantic=EmailResponse,
        )
        
        def format_callback(task_output):
            output_text = task_output.raw if hasattr(task_output, "raw") else str(task_output)
            
            # Extract thinking/reasoning from task_output using comprehensive method
            thinking = None
            if task_output is not None:
                # Method 1: Check for 'thought' attribute first (CrewAI AgentFinish objects)
                if hasattr(task_output, 'thought'):
                    thought_value = getattr(task_output, 'thought')
                    if thought_value and str(thought_value).strip() and str(thought_value).strip().lower() != 'none':
                        thinking = str(thought_value)
                        logger.debug(f"Job {self.job_id}: Found reasoning in format_task_output.thought")
                
                # Method 2: Try multiple ways to extract reasoning/thinking
                if not thinking:
                    for attr in ['reasoning', 'thinking', 'reasoning_text', 'thoughts', 'plan', 'reasoning_plan']:
                        if hasattr(task_output, attr):
                            value = getattr(task_output, attr)
                            if value and str(value).strip():
                                thinking = str(value)
                                logger.debug(f"Job {self.job_id}: Found reasoning in format_task_output.{attr}")
                                break
                
                # Method 3: Dictionary access
                if not thinking and isinstance(task_output, dict):
                    # Check 'thought' first (CrewAI AgentFinish)
                    if 'thought' in task_output and task_output['thought']:
                        thought_value = task_output['thought']
                        if str(thought_value).strip().lower() != 'none':
                            thinking = str(thought_value)
                            logger.debug(f"Job {self.job_id}: Found reasoning in format_task_output['thought']")
                    
                    # Then check other keys
                    if not thinking:
                        for key in ['reasoning', 'thinking', 'reasoning_text', 'thoughts', 'plan', 'reasoning_plan']:
                            if key in task_output and task_output[key]:
                                thinking = str(task_output[key])
                                logger.debug(f"Job {self.job_id}: Found reasoning in format_task_output['{key}']")
                                break
                
                # Check raw output for reasoning markers using regex for better extraction
                if not thinking and output_text:
                    reasoning_markers = [
                        'reasoning:', 'thinking:', 'plan:', 'analysis:', 
                        'understanding:', 'key steps', 'reasoning plan',
                        'execution plan', 'approach:'
                    ]
                    for marker in reasoning_markers:
                        if marker.lower() in output_text.lower():
                            # Use regex to extract reasoning section
                            pattern = rf'{re.escape(marker)}\s*(.*?)(?=\n\n|\n---|\n##|\n#|\nTask:|\nExecution:|\nOutput:|$)'
                            match = re.search(pattern, output_text, re.IGNORECASE | re.DOTALL)
                            if match:
                                thinking = match.group(1).strip()
                            else:
                                # Fallback: split and extract
                                parts = output_text.split(marker, 1)
                                if len(parts) > 1:
                                    reasoning_section = parts[1]
                                    end_markers = ['\n\n', '\n---', '\n##', '\n#', '\nTask:', '\nExecution:', '\nOutput:']
                                    for end_marker in end_markers:
                                        if end_marker in reasoning_section:
                                            thinking = reasoning_section.split(end_marker)[0].strip()
                                            break
                                    if not thinking:
                                        thinking = reasoning_section.strip()
                            
                            if thinking:
                                logger.debug(f"Job {self.job_id}: Extracted reasoning from format_task_output raw using marker '{marker}'")
                                break
            
            self._emit_event(
                agent_name=AgentNameEnum.RESPONSE_FORMATTER,
                agent_role=response_formatter.role,
                status=AgentEventStatusEnum.COMPLETED,
                message=f"{response_formatter.role} completed formatting the response.",
                output=output_text[:500] if output_text else None,
                thinking=thinking,
            )
        
        format_task.callback = format_callback

        # Create crew
        crew_instance = Crew(
            agents=[email_planner, tone_specialist, grammar_specialist, dictation_specialist, response_formatter],
            tasks=[plan_task, tone_task, grammar_task, dictation_task, format_task],
            process=Process.sequential,
            verbose=True,
        )

        # Emit start event
        self._emit_event(
            agent_name=AgentNameEnum.SYSTEM,
            agent_role=AgentRoleEnum.SYSTEM,
            status=AgentEventStatusEnum.STARTED,
            message="Email improvement process started",
        )

        workflow_start_time = time.time()
        try:
            logger.info(f"Job {self.job_id}: Executing crew workflow")
            
            # Build translation inputs for CrewAI template variables
            # CrewAI will automatically replace {translation_instruction} and {output_language_requirement} in tasks.yaml
            translation_instruction = ""
            output_language_requirement = "Same language as original."
            format_translation_instruction = ""
            
            if self.translation == "en_to_fa":
                translation_instruction = f"""
{'='*80}
CRITICAL TRANSLATION REQUIREMENT - THIS OVERRIDES ALL OTHER INSTRUCTIONS
{'='*80}

YOU MUST TRANSLATE THE ENTIRE EMAIL FROM ENGLISH TO PERSIAN (فارسی).

REQUIREMENTS:
- The output email MUST be completely in Persian (فارسی).
- Translate ALL content: subject line, body text, greetings, closings, everything.
- Maintain the same meaning, tone, and structure as the original.
- Use proper Persian grammar, vocabulary, and script.
- This translation requirement OVERRIDES any instruction about "same language" or "preserving language".

IMPORTANT: If the task description mentions "same language as original" or similar, IGNORE IT.
You MUST translate to Persian.

{'='*80}

"""
                output_language_requirement = "The output email MUST be in Persian (فارسی)."
                format_translation_instruction = "\n\nIMPORTANT: The improved email from context should already be in Persian (فارسی). Extract and format it as-is. All suggestions and differences must be in Persian."
            elif self.translation == "fa_to_en":
                translation_instruction = f"""
{'='*80}
CRITICAL TRANSLATION REQUIREMENT - THIS OVERRIDES ALL OTHER INSTRUCTIONS
{'='*80}

YOU MUST TRANSLATE THE ENTIRE EMAIL FROM PERSIAN (فارسی) TO ENGLISH.

REQUIREMENTS:
- The output email MUST be completely in English.
- Translate ALL content: subject line, body text, greetings, closings, everything.
- Maintain the same meaning, tone, and structure as the original.
- Use proper English grammar and vocabulary.
- This translation requirement OVERRIDES any instruction about "same language" or "preserving language".

IMPORTANT: If the task description mentions "same language as original" or similar, IGNORE IT.
You MUST translate to English.

{'='*80}

"""
                output_language_requirement = "The output email MUST be in English."
                format_translation_instruction = "\n\nIMPORTANT: The improved email from context should already be in English. Extract and format it as-is. All suggestions and differences must be in English."
            
            # Build inputs dict for CrewAI - these will replace template variables in tasks.yaml
            crew_inputs = {
                "email": email,
                "translation_instruction": translation_instruction,
                "output_language_requirement": output_language_requirement,
                "format_translation_instruction": format_translation_instruction,
                "tone": self.tone,
                "translation": self.translation,
                "audience": self.audience,
                "language": self.language,
            }

            logger.info(f"Job {self.job_id}: Crew inputs prepared - translation={self.translation}, tone={self.tone}, audience={self.audience}")
            logger.info(f"Job {self.job_id}: Crew inputs prepared - translation_instruction={translation_instruction}, output_language_requirement={output_language_requirement}, format_translation_instruction={format_translation_instruction}")
            logger.info(f"Job {self.job_id}: Crew inputs prepared - tone={self.tone}, translation={self.translation}, audience={self.audience}, language={self.language}")
            
            logger.debug(f"Job {self.job_id}: Crew inputs prepared - translation={self.translation}, tone={self.tone}, audience={self.audience}")
            
            # Run crew with all inputs - CrewAI will replace template variables automatically
            result = crew_instance.kickoff(inputs=crew_inputs)
            
            # Extract reasoning from completed tasks after execution
            # CrewAI stores reasoning in task execution results
            try:
                if hasattr(result, 'tasks') and result.tasks:
                    for task_result in result.tasks:
                        # Try to extract reasoning from task result
                        # CrewAI stores task outputs in various formats - check multiple attributes
                        task_output = None
                        if hasattr(task_result, 'output'):
                            task_output = task_result.output
                        elif hasattr(task_result, 'raw'):
                            task_output = task_result.raw
                        elif hasattr(task_result, 'result'):
                            task_output = task_result.result
                        
                        # Get agent role
                        agent_role = None
                        if hasattr(task_result, 'agent'):
                            agent_obj = task_result.agent
                            if hasattr(agent_obj, 'role'):
                                agent_role = agent_obj.role
                        elif hasattr(task_result, 'agent_role'):
                            agent_role = task_result.agent_role
                        elif isinstance(task_result, dict) and 'agent' in task_result:
                            agent_info = task_result['agent']
                            if isinstance(agent_info, dict) and 'role' in agent_info:
                                agent_role = agent_info['role']
                        
                        if task_output and agent_role:
                            reasoning_text = None
                            
                            # Method 1: Check for 'thought' attribute first (CrewAI AgentFinish)
                            if hasattr(task_output, 'thought'):
                                thought_value = getattr(task_output, 'thought')
                                if thought_value and str(thought_value).strip() and str(thought_value).strip().lower() != 'none':
                                    reasoning_text = str(thought_value)
                                    logger.debug(f"Job {self.job_id}: Found reasoning in crew result task_output.thought")
                            
                            # Method 2: Check dictionary for 'thought'
                            if not reasoning_text and isinstance(task_output, dict):
                                if 'thought' in task_output and task_output['thought']:
                                    thought_value = task_output['thought']
                                    if str(thought_value).strip().lower() != 'none':
                                        reasoning_text = str(thought_value)
                                        logger.debug(f"Job {self.job_id}: Found reasoning in crew result task_output['thought']")
                            
                            # Method 3: Check other reasoning attributes
                            if not reasoning_text:
                                if hasattr(task_output, 'reasoning'):
                                    reasoning_text = str(task_output.reasoning)
                                elif isinstance(task_output, dict) and 'reasoning' in task_output:
                                    reasoning_text = str(task_output['reasoning'])
                            
                            # Method 4: Look for reasoning patterns in string output
                            if not reasoning_text and isinstance(task_output, str):
                                reasoning_markers = ['reasoning:', 'thinking:', 'plan:', 'analysis:', 'understanding:', 'key steps']
                                for marker in reasoning_markers:
                                    if marker.lower() in task_output.lower():
                                        # Extract reasoning section using regex
                                        pattern = rf'{re.escape(marker)}\s*(.*?)(?=\n\n|\n---|\n##|\n#|\nTask:|\nExecution:|\nOutput:|$)'
                                        match = re.search(pattern, task_output, re.IGNORECASE | re.DOTALL)
                                        if match:
                                            reasoning_text = match.group(1).strip()
                                        else:
                                            # Fallback: split and extract
                                            parts = task_output.split(marker, 1)
                                            if len(parts) > 1:
                                                reasoning_section = parts[1]
                                                end_markers = ['\n\n', '\n---', '\n##', '\n#', '\nTask:', '\nExecution:']
                                                for end_marker in end_markers:
                                                    if end_marker in reasoning_section:
                                                        reasoning_text = reasoning_section.split(end_marker)[0].strip()
                                                        break
                                                if not reasoning_text:
                                                    reasoning_text = reasoning_section.strip()
                                        if reasoning_text:
                                            break
                            
                            # If we found reasoning, emit it for the corresponding agent
                            if reasoning_text and agent_role:
                                agent_name_map = {
                                    'Email Strategy Planner': AgentNameEnum.EMAIL_PLANNER,
                                    'Tone and Style Specialist': AgentNameEnum.TONE_SPECIALIST,
                                    'Grammar and Syntax Expert': AgentNameEnum.GRAMMAR_SPECIALIST,
                                    'Spelling and Word Choice Specialist': AgentNameEnum.DICTATION_SPECIALIST,
                                    'Response Formatter and Analysis Specialist': AgentNameEnum.RESPONSE_FORMATTER,
                                }
                                agent_name_enum = agent_name_map.get(agent_role)
                                if agent_name_enum:
                                    logger.debug(f"Job {self.job_id}: Found reasoning in task result for {agent_role}: {reasoning_text[:100]}...")
                                    self._emit_event(
                                        agent_name=agent_name_enum,
                                        agent_role=agent_role,
                                        status=AgentEventStatusEnum.COMPLETED,
                                        message=f"{agent_role} reasoning captured.",
                                        thinking=reasoning_text[:1000],  # Limit length
                                    )
            except Exception as e:
                logger.warning(f"Job {self.job_id}: Error extracting reasoning from crew result: {e}", exc_info=True)
            
            # Record job duration
            workflow_duration = time.time() - workflow_start_time
            job_duration_seconds.labels(agent_name="crew_workflow").observe(workflow_duration)
            
            # Try to extract token usage from result if available
            if hasattr(result, "usage_metadata"):
                usage = result.usage_metadata
                if usage:
                    prompt_tokens = getattr(usage, "prompt_tokens", 0)
                    completion_tokens = getattr(usage, "completion_tokens", 0)
                    self._track_llm_usage("crew_workflow", workflow_duration, prompt_tokens, completion_tokens)
            
            logger.info(f"Job {self.job_id}: Crew workflow completed successfully (duration: {workflow_duration:.2f}s)")
            
            # Return structured response
            if hasattr(result, "pydantic") and result.pydantic:
                logger.debug(f"Job {self.job_id}: Returning Pydantic model result")
                return result.pydantic
            
            # Fallback parsing
            if hasattr(result, "raw"):
                try:
                    import json
                    logger.debug(f"Job {self.job_id}: Parsing raw result as JSON")
                    data = json.loads(result.raw)
                    return EmailResponse(**data)
                except (json.JSONDecodeError, Exception) as parse_error:
                    logger.warning(f"Job {self.job_id}: Failed to parse raw result: {parse_error}")
                    pass
            
            logger.error(f"Job {self.job_id}: Failed to parse structured response")
            raise ValueError("Failed to parse structured response")
            
        except Exception as e:
            logger.error(f"Job {self.job_id}: Crew workflow failed: {e}", exc_info=True)
            workflow_duration = time.time() - workflow_start_time
            error_type = type(e).__name__
            error_message = str(e).lower()
            
            # Track LLM error if it's an LLM-related error
            model_name = getattr(self._llm, "_model_name", "unknown")
            # Check if it's an LLM/API error
            is_llm_error = (
                "llm" in error_type.lower() or 
                "api" in error_type.lower() or 
                "openai" in error_type.lower() or
                "anthropic" in error_type.lower() or
                "timeout" in error_message or
                "connection" in error_message or
                "429" in error_message or  # Rate limit
                "401" in error_message or  # Auth error
                "404" in error_message     # Not found
            )
            
            if is_llm_error:
                # Try to determine which agent might have failed
                # Since we can't know for sure, we'll track it as a general error
                llm_request_errors_total.labels(
                    model=model_name, 
                    agent_name="unknown", 
                    error_type=error_type
                ).inc()
                logger.warning(f"Job {self.job_id}: LLM error tracked - {error_type}: {error_message}")
            
            self._emit_event(
                agent_name=AgentNameEnum.SYSTEM,
                agent_role=AgentRoleEnum.SYSTEM,
                status=AgentEventStatusEnum.FAILED,
                message=f"Error: {str(e)}",
            )
            raise


async def run_async(
    job_id: str, 
    email: str, 
    redis_service: RedisService,
    tone: str = "professional",
    translation: str = "none",
    audience: str = "general",
    language: str = "en",
) -> EmailResponse:
    """Run the crew workflow asynchronously."""
    logger.info(f"Starting async workflow for job: {job_id} (tone={tone}, translation={translation}, audience={audience}, language={language})")
    crew_instance = AsyncMailFormatterCrew(job_id, redis_service, tone=tone, translation=translation, audience=audience, language=language)
    
    # Update job status to processing
    redis_service.update_job_status(job_id, JobStatusEnum.PROCESSING)
    
    try:
        logger.info(f"Job {job_id}: Running crew in thread pool")
        # Run in thread pool to avoid blocking
        result = await asyncio.to_thread(crew_instance.run, email)
        logger.info(f"Job {job_id}: Crew workflow completed")
        
        # Update job status to completed
        redis_service.update_job_status(job_id, JobStatusEnum.COMPLETED, result=result)
        
        # Update metrics
        jobs_completed_total.labels(status="completed").inc()
        jobs_in_progress.dec()
        
        # Emit completion event
        event = AgentEvent(
            job_id=job_id,
            agent_name=AgentNameEnum.SYSTEM,
            agent_role=AgentRoleEnum.SYSTEM,
            status=AgentEventStatusEnum.COMPLETED,
            progress=100,
            message="Email improvement completed successfully",
            timestamp=datetime.now(timezone.utc).isoformat(),
            output=None,
        )
        redis_service.add_event(event)
        redis_service.publish_event(event)
        logger.info(f"Job {job_id}: Successfully completed and result stored")
        
        return result
        
    except Exception as e:
        logger.error(f"Job {job_id}: Async workflow failed: {e}", exc_info=True)
        # Update job status to failed
        redis_service.update_job_status(job_id, JobStatusEnum.FAILED, error=str(e))
        
        # Update metrics
        jobs_completed_total.labels(status="failed").inc()
        jobs_in_progress.dec()
        
        # Emit failure event
        event = AgentEvent(
            job_id=job_id,
            agent_name=AgentNameEnum.SYSTEM,
            agent_role=AgentRoleEnum.SYSTEM,
            status=AgentEventStatusEnum.FAILED,
            progress=0,
            message=f"Email improvement failed: {str(e)}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            output=None,
        )
        redis_service.add_event(event)
        redis_service.publish_event(event)
        
        raise
