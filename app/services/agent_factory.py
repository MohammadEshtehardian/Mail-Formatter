"""
Agent factory service for creating agents with proper configuration.
"""

import yaml
from pathlib import Path

from crewai import Agent

from app.core.logging_config import get_logger
from app.models.enums import AgentEventStatusEnum, AgentNameEnum, AgentRoleEnum, LanguageEnum
from app.services.event_emitter import EventEmitterService
from app.services.progress_tracker import ProgressTrackerService
from app.services.reasoning_extractor import ReasoningExtractor

logger = get_logger(__name__)


class AgentFactory:
    """Service responsible for creating agents."""

    def __init__(
        self,
        job_id: str,
        llm,
        event_emitter: EventEmitterService,
        progress_tracker: ProgressTrackerService,
        reasoning_extractor: ReasoningExtractor,
        language: LanguageEnum = LanguageEnum.ENGLISH,
    ):
        self.job_id = job_id
        self.llm = llm
        self.event_emitter = event_emitter
        self.progress_tracker = progress_tracker
        self.reasoning_extractor = reasoning_extractor
        self.language = language if isinstance(language, LanguageEnum) else LanguageEnum(language)
        self._agents_config = self._load_agents_config()

    def create_agent(self, agent_key: str, agent_name: str) -> Agent:
        """Create an agent with callbacks."""
        config = self._agents_config[agent_key].copy()
        role = config.get("role", agent_name)

        # Map agent_name to enum for tracking
        try:
            agent_name_enum = AgentNameEnum(agent_name) if isinstance(agent_name, str) else agent_name
            agent_name_str = agent_name_enum.value if isinstance(agent_name_enum, AgentNameEnum) else str(agent_name_enum)
        except ValueError:
            agent_name_str = str(agent_name)

        # Add language instruction to agent config for reasoning
        if isinstance(config, dict):
            thinking_language = "Persian (فارسی)" if self.language == LanguageEnum.PERSIAN else "English"
            if "backstory" in config:
                config["backstory"] = config["backstory"] + f"\n\nIMPORTANT: When providing reasoning or thinking, write it in {thinking_language}."
            elif "goal" in config:
                config["goal"] = config["goal"] + f"\n\nIMPORTANT: When providing reasoning or thinking, write it in {thinking_language}."

        # Create step callback
        def tracked_step_callback(step_output):
            logger.debug(f"Job {self.job_id}: Step callback received for {role}, step_output type: {type(step_output)}")

            # Only emit started event on the first step for this agent
            if self.progress_tracker.mark_agent_started(agent_name_str):
                # Try to convert agent role string to enum
                try:
                    agent_role = AgentRoleEnum(role)
                except ValueError:
                    agent_role = role  # Fallback to string if not found
                
                # Emit STARTED event first to notify user that agent has begun
                progress = self.progress_tracker.update_progress(agent_name_str, AgentEventStatusEnum.STARTED)
                self.event_emitter.emit_event(
                    agent_name=agent_name_enum,
                    agent_role=agent_role,
                    status=AgentEventStatusEnum.STARTED,
                    message=f"{role} has started working on the task.",
                    progress=progress,
                )
                
                # Then emit PROCESSING event with thinking if available
                thinking = self.reasoning_extractor.extract_from_step_output(step_output)
                progress = self.progress_tracker.update_progress(agent_name_str, AgentEventStatusEnum.PROCESSING)
                self.event_emitter.emit_event(
                    agent_name=agent_name_enum,
                    agent_role=agent_role,
                    status=AgentEventStatusEnum.PROCESSING,
                    message=f"{role} is working on the task...",
                    progress=progress,
                    thinking=thinking,
                )

        return Agent(
            config=config,
            llm=self.llm,
            verbose=True,
            allow_delegation=False,
            step_callback=tracked_step_callback,
        )

    def _load_agents_config(self) -> dict:
        """Load agents configuration from YAML."""
        path = Path(__file__).resolve().parent.parent / "config" / "agents.yaml"
        logger.debug(f"Loading agents config: {path}")
        try:
            with open(path) as f:
                config = yaml.safe_load(f)
            logger.debug(f"Successfully loaded agents.yaml")
            return config
        except Exception as e:
            logger.error(f"Failed to load agents.yaml: {e}")
            raise
