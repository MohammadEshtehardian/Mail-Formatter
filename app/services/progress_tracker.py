"""
Progress tracker service for tracking agent progress.
"""

from app.core.logging_config import get_logger
from app.models.enums import AgentEventStatusEnum, AgentNameEnum

logger = get_logger(__name__)


class ProgressTrackerService:
    """Service responsible for tracking agent progress."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.agent_progress = {
            AgentNameEnum.EMAIL_PLANNER.value: 0,
            AgentNameEnum.TONE_SPECIALIST.value: 0,
            AgentNameEnum.GRAMMAR_SPECIALIST.value: 0,
            AgentNameEnum.DICTATION_SPECIALIST.value: 0,
            AgentNameEnum.RESPONSE_FORMATTER.value: 0,
        }
        self.agents_started = set()
        logger.debug(f"Progress tracker initialized for job {job_id}")

    def update_progress(
        self,
        agent_name: AgentNameEnum | str,
        status: AgentEventStatusEnum,
    ) -> float:
        """Update progress for an agent and return overall progress."""
        agent_name_str = agent_name.value if isinstance(agent_name, AgentNameEnum) else str(agent_name)

        # Update individual agent progress based on status
        if status == AgentEventStatusEnum.STARTED:
            self.agent_progress[agent_name_str] = 0
        elif status == AgentEventStatusEnum.PROCESSING:
            self.agent_progress[agent_name_str] = 50
        elif status == AgentEventStatusEnum.COMPLETED:
            self.agent_progress[agent_name_str] = 100

        # Calculate overall progress (average of all agents)
        total_agents = len(self.agent_progress)
        total_progress = sum(self.agent_progress.values())
        overall_progress = total_progress / total_agents

        logger.debug(f"Job {self.job_id}: Progress updated - {agent_name_str}: {self.agent_progress[agent_name_str]}%, Overall: {overall_progress:.1f}%")
        return overall_progress

    def mark_agent_started(self, agent_name: AgentNameEnum | str) -> bool:
        """Mark an agent as started. Returns True if this is the first time."""
        agent_name_str = agent_name.value if isinstance(agent_name, AgentNameEnum) else str(agent_name)
        if agent_name_str not in self.agents_started:
            self.agents_started.add(agent_name_str)
            return True
        return False
