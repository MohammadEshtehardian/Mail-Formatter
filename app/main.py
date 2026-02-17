"""
FastAPI application entry point for the mail formatter service.
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.logging_config import get_logger, setup_logging
from app.routers import health_check, jobs, metrics

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Setup logging
setup_logging()
logger = get_logger(__name__)

logger.info("Starting Mail Formatter API...")
logger.info(f"Environment: {os.getenv('FASTAPI_ENV', 'development')}")
logger.info(f"Port: {os.getenv('FASTAPI_PORT', '8000')}")
logger.info(f"Log Level: {os.getenv('FASTAPI_LOG_LEVEL', 'INFO')}")

app = FastAPI(
    title="Mail Formatter API",
    description="AI-powered email improvement service using CrewAI multi-agent workflow with WebSocket streaming",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("Configuring CORS middleware")

# Include routers (must be before static files)
app.include_router(jobs.router)
app.include_router(health_check.router)
app.include_router(metrics.router)
logger.info("Registered routers: jobs, health_check, metrics")

# Serve static files (frontend) - must be last to not override API routes
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
    logger.info(f"Serving frontend from: {frontend_path}")
else:
    logger.warning("Frontend directory not found, skipping static file serving")


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    logger.info("Application startup complete")
    logger.info("API Documentation available at: /docs")
    
    # Check Redis connection (non-blocking, just log)
    try:
        from app.services.redis_service import RedisService
        redis_service = RedisService()
        redis_service.redis_client.ping()
        logger.info("Redis connection verified at startup")
    except Exception as e:
        logger.warning(f"Redis not available at startup: {e}")
        logger.warning("Application will start but Redis-dependent features may not work")
        logger.warning("Make sure Redis is running and REDIS_HOST is correct in .env")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    logger.info("Application shutdown initiated")


@app.get("/")
async def root():
    """Root endpoint."""
    logger.debug("Root endpoint accessed")
    return {
        "message": "Mail Formatter API",
        "version": "1.0.0",
        "docs": "/docs",
    }
