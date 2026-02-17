"""
FastAPI router for Prometheus metrics endpoint.
"""

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST

from app.core.logging_config import get_logger
from app.core.metrics import get_metrics

logger = get_logger(__name__)

router = APIRouter(
    prefix="/metrics",
    tags=["metrics"],
)


@router.get(
    "/",
    summary="Prometheus metrics endpoint",
    description="Returns Prometheus metrics in text format for scraping.",
    response_class=Response,
)
async def metrics():
    """
    Prometheus metrics endpoint.
    Returns metrics in Prometheus text format.
    """
    logger.debug("Metrics endpoint accessed")
    return Response(content=get_metrics(), media_type=CONTENT_TYPE_LATEST)
