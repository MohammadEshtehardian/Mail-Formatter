"""
Task factory service for creating tasks with callbacks.
"""

import yaml
from pathlib import Path

from crewai import Task

from app.core.logging_config import get_logger
from app.models.enums import (
    AgentEventStatusEnum,
    AgentNameEnum,
    AgentRoleEnum,
    AudienceEnum,
    LanguageEnum,
    ToneEnum,
    TranslationDirectionEnum,
)
from app.services.event_emitter import EventEmitterService
from app.services.progress_tracker import ProgressTrackerService
from app.services.reasoning_extractor import ReasoningExtractor

logger = get_logger(__name__)


class TaskFactory:
    """Service responsible for creating tasks."""

    def __init__(
        self,
        job_id: str,
        event_emitter: EventEmitterService,
        progress_tracker: ProgressTrackerService,
        reasoning_extractor: ReasoningExtractor,
        tone: ToneEnum = ToneEnum.PROFESSIONAL,
        translation: TranslationDirectionEnum = TranslationDirectionEnum.NONE,
        audience: AudienceEnum = AudienceEnum.GENERAL,
        language: LanguageEnum = LanguageEnum.ENGLISH,
    ):
        self.job_id = job_id
        self.event_emitter = event_emitter
        self.progress_tracker = progress_tracker
        self.reasoning_extractor = reasoning_extractor
        # Normalize to enums if strings are passed
        self.tone = tone if isinstance(tone, ToneEnum) else ToneEnum(tone)
        self.translation = translation if isinstance(translation, TranslationDirectionEnum) else TranslationDirectionEnum(translation)
        self.audience = audience if isinstance(audience, AudienceEnum) else AudienceEnum(audience)
        self.language = language if isinstance(language, LanguageEnum) else LanguageEnum(language)
        self._tasks_config = self._load_tasks_config()

        # Map task_key to agent name enum
        self._task_to_agent_map = {
            "plan_email_improvement": AgentNameEnum.EMAIL_PLANNER,
            "improve_tone": AgentNameEnum.TONE_SPECIALIST,
            "fix_grammar": AgentNameEnum.GRAMMAR_SPECIALIST,
            "fix_dictation": AgentNameEnum.DICTATION_SPECIALIST,
        }

    def create_task(self, task_key: str, agent, context_tasks: list[Task] = None) -> Task:
        """Create a task with callback."""
        config = self._tasks_config[task_key].copy()
        agent_role_str = agent.role if hasattr(agent, "role") else "Agent"
        
        # Try to convert agent role string to enum
        try:
            agent_role = AgentRoleEnum(agent_role_str)
        except ValueError:
            agent_role = agent_role_str  # Fallback to string if not found

        agent_name_enum = self._task_to_agent_map.get(task_key, AgentNameEnum.SYSTEM)

        # Inject user preferences into task description
        if isinstance(config.get("description"), str):
            description = config["description"]

            # Append user preferences to description
            preferences = []
            if self.tone != ToneEnum.PROFESSIONAL:
                preferences.append(f"Desired tone: {self.tone.value}")
            if self.translation != TranslationDirectionEnum.NONE:
                preferences.append(f"Translation: {self.translation.value}")
            if self.audience != AudienceEnum.GENERAL:
                preferences.append(f"Target audience: {self.audience.value}")

            # Add language instruction for thinking/reasoning
            thinking_language = "Persian (فارسی)" if self.language == LanguageEnum.PERSIAN else "English"
            description += f"\n\nIMPORTANT: When providing your reasoning or thinking process, write it in {thinking_language}. Your reasoning should match the user's language preference."

            if preferences:
                description += f"\n\nUser Preferences:\n" + "\n".join(f"- {p}" for p in preferences)

            config["description"] = description

        task = Task(
            config=config,
            agent=agent,
            context=context_tasks or [],
        )

        # Create callback for this task
        def task_callback(task_output):
            output_text = task_output.raw if hasattr(task_output, "raw") else str(task_output)
            thinking = self.reasoning_extractor.extract_from_task_output(task_output, output_text)

            overall_progress = self.progress_tracker.update_progress(
                agent_name_enum.value,
                AgentEventStatusEnum.COMPLETED
            )

            agent_role_display = agent_role.value if isinstance(agent_role, AgentRoleEnum) else agent_role
            self.event_emitter.emit_event(
                agent_name=agent_name_enum,
                agent_role=agent_role,
                status=AgentEventStatusEnum.COMPLETED,
                message=f"{agent_role_display} completed their task.",
                progress=overall_progress,
                output=output_text[:500] if output_text else None,
                thinking=thinking,
            )

        task.callback = task_callback
        return task

    def create_format_task(self, agent, context_tasks: list[Task], output_pydantic) -> Task:
        """Create format response task with Pydantic output."""
        config = self._tasks_config["format_response"].copy()

        task = Task(
            config=config,
            agent=agent,
            context=context_tasks,
            output_pydantic=output_pydantic,
        )

        def format_callback(task_output):
            output_text = task_output.raw if hasattr(task_output, "raw") else str(task_output)
            thinking = self.reasoning_extractor.extract_from_task_output(task_output, output_text)

            overall_progress = self.progress_tracker.update_progress(
                AgentNameEnum.RESPONSE_FORMATTER.value,
                AgentEventStatusEnum.COMPLETED
            )

            # Try to convert agent role string to enum
            agent_role_str = agent.role if hasattr(agent, "role") else "Agent"
            try:
                agent_role = AgentRoleEnum(agent_role_str)
            except ValueError:
                agent_role = agent_role_str  # Fallback to string if not found
            
            agent_role_display = agent_role.value if isinstance(agent_role, AgentRoleEnum) else agent_role
            self.event_emitter.emit_event(
                agent_name=AgentNameEnum.RESPONSE_FORMATTER,
                agent_role=agent_role,
                status=AgentEventStatusEnum.COMPLETED,
                message=f"{agent_role_display} completed formatting the response.",
                progress=overall_progress,
                output=output_text[:500] if output_text else None,
                thinking=thinking,
            )

        task.callback = format_callback
        return task

    def _load_tasks_config(self) -> dict:
        """Load tasks configuration from YAML."""
        path = Path(__file__).resolve().parent.parent / "config" / "tasks.yaml"
        logger.debug(f"Loading tasks config: {path}")
        try:
            with open(path) as f:
                config = yaml.safe_load(f)
            logger.debug(f"Successfully loaded tasks.yaml")
            return config
        except Exception as e:
            logger.error(f"Failed to load tasks.yaml: {e}")
            raise
