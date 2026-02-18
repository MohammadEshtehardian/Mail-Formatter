"""
Event emitter service for handling agent events.
"""

from datetime import datetime, timezone

from app.core.logging_config import get_logger
from app.core.metrics import agent_events_total, agent_progress as agent_progress_metric
from app.models.enums import AgentEventStatusEnum, AgentNameEnum, AgentRoleEnum
from app.models.schemas import AgentEvent
from app.services.redis_service import RedisService

logger = get_logger(__name__)


class EventEmitterService:
    """Service responsible for emitting agent events."""

    def __init__(self, job_id: str, redis_service: RedisService):
        self.job_id = job_id
        self.redis_service = redis_service

    def emit_event(
        self,
        agent_name: AgentNameEnum | str,
        agent_role: AgentRoleEnum | str,
        status: AgentEventStatusEnum | str,
        message: str,
        progress: float | None = None,
        output: str | None = None,
        thinking: str | None = None,
    ) -> None:
        """Emit an event to Redis."""
        # Normalize enums
        agent_name = self._normalize_agent_name(agent_name)
        agent_role = self._normalize_agent_role(agent_role)
        status = self._normalize_status(status)

        agent_name_str = agent_name.value if isinstance(agent_name, AgentNameEnum) else str(agent_name)
        status_str = status.value if isinstance(status, AgentEventStatusEnum) else str(status)

        event = AgentEvent(
            job_id=self.job_id,
            agent_name=agent_name,
            agent_role=agent_role,
            status=status,
            progress=progress or 0.0,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
            output=output,
            thinking=thinking,
        )

        logger.debug(f"Job {self.job_id}: Emitting event - {agent_name_str} - {status_str} (progress: {event.progress:.1f}%)")

        # Update metrics
        agent_events_total.labels(agent_name=agent_name_str, status=status_str).inc()
        agent_progress_metric.labels(agent_name=agent_name_str, job_id=self.job_id).set(event.progress)

        # Publish to Redis
        self.redis_service.add_event(event)
        self.redis_service.publish_event(event)

    def _normalize_agent_name(self, agent_name: AgentNameEnum | str) -> AgentNameEnum:
        """Normalize agent name to enum."""
        if isinstance(agent_name, AgentNameEnum):
            return agent_name
        try:
            return AgentNameEnum(agent_name)
        except ValueError:
            logger.warning(f"Unknown agent name: {agent_name}, using SYSTEM")
            return AgentNameEnum.SYSTEM

    def _normalize_agent_role(self, agent_role: AgentRoleEnum | str) -> AgentRoleEnum:
        """Normalize agent role to enum."""
        if isinstance(agent_role, AgentRoleEnum):
            return agent_role
        try:
            return AgentRoleEnum(agent_role)
        except ValueError:
            logger.warning(f"Unknown agent role: {agent_role}, using SYSTEM")
            return AgentRoleEnum.SYSTEM

    def _normalize_status(self, status: AgentEventStatusEnum | str) -> AgentEventStatusEnum:
        """Normalize status to enum."""
        if isinstance(status, AgentEventStatusEnum):
            return status
        try:
            return AgentEventStatusEnum(status)
        except ValueError:
            logger.warning(f"Unknown status: {status}, using PROCESSING")
            return AgentEventStatusEnum.PROCESSING
