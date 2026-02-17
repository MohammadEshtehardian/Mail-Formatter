"""
FastAPI router for job management and WebSocket streaming endpoints.
Handles job creation, status tracking, event streaming via WebSocket, and event retrieval.
"""

import asyncio
import json
import uuid
from typing import Dict, Set

from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect

import time

from app.core.logging_config import get_logger
from app.core.metrics import (
    active_websocket_connections,
    api_request_duration_seconds,
    api_requests_total,
    jobs_created_total,
    jobs_in_progress,
    websocket_connection_duration_seconds,
    websocket_connections_total,
    websocket_events_sent_total,
)
from app.models.enums import (
    AgentEventStatusEnum,
    AgentNameEnum,
    JobStatusEnum,
    ToneEnum,
    TranslationDirectionEnum,
    AudienceEnum,
    LanguageEnum,
)
from app.models.schemas import (
    JobEventsResponse,
    JobRequest,
    JobResponse,
    JobStatus,
)
from app.services.mail_formatter_crew_async import run_async
from app.services.redis_service import RedisService

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/jobs",
    tags=["jobs"],
)

# Lazy initialization - RedisService will connect on first use
redis_service = RedisService()

# WebSocket connection manager
class WebSocketManager:
    """Manages WebSocket connections per job."""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, job_id: str):
        """Accept WebSocket connection and add to active connections."""
        await websocket.accept()
        if job_id not in self.active_connections:
            self.active_connections[job_id] = set()
        self.active_connections[job_id].add(websocket)
        active_websocket_connections.inc()
        logger.info(f"WebSocket connected for job: {job_id} (total: {len(self.active_connections.get(job_id, set()))})")
    
    def disconnect(self, websocket: WebSocket, job_id: str):
        """Remove WebSocket from active connections."""
        if job_id in self.active_connections:
            self.active_connections[job_id].discard(websocket)
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]
        active_websocket_connections.dec()
        logger.info(f"WebSocket disconnected for job: {job_id}")
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send message to a specific WebSocket."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending WebSocket message: {e}")
    
    async def broadcast_to_job(self, job_id: str, message: dict):
        """Broadcast message to all WebSocket connections for a job."""
        if job_id not in self.active_connections:
            return
        
        disconnected = set()
        for websocket in list(self.active_connections[job_id]):  # Create a copy to iterate safely
            try:
                await websocket.send_json(message)
                event_type = message.get("status", message.get("type", "unknown"))
                websocket_events_sent_total.labels(event_type=str(event_type)).inc()
            except Exception as e:
                logger.warning(f"Error broadcasting to WebSocket for job {job_id}: {e}")
                disconnected.add(websocket)
        
        # Remove disconnected websockets
        for websocket in disconnected:
            self.disconnect(websocket, job_id)

# Global WebSocket manager instance
websocket_manager = WebSocketManager()


@router.post(
    "/",
    response_model=JobResponse,
    summary="Create email improvement job",
    description="""
    Create a new asynchronous email improvement job. Returns a job ID and WebSocket URL.
    Connect to the WebSocket endpoint to receive real-time updates.
    """,
)
async def create_email_improvement_job(
    request: JobRequest,
    background_tasks: BackgroundTasks,
) -> JobResponse:
    """
    Create a new email improvement job.
    
    Args:
        request: JobRequest containing the email to improve
        background_tasks: FastAPI background tasks
        
    Returns:
        JobResponse with job_id and stream_url
    """
    start_time = time.time()
    logger.info("Received request to create email improvement job")
    
    try:
        # Generate job ID
        job_id = str(uuid.uuid4())
        logger.info(f"Generated job ID: {job_id}")
        
        # Create job in Redis
        email_data = request.email.model_dump()
        redis_service.create_job(job_id, email_data)
        
        # Update metrics
        jobs_created_total.labels(status="pending").inc()
        jobs_in_progress.inc()
        
        # Combine subject and body for the crew
        email_text = f"Subject: {request.email.subject}\n\n{request.email.body}"
        logger.debug(f"Job {job_id}: Email prepared (subject length: {len(request.email.subject)}, body length: {len(request.email.body)})")
        
        # Extract enum values (Pydantic will validate and convert strings to enums)
        tone_value = request.tone.value if isinstance(request.tone, ToneEnum) else str(request.tone)
        translation_value = request.translation.value if isinstance(request.translation, TranslationDirectionEnum) else str(request.translation)
        audience_value = request.audience.value if isinstance(request.audience, AudienceEnum) else str(request.audience)
        language_value = request.language.value if isinstance(request.language, LanguageEnum) else str(request.language)
        
        logger.debug(f"Job {job_id}: Options - tone={tone_value}, translation={translation_value}, audience={audience_value}, language={language_value}")
        
        # Start background task
        background_tasks.add_task(
            run_async,
            job_id=job_id,
            email=email_text,
            redis_service=redis_service,
            tone=tone_value,
            translation=translation_value,
            audience=audience_value,
            language=language_value,
        )
        logger.info(f"Job {job_id}: Background task started")
        
        response = JobResponse(
            job_id=job_id,
            status=JobStatusEnum.PENDING,
            message="Job created successfully. Connect to WebSocket endpoint for updates.",
            stream_url=f"/api/v1/jobs/{job_id}/ws",
        )
        logger.info(f"Job {job_id}: Created successfully")
        
        # Record API metrics
        duration = time.time() - start_time
        api_request_duration_seconds.labels(method="POST", endpoint="/api/v1/jobs/").observe(duration)
        api_requests_total.labels(method="POST", endpoint="/api/v1/jobs/", status_code=200).inc()
        
        return response
    except Exception as e:
        logger.error(f"Failed to create job: {e}", exc_info=True)
        api_requests_total.labels(method="POST", endpoint="/api/v1/jobs/", status_code=500).inc()
        raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")


@router.websocket("/{job_id}/ws")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint for real-time job updates.
    Connect to this endpoint to receive events as agents complete their tasks.
    Events are sent in real-time as the email improvement process progresses.
    """
    stream_start_time = time.time()
    logger.info(f"WebSocket connection requested for job: {job_id}")
    
    # Verify job exists
    job = redis_service.get_job(job_id)
    if not job:
        logger.warning(f"WebSocket requested for non-existent job: {job_id}")
        await websocket.close(code=1008, reason="Job not found")
        return
    
    # Update metrics
    websocket_connections_total.labels(status="opened").inc()
    
    try:
        # Accept connection
        await websocket_manager.connect(websocket, job_id)
        
        # Send initial connection event
        await websocket_manager.send_personal_message(
            {'type': 'connected', 'job_id': job_id},
            websocket
        )
        websocket_events_sent_total.labels(event_type="connected").inc()
        
        # Get existing events and send them
        existing_events = redis_service.get_events(job_id)
        logger.debug(f"Job {job_id}: Sending {len(existing_events)} existing events via WebSocket")
        for event in existing_events:
            try:
                # Use mode='json' to ensure enums are serialized as their values
                event_dict = event.model_dump(mode='json')
                await websocket_manager.send_personal_message(event_dict, websocket)
                event_status = event_dict.get('status', 'unknown')
                websocket_events_sent_total.labels(event_type=str(event_status)).inc()
            except Exception as e:
                logger.warning(f"Error sending historical event: {e}")
        
        # Subscribe to new events via Redis pub/sub
        pubsub = redis_service.subscribe_to_job(job_id)
        logger.debug(f"Job {job_id}: Subscribed to Redis pub/sub channel")
        
        # Listen for new events
        last_status_check = time.time()
        while True:
            try:
                # Check for messages from client (ping/pong) - non-blocking
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=0.05)
                    # Handle ping/pong if needed
                    if data == "ping":
                        await websocket.send_text("pong")
                except asyncio.TimeoutError:
                    pass
                except WebSocketDisconnect:
                    raise
                
                # Check Redis for new events (non-blocking)
                message = pubsub.get_message(ignore_subscribe_messages=True)
                if message:
                    try:
                        event_data = json.loads(message["data"])
                        logger.debug(f"Job {job_id}: Received event from Redis: {event_data.get('agent_name')} - {event_data.get('status')}")
                        
                        # Send to this WebSocket connection
                        await websocket_manager.send_personal_message(event_data, websocket)
                        
                        # Extract status and agent_name values (should be strings after model_dump(mode='json'))
                        status_value = event_data.get("status", "")
                        agent_name_value = event_data.get("agent_name", "")
                        
                        # Update metrics
                        websocket_events_sent_total.labels(event_type=str(status_value)).inc()
                        
                        # Check if job is completed or failed (system agent)
                        if status_value in [AgentEventStatusEnum.COMPLETED.value, AgentEventStatusEnum.FAILED.value, "completed", "failed"]:
                            if agent_name_value == "system" or agent_name_value == AgentNameEnum.SYSTEM.value:
                                logger.info(f"Job {job_id}: System agent completed/failed, closing WebSocket")
                                break
                    except (json.JSONDecodeError, KeyError, AttributeError) as e:
                        logger.warning(f"Error parsing Redis message: {e}", exc_info=True)
                        continue
                
                # Check job status periodically (every 2 seconds)
                current_time = time.time()
                if current_time - last_status_check >= 2.0:
                    last_status_check = current_time
                    current_job = redis_service.get_job(job_id)
                    if current_job and current_job.status in [JobStatusEnum.COMPLETED, JobStatusEnum.FAILED]:
                        # Send final status
                        await websocket_manager.send_personal_message(
                            {'type': 'job_complete', 'status': current_job.status.value, 'job_id': job_id},
                            websocket
                        )
                        break
                
                # Small delay to avoid busy waiting
                await asyncio.sleep(0.05)
                
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for job: {job_id}")
                break
            except Exception as e:
                logger.error(f"Error in WebSocket loop for job {job_id}: {e}", exc_info=True)
                await websocket_manager.send_personal_message(
                    {'type': 'error', 'message': str(e)},
                    websocket
                )
                break
        
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected for job: {job_id}")
    except Exception as e:
        logger.error(f"WebSocket error for job {job_id}: {e}", exc_info=True)
    finally:
        websocket_manager.disconnect(websocket, job_id)
        pubsub.close()
        websocket_connections_total.labels(status="closed").inc()
        
        # Record connection duration
        duration = time.time() - stream_start_time
        websocket_connection_duration_seconds.observe(duration)
        
        logger.info(f"WebSocket closed for job: {job_id} (duration: {duration:.2f}s)")


@router.get(
    "/{job_id}/status",
    response_model=JobStatus,
    summary="Get job status",
    description="Get the current status of a job.",
)
async def get_job_status(job_id: str) -> JobStatus:
    """
    Get job status.
    
    Args:
        job_id: Job identifier
        
    Returns:
        JobStatus with current job information
    """
    start_time = time.time()
    logger.debug(f"Status requested for job: {job_id}")
    try:
        job = redis_service.get_job(job_id)
        if not job:
            logger.warning(f"Status requested for non-existent job: {job_id}")
            api_requests_total.labels(method="GET", endpoint="/api/v1/jobs/{job_id}/status", status_code=404).inc()
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        logger.debug(f"Job {job_id} status: {job.status.value}")
        
        # Record API metrics
        duration = time.time() - start_time
        api_request_duration_seconds.labels(method="GET", endpoint="/api/v1/jobs/{job_id}/status").observe(duration)
        api_requests_total.labels(method="GET", endpoint="/api/v1/jobs/{job_id}/status", status_code=200).inc()
        
        return job
    except HTTPException:
        raise
    except Exception as e:
        api_requests_total.labels(method="GET", endpoint="/api/v1/jobs/{job_id}/status", status_code=500).inc()
        raise


@router.get(
    "/{job_id}/events",
    response_model=JobEventsResponse,
    summary="Get job events",
    description="Retrieve all events for a specific job.",
)
async def get_job_events(job_id: str, limit: int = 100) -> JobEventsResponse:
    """
    Get all events for a job.
    
    Args:
        job_id: Job identifier
        limit: Maximum number of events to return (default: 100)
        
    Returns:
        JobEventsResponse with list of events
    """
    start_time = time.time()
    logger.debug(f"Events requested for job: {job_id} (limit: {limit})")
    try:
        job = redis_service.get_job(job_id)
        if not job:
            logger.warning(f"Events requested for non-existent job: {job_id}")
            api_requests_total.labels(method="GET", endpoint="/api/v1/jobs/{job_id}/events", status_code=404).inc()
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        
        events = redis_service.get_events(job_id, limit=limit)
        logger.debug(f"Job {job_id}: Returning {len(events)} events")
        
        # Record API metrics
        duration = time.time() - start_time
        api_request_duration_seconds.labels(method="GET", endpoint="/api/v1/jobs/{job_id}/events").observe(duration)
        api_requests_total.labels(method="GET", endpoint="/api/v1/jobs/{job_id}/events", status_code=200).inc()
        
        return JobEventsResponse(
            job_id=job_id,
            events=events,
            count=len(events),
        )
    except HTTPException:
        raise
    except Exception as e:
        api_requests_total.labels(method="GET", endpoint="/api/v1/jobs/{job_id}/events", status_code=500).inc()
        raise
