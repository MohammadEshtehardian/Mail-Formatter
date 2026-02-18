"""
Crew executor service for executing crew workflows.
"""

import time

from crewai import Crew, Process

from app.core.logging_config import get_logger
from app.core.metrics import job_duration_seconds
from app.models.enums import AgentEventStatusEnum, AgentNameEnum, AgentRoleEnum
from app.services.event_emitter import EventEmitterService
from app.services.reasoning_extractor import ReasoningExtractor

logger = get_logger(__name__)


class CrewExecutor:
    """Service responsible for executing crew workflows."""

    def __init__(
        self,
        job_id: str,
        event_emitter: EventEmitterService,
        reasoning_extractor: ReasoningExtractor,
    ):
        self.job_id = job_id
        self.event_emitter = event_emitter
        self.reasoning_extractor = reasoning_extractor

    def execute(
        self,
        crew_instance: Crew,
        inputs: dict,
    ):
        """Execute crew workflow with inputs."""
        logger.info(f"Job {self.job_id}: Executing crew workflow")

        # Emit start event
        self.event_emitter.emit_event(
            agent_name=AgentNameEnum.SYSTEM,
            agent_role=AgentRoleEnum.SYSTEM,
            status=AgentEventStatusEnum.STARTED,
            message="Email improvement process started",
            progress=0.0,
        )

        workflow_start_time = time.time()

        try:
            # Run crew with inputs
            result = crew_instance.kickoff(inputs=inputs)

            # Extract reasoning from completed tasks after execution
            self._extract_reasoning_from_result(result)

            # Record job duration
            workflow_duration = time.time() - workflow_start_time
            job_duration_seconds.labels(agent_name="crew_workflow").observe(workflow_duration)

            logger.info(f"Job {self.job_id}: Crew workflow completed successfully (duration: {workflow_duration:.2f}s)")

            return result

        except Exception as e:
            workflow_duration = time.time() - workflow_start_time
            logger.error(f"Job {self.job_id}: Crew workflow failed: {e}", exc_info=True)

            self.event_emitter.emit_event(
                agent_name=AgentNameEnum.SYSTEM,
                agent_role=AgentRoleEnum.SYSTEM,
                status=AgentEventStatusEnum.FAILED,
                message=f"Error: {str(e)}",
                progress=0.0,
            )

            raise

    def _extract_reasoning_from_result(self, result) -> None:
        """Extract reasoning from crew execution result and emit events."""
        reasoning_by_agent = self.reasoning_extractor.extract_from_crew_result(result)

        # Map agent roles to agent name enums and role enums
        agent_name_map = {
            AgentRoleEnum.EMAIL_STRATEGY_PLANNER.value: AgentNameEnum.EMAIL_PLANNER,
            AgentRoleEnum.TONE_AND_STYLE_SPECIALIST.value: AgentNameEnum.TONE_SPECIALIST,
            AgentRoleEnum.GRAMMAR_AND_SYNTAX_EXPERT.value: AgentNameEnum.GRAMMAR_SPECIALIST,
            AgentRoleEnum.SPELLING_AND_WORD_CHOICE_SPECIALIST.value: AgentNameEnum.DICTATION_SPECIALIST,
            AgentRoleEnum.RESPONSE_FORMATTER_AND_ANALYSIS_SPECIALIST.value: AgentNameEnum.RESPONSE_FORMATTER,
        }

        for agent_role_str, reasoning_text in reasoning_by_agent.items():
            agent_name_enum = agent_name_map.get(agent_role_str)
            if agent_name_enum:
                # Try to get AgentRoleEnum from string
                try:
                    agent_role_enum = AgentRoleEnum(agent_role_str)
                except ValueError:
                    agent_role_enum = agent_role_str  # Fallback to string if not found
                
                logger.debug(f"Job {self.job_id}: Found reasoning in task result for {agent_role_str}: {reasoning_text[:100]}...")
                self.event_emitter.emit_event(
                    agent_name=agent_name_enum,
                    agent_role=agent_role_enum,
                    status=AgentEventStatusEnum.COMPLETED,
                    message=f"{agent_role_str} reasoning captured.",
                    progress=100.0,
                    thinking=reasoning_text[:1000],  # Limit length
                )
