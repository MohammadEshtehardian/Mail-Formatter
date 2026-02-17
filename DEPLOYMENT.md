# Deployment Guide

## Two Deployment Modes

This application supports two deployment modes to suit different environments.

### Mode 1: Fully Dockerized (Production)

**Best for:** Production deployments, consistent environments, easy scaling

**Services:**
- FastAPI Application (Docker container)
- Redis (Docker container)

**Usage:**
```bash
# Start all services
docker compose -f docker-compose.full.yml up -d

# Check status
docker compose -f docker-compose.full.yml ps

# View logs
docker compose -f docker-compose.full.yml logs -f app
docker compose -f docker-compose.full.yml logs -f redis

# Stop services
docker compose -f docker-compose.full.yml down
```

**Configuration:**
- Application port: Read from `.env` `FASTAPI_PORT` (default: 8000)
- Redis port: Read from `.env` `REDIS_PORT` (default: 6389)
- Redis host: `redis` (Docker service name)

### Mode 2: Redis Only (Development)

**Best for:** Local development, debugging, testing

**Services:**
- FastAPI Application (runs on host machine)
- Redis (Docker container)

**Usage:**
```bash
# Start Redis only
docker compose -f docker-compose.redis.yml up -d

# Update .env for local connection
REDIS_HOST=localhost
REDIS_PORT=6389

# Run application locally
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Or with custom port from .env
uvicorn app.main:app --host 0.0.0.0 --port ${FASTAPI_PORT:-8000} --reload
```

**Configuration:**
- Application port: From `.env` `FASTAPI_PORT` or command line
- Redis port: Read from `.env` `REDIS_PORT` (default: 6389)
- Redis host: `localhost` (for local development)

## Port Configuration

The Dockerfile reads the port from environment variables:

1. **Build time:** `ARG FASTAPI_PORT=8000` (default)
2. **Runtime:** `ENV FASTAPI_PORT=${FASTAPI_PORT}` (from build arg or .env)
3. **CMD:** Uses `${FASTAPI_PORT:-8000}` (environment variable with fallback)

To use a custom port:

```bash
# In .env
FASTAPI_PORT=9000

# Build with custom port
docker build --build-arg FASTAPI_PORT=9000 -t mail-formatter .

# Or let docker compose read from .env
docker compose -f docker-compose.full.yml up -d
```

## Logging

### Log Files Location

- **Mode 1 (Docker):** Logs are inside the container at `/app/logs/`
  - View logs: `docker compose logs -f app`
  - Access files: Mount volume or exec into container
  
- **Mode 2 (Local):** Logs are in `./logs/` directory
  - `logs/app.log`: All application logs
  - `logs/error.log`: Errors only

### Log Configuration

Configure logging via `.env`:

```env
FASTAPI_LOG_LEVEL=INFO          # DEBUG, INFO, WARNING, ERROR, CRITICAL
FASTAPI_LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s
LOG_FILE_MAX_SIZE=10485760      # 10MB
LOG_FILE_BACKUP_COUNT=5
```

### Viewing Logs

**Mode 1 (Docker):**
```bash
# Real-time logs
docker compose -f docker-compose.full.yml logs -f app

# Last 100 lines
docker compose -f docker-compose.full.yml logs --tail=100 app

# Logs from specific time
docker compose -f docker-compose.full.yml logs --since 30m app
```

**Mode 2 (Local):**
```bash
# View logs
tail -f logs/app.log
tail -f logs/error.log

# Search logs
grep "ERROR" logs/app.log
grep "Job" logs/app.log
```

## Health Checks

Both modes include health checks:

- **Application:** `GET /api/v1/health`
- **Redis:** `redis-cli ping` (in Docker)

## Troubleshooting

### Port Already in Use

```bash
# Check what's using the port
lsof -i :8000  # Linux/Mac
netstat -ano | findstr :8000  # Windows

# Change port in .env
FASTAPI_PORT=8001
```

### Redis Connection Issues

**Mode 1:**
- Ensure Redis container is healthy: `docker compose ps`
- Check Redis logs: `docker compose logs redis`
- Verify network: Containers should be on same network

**Mode 2:**
- Verify Redis is running: `docker ps | grep redis`
- Check Redis port: `docker compose -f docker-compose.redis.yml ps`
- Test connection: `redis-cli -h localhost -p 6389 ping`

### Logging Issues

- Ensure `logs/` directory exists (created automatically)
- Check file permissions
- Verify log level in `.env` is appropriate
