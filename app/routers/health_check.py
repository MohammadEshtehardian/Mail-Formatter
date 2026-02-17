"""
FastAPI router for health check endpoints.
"""

from fastapi import APIRouter, HTTPException

from app.core.logging_config import get_logger
from app.services.redis_service import RedisService

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["health"],
)

redis_service = RedisService()


@router.get(
    "/health",
    summary="Health check endpoint",
    description="Check if the mail formatter service is running.",
)
async def health_check():
    """Health check endpoint."""
    logger.debug("Health check endpoint accessed")
    
    # Check Redis connectivity
    redis_status = "unknown"
    try:
        redis_service.redis_client.ping()
        redis_status = "connected"
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
        redis_status = "disconnected"
    
    return {
        "status": "healthy",
        "service": "mail-formatter",
        "redis": redis_status,
    }


@router.get(
    "/health/redis",
    summary="Redis health check",
    description="Check Redis connectivity status.",
)
async def redis_health_check():
    """Redis health check endpoint."""
    try:
        redis_service.redis_client.ping()
        return {
            "status": "healthy",
            "service": "redis",
            "connected": True,
        }
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Redis connection failed: {str(e)}"
        )
