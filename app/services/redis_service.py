"""
Redis service for storing job status and events.
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Optional

import redis
from redis import Redis

from app.core.logging_config import get_logger
from app.core.metrics import (
    redis_connection_status,
    redis_operation_duration_seconds,
    redis_operations_total,
)
from app.models.enums import AgentEventStatusEnum, AgentNameEnum, AgentRoleEnum, JobStatusEnum
from app.models.schemas import AgentEvent, EmailResponse, JobStatus

logger = get_logger(__name__)


class RedisService:
    """Service for Redis operations."""

    def __init__(self):
        self._redis_client: Redis | None = None
        self._connection_config = {
            "host": os.getenv("REDIS_HOST", "localhost"),
            "port": int(os.getenv("REDIS_PORT", 6379)),
            "password": os.getenv("REDIS_PASSWORD") or None,
            "db": int(os.getenv("REDIS_DB", 0)),
            "decode_responses": True,
        }
        logger.info(f"RedisService initialized (lazy connection): {self._connection_config['host']}:{self._connection_config['port']}")

    @property
    def redis_client(self) -> Redis:
        """Get Redis client with lazy connection."""
        if self._redis_client is None:
            self._connect()
        return self._redis_client

    def _connect(self) -> None:
        """Establish Redis connection."""
        if self._redis_client is not None:
            return
        
        logger.info(f"Connecting to Redis: {self._connection_config['host']}:{self._connection_config['port']}")
        
        try:
            self._redis_client = redis.Redis(**self._connection_config)
            # Test connection
            self._redis_client.ping()
            redis_connection_status.set(1)
            logger.info("Redis connection established successfully")
        except Exception as e:
            redis_connection_status.set(0)
            logger.error(f"Failed to connect to Redis: {e}")
            logger.error(f"Redis config: host={self._connection_config['host']}, port={self._connection_config['port']}")
            logger.error("Make sure Redis is running and REDIS_HOST is set correctly in .env")
            logger.error("For Mode 2 (bare metal): REDIS_HOST=localhost")
            logger.error("For Mode 1 (Docker): REDIS_HOST=redis")
            raise ConnectionError(f"Failed to connect to Redis: {e}") from e

    def _get_job_key(self, job_id: str) -> str:
        """Get Redis key for job status."""
        return f"job:{job_id}"

    def _get_events_key(self, job_id: str) -> str:
        """Get Redis key for job events list."""
        return f"job:{job_id}:events"

    def create_job(self, job_id: str, email_data: dict) -> JobStatus:
        """Create a new job in Redis."""
        logger.info(f"Creating job: {job_id}")
        operation_start = time.time()
        
        job_status = JobStatus(
            job_id=job_id,
            status=JobStatusEnum.PENDING,
            created_at=datetime.now(timezone.utc).isoformat(),
            completed_at=None,
            result=None,
            error=None,
        )
        
        try:
            # Store job status
            self.redis_client.setex(
                self._get_job_key(job_id),
                3600,  # 1 hour TTL
                json.dumps(job_status.model_dump()),
            )
            
            # Store original email data
            self.redis_client.setex(
                f"job:{job_id}:email",
                3600,
                json.dumps(email_data),
            )
            logger.debug(f"Job {job_id} created successfully")
            
            # Update metrics
            redis_operations_total.labels(operation="create_job").inc()
            redis_operation_duration_seconds.labels(operation="create_job").observe(time.time() - operation_start)
        except Exception as e:
            redis_operation_duration_seconds.labels(operation="create_job").observe(time.time() - operation_start)
            logger.error(f"Failed to create job {job_id}: {e}")
            raise
        
        return job_status

    def update_job_status(
        self,
        job_id: str,
        status: JobStatusEnum,
        result: Optional[EmailResponse] = None,
        error: Optional[str] = None,
    ) -> JobStatus:
        """Update job status."""
        logger.info(f"Updating job {job_id} status to: {status.value}")
        operation_start = time.time()
        
        job_data = self.get_job(job_id)
        if not job_data:
            logger.error(f"Job {job_id} not found for status update")
            raise ValueError(f"Job {job_id} not found")

        job_data.status = status
        if result:
            job_data.result = result
            logger.debug(f"Job {job_id} result updated")
        if error:
            job_data.error = error
            logger.warning(f"Job {job_id} error: {error}")
        if status in [JobStatusEnum.COMPLETED, JobStatusEnum.FAILED]:
            job_data.completed_at = datetime.now(timezone.utc).isoformat()
            logger.info(f"Job {job_id} marked as {status.value}")

        try:
            self.redis_client.setex(
                self._get_job_key(job_id),
                3600,
                json.dumps(job_data.model_dump()),
            )
            
            # Update metrics
            redis_operations_total.labels(operation="update_status").inc()
            redis_operation_duration_seconds.labels(operation="update_status").observe(time.time() - operation_start)
        except Exception as e:
            redis_operation_duration_seconds.labels(operation="update_status").observe(time.time() - operation_start)
            logger.error(f"Failed to update job {job_id} status: {e}")
            raise

        return job_data

    def get_job(self, job_id: str) -> Optional[JobStatus]:
        """Get job status."""
        operation_start = time.time()
        try:
            data = self.redis_client.get(self._get_job_key(job_id))
            redis_operations_total.labels(operation="get_job").inc()
            redis_operation_duration_seconds.labels(operation="get_job").observe(time.time() - operation_start)
            if not data:
                return None
            return JobStatus(**json.loads(data))
        except Exception as e:
            redis_operation_duration_seconds.labels(operation="get_job").observe(time.time() - operation_start)
            raise

    def add_event(self, event: AgentEvent) -> None:
        """Add an event to the job's event list."""
        logger.debug(f"Adding event for job {event.job_id}: {event.agent_name.value} - {event.status.value}")
        operation_start = time.time()
        try:
            self.redis_client.lpush(
                self._get_events_key(event.job_id),
                json.dumps(event.model_dump()),
            )
            # Keep only last 100 events
            self.redis_client.ltrim(self._get_events_key(event.job_id), 0, 99)
            # Set TTL on events list
            self.redis_client.expire(self._get_events_key(event.job_id), 3600)
            
            # Update metrics
            redis_operations_total.labels(operation="add_event").inc()
            redis_operation_duration_seconds.labels(operation="add_event").observe(time.time() - operation_start)
        except Exception as e:
            redis_operation_duration_seconds.labels(operation="add_event").observe(time.time() - operation_start)
            logger.error(f"Failed to add event for job {event.job_id}: {e}")
            raise

    def get_events(self, job_id: str, limit: int = 100) -> list[AgentEvent]:
        """Get events for a job."""
        operation_start = time.time()
        try:
            events_data = self.redis_client.lrange(
                self._get_events_key(job_id),
                0,
                limit - 1,
            )
            
            # Update metrics
            redis_operations_total.labels(operation="get_events").inc()
            redis_operation_duration_seconds.labels(operation="get_events").observe(time.time() - operation_start)
            
            return [AgentEvent(**json.loads(event)) for event in reversed(events_data)]
        except Exception as e:
            redis_operation_duration_seconds.labels(operation="get_events").observe(time.time() - operation_start)
            raise

    def publish_event(self, event: AgentEvent) -> None:
        """Publish event to Redis pub/sub channel for WebSocket."""
        channel = f"job:{event.job_id}:stream"
        logger.debug(f"Publishing event to channel {channel}")
        operation_start = time.time()
        try:
            # Serialize with mode='json' to ensure enums are converted to their values
            event_dict = event.model_dump(mode='json')
            event_json = json.dumps(event_dict)
            subscribers = self.redis_client.publish(channel, event_json)
            logger.debug(f"Event published to {subscribers} subscribers (Redis pub/sub): {event_dict.get('agent_name')} - {event_dict.get('status')}")
            
            # Update metrics
            redis_operations_total.labels(operation="publish_event").inc()
            redis_operation_duration_seconds.labels(operation="publish_event").observe(time.time() - operation_start)
        except Exception as e:
            redis_operation_duration_seconds.labels(operation="publish_event").observe(time.time() - operation_start)
            logger.error(f"Failed to publish event to channel {channel}: {e}")
            raise

    def subscribe_to_job(self, job_id: str):
        """Create a pub/sub subscriber for a job."""
        pubsub = self.redis_client.pubsub()
        channel = f"job:{job_id}:stream"
        pubsub.subscribe(channel)
        return pubsub
