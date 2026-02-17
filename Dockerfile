# Use Python 3.11 slim image
FROM docker.arvancloud.ir/python:3.11-slim

# Set working directory
WORKDIR /app

# Accept build argument for port
ARG FASTAPI_PORT=8000

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FASTAPI_PORT=${FASTAPI_PORT}

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port (default 8000, can be overridden via build arg)
EXPOSE 8000

# Health check (use environment variable)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import os, urllib.request; port=os.getenv('FASTAPI_PORT', '8000'); urllib.request.urlopen(f'http://localhost:{port}/api/v1/health')" || exit 1

# Run the application (use environment variable)
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${FASTAPI_PORT:-8000}"
