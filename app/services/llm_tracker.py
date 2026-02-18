"""
LLM tracker service for tracking LLM usage, duration, and errors.
"""

import time

from crewai.hooks import (
    register_before_llm_call_hook,
    register_after_llm_call_hook,
    LLMCallHookContext,
)

from app.core.logging_config import get_logger
from app.core.metrics import (
    llm_request_duration_seconds,
    llm_request_errors_total,
    llm_requests_total,
    llm_tokens_total,
)
from app.models.enums import AgentNameEnum

logger = get_logger(__name__)


class LLMTrackerService:
    """Service responsible for tracking LLM usage and metrics."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self._llm_call_times: dict[tuple[str, str], float] = {}
        self._agent_name_map = {
            'Email Strategy Planner': AgentNameEnum.EMAIL_PLANNER.value,
            'Tone and Style Specialist': AgentNameEnum.TONE_SPECIALIST.value,
            'Grammar and Syntax Expert': AgentNameEnum.GRAMMAR_SPECIALIST.value,
            'Spelling and Word Choice Specialist': AgentNameEnum.DICTATION_SPECIALIST.value,
            'Response Formatter and Analysis Specialist': AgentNameEnum.RESPONSE_FORMATTER.value,
        }
        logger.debug(f"LLM tracker initialized for job {job_id}")

    def register_hooks(self) -> None:
        """Register LLM hooks for tracking."""
        register_before_llm_call_hook(self._before_llm_hook)
        register_after_llm_call_hook(self._after_llm_hook)
        logger.debug(f"Job {self.job_id}: LLM hooks registered")

    def _before_llm_hook(self, context: LLMCallHookContext) -> None:
        """Track LLM call start time before each LLM call."""
        try:
            if not hasattr(context, 'agent') or not context.agent:
                return

            agent_role = getattr(context.agent, 'role', 'unknown')
            agent_name_str = self._get_agent_name(agent_role)

            model_name = self._get_model_name(context.llm)

            # Store start time for duration calculation
            call_key = (agent_name_str, model_name)
            self._llm_call_times[call_key] = time.time()
            logger.debug(f"Job {self.job_id}: Before LLM hook - {agent_name_str} - model: {model_name}")

        except Exception as e:
            logger.warning(f"Error in before LLM hook: {e}", exc_info=True)

    def _after_llm_hook(self, context: LLMCallHookContext) -> None:
        """Track LLM usage, duration, and errors after each LLM call."""
        try:
            if not hasattr(context, 'agent') or not context.agent:
                return

            agent_role = getattr(context.agent, 'role', 'unknown')
            agent_name_str = self._get_agent_name(agent_role)
            model_name = self._get_model_name(context.llm)

            call_key = (agent_name_str, model_name)
            start_time = self._llm_call_times.pop(call_key, None)
            duration = time.time() - start_time if start_time else 0

            # Track LLM request
            llm_requests_total.labels(model=model_name, agent_name=agent_name_str).inc()
            logger.debug(f"Job {self.job_id}: LLM request tracked - {agent_name_str} - model: {model_name}")

            # Track request duration
            if duration > 0:
                llm_request_duration_seconds.labels(model=model_name, agent_name=agent_name_str).observe(duration)
                logger.debug(f"Job {self.job_id}: LLM duration tracked - {agent_name_str} - duration: {duration:.2f}s")
            else:
                logger.warning(f"Job {self.job_id}: LLM duration is 0 or missing start time for {agent_name_str}")

            # Extract and track token usage
            prompt_tokens, completion_tokens = self._extract_token_usage(context)

            # Track tokens
            if prompt_tokens > 0:
                llm_tokens_total.labels(model=model_name, agent_name=agent_name_str, type="prompt").inc(prompt_tokens)
            if completion_tokens > 0:
                llm_tokens_total.labels(model=model_name, agent_name=agent_name_str, type="completion").inc(completion_tokens)
            if prompt_tokens > 0 or completion_tokens > 0:
                total_tokens = prompt_tokens + completion_tokens
                llm_tokens_total.labels(model=model_name, agent_name=agent_name_str, type="total").inc(total_tokens)

            logger.debug(
                f"Job {self.job_id}: LLM call tracked - {agent_name_str} - model: {model_name} - "
                f"duration: {duration:.2f}s - tokens: {prompt_tokens}+{completion_tokens}={prompt_tokens+completion_tokens}"
            )

        except Exception as e:
            # Track error
            try:
                agent_role = getattr(context.agent, 'role', 'unknown') if hasattr(context, 'agent') and context.agent else 'unknown'
                agent_name_str = self._get_agent_name(agent_role)
                model_name = self._get_model_name(context.llm) if hasattr(context, 'llm') else "unknown"
                error_type = type(e).__name__
                llm_request_errors_total.labels(model=model_name, agent_name=agent_name_str, error_type=error_type).inc()
            except:
                pass
            logger.warning(f"Error tracking LLM usage in hook: {e}", exc_info=True)

    def _get_agent_name(self, agent_role: str) -> str:
        """Get agent name from agent role."""
        return self._agent_name_map.get(agent_role, agent_role.lower().replace(' ', '_'))

    def _get_model_name(self, llm) -> str:
        """Get model name from LLM instance."""
        model_name = getattr(llm, "_model_name", None)
        if not model_name:
            model_name = getattr(llm, "model", "unknown")
            if hasattr(llm, "model_name"):
                model_name = llm.model_name
        return model_name

    def _extract_token_usage(self, context: LLMCallHookContext) -> tuple[int, int]:
        """Extract token usage from LLM context."""
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
            prompt_tokens = max(1, total_chars // 4)
            logger.debug(f"Job {self.job_id}: Estimated prompt tokens from content: {prompt_tokens}")

        if completion_tokens == 0 and context.response:
            response_chars = len(str(context.response))
            completion_tokens = max(1, response_chars // 4)
            logger.debug(f"Job {self.job_id}: Estimated completion tokens from response: {completion_tokens}")

        return prompt_tokens, completion_tokens
