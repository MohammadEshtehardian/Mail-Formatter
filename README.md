# Mail Formatter - AI Email Improvement Service

A FastAPI application that uses CrewAI multi-agent workflow to improve email tone, grammar, and overall quality with real-time progress tracking via WebSocket.

## Features

- 🤖 **Multi-Agent AI Workflow**: 5 specialized agents working sequentially
- 📊 **Real-time Progress**: SSE streaming for live updates
- 💾 **Redis Integration**: Job queue and event storage
- 🎨 **Modern Frontend**: Responsive web interface
- 🐳 **Docker Support**: Two deployment modes
- 📝 **Comprehensive Logging**: Structured logging with file rotation
- 📈 **Monitoring & Observability**: Prometheus metrics, Grafana dashboards, Redis monitoring

## Architecture

### Agents

1. **Email Planner**: Analyzes email and creates improvement plan
2. **Tone Specialist**: Adjusts tone and style
3. **Grammar Specialist**: Fixes grammar and punctuation
4. **Dictation Specialist**: Corrects spelling and word choice
5. **Response Formatter**: Formats output with suggestions and differences

## Deployment Modes

### Mode 1: Fully Dockerized (Recommended for Production)

All services run in Docker containers.

```bash
# Start all services
docker compose -f docker-compose.full.yml up -d

# View logs
docker compose -f docker-compose.full.yml logs -f app
docker compose -f docker-compose.full.yml logs -f redis

# Stop services
docker compose -f docker-compose.full.yml down
```

### Mode 2: Redis Only (Development Mode)

Only Redis runs in Docker, application runs on bare metal.

```bash
# Start Redis only
docker compose -f docker-compose.redis.yml up -d

# Update .env for local Redis
REDIS_HOST=localhost
REDIS_PORT=6389

# Run application locally
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Quick Start

### Prerequisites

- Docker and Docker Compose (for Mode 1)
- Python 3.11+ (for Mode 2)
- Redis (via Docker or local installation)

### Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd mail-formatter
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and settings
   ```

3. **Choose deployment mode:**

   **Mode 1 (Fully Dockerized):**
   ```bash
   docker compose -f docker-compose.full.yml up -d
   ```

   **Mode 2 (Redis Only):**
   ```bash
   docker compose -f docker-compose.redis.yml up -d
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Access the application:**
   - Frontend: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - Health Check: http://localhost:8000/api/v1/health
   - Metrics: http://localhost:8000/metrics/

5. **Access monitoring tools:**
   - Grafana Dashboard: http://localhost:3000 (admin/admin)
   - Prometheus: http://localhost:9090
   - Redis Insight: http://localhost:8001
   - Redis Exporter Metrics: http://localhost:9121/metrics

## Environment Variables

Create a `.env` file with the following variables:

```env
# Model Info
MODEL_NAME=gpt-4o
API_KEY=your-api-key
BASE_URL=https://localhost:10001/v1

# Redis Info
# Mode 1 (Docker): use 'redis' as host
# Mode 2 (Local): use 'localhost'
REDIS_HOST=redis
REDIS_PORT=6389
REDIS_PASSWORD=
REDIS_DB=0

# FastAPI Info
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000
FASTAPI_RELOAD=false
FASTAPI_DEBUG=false

# Logging Configuration
FASTAPI_LOG_LEVEL=INFO
FASTAPI_LOG_FORMAT=%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s
LOG_FILE_MAX_SIZE=10485760  # 10MB
LOG_FILE_BACKUP_COUNT=5

# Monitoring Configuration
REDIS_INSIGHT_PORT=8001
REDIS_EXPORTER_PORT=9121
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin
```

## API Endpoints

### Job Management

- **POST** `/api/v1/jobs/` - Create email improvement job
- **WebSocket** `/api/v1/jobs/{job_id}/ws` - WebSocket connection for real-time job updates
- **GET** `/api/v1/jobs/{job_id}/status` - Get job status
- **GET** `/api/v1/jobs/{job_id}/events` - Get job events

### Health

- **GET** `/api/v1/health` - Health check endpoint
- **GET** `/api/v1/health/redis` - Redis connectivity check

### Metrics

- **GET** `/metrics/` - Prometheus metrics endpoint

## Logging

The application uses structured logging with the following features:

- **Console Output**: All logs to stdout/stderr
- **File Logging**: Rotating log files in `logs/` directory
  - `app.log`: All logs
  - `error.log`: Errors and above only
- **Log Rotation**: 10MB max size, 5 backup files
- **Configurable**: Log level and format via `.env`

### Log Levels

- `DEBUG`: Detailed information for debugging
- `INFO`: General informational messages
- `WARNING`: Warning messages
- `ERROR`: Error messages
- `CRITICAL`: Critical errors

## Monitoring & Observability

The application includes comprehensive monitoring capabilities:

### Prometheus Metrics

- **Metrics Endpoint**: `http://localhost:8000/metrics/`
- **Metrics Exposed**:
  - Job metrics (created, completed, in progress, duration)
  - Agent metrics (events, progress)
  - LLM metrics (requests, tokens, duration, errors)
  - Redis metrics (operations, duration, connection status)
  - API metrics (requests, duration)
  - SSE metrics (connections, events, duration)

### Grafana Dashboard

- **URL**: `http://localhost:3000`
- **Default Credentials**: `admin` / `admin`
- **Dashboard**: Automatically provisioned at `/d/mail-formatter/mail-formatter-dashboard`
- **Panels Include**:
  - Job creation and completion rates
  - Job duration percentiles (p50, p95)
  - Agent event tracking
  - API request rates and latencies
  - LLM token usage and request metrics
  - Redis operation metrics
  - WebSocket connection statistics

### Redis Insight

- **URL**: `http://localhost:8001`
- **Purpose**: Visual Redis database browser and management tool
- **Features**: Browse keys, execute commands, monitor performance

### Prometheus

- **URL**: `http://localhost:9090`
- **Purpose**: Time-series database and query interface
- **Features**: Query metrics, create alerts, explore data

### Redis Exporter

- **Metrics URL**: `http://localhost:9121/metrics`
- **Purpose**: Exports Redis metrics for Prometheus scraping
- **Metrics**: Redis memory usage, connections, commands, keyspace info

## Docker Commands

### Mode 1 (Fully Dockerized)

```bash
# Build and start
docker compose -f docker-compose.full.yml up -d --build

# View logs
docker compose -f docker-compose.full.yml logs -f app
docker compose -f docker-compose.full.yml logs -f redis

# Stop
docker compose -f docker-compose.full.yml down

# Stop and remove volumes
docker compose -f docker-compose.full.yml down -v
```

### Mode 2 (Redis Only)

```bash
# Start Redis
docker compose -f docker-compose.redis.yml up -d

# View logs
docker compose -f docker-compose.redis.yml logs -f redis
docker compose -f docker-compose.redis.yml logs -f prometheus
docker compose -f docker-compose.redis.yml logs -f grafana

# Stop services
docker compose -f docker-compose.redis.yml down
```

## Project Structure

```
mail-formatter/
├── app/
│   ├── core/              # Core modules (logging, metrics)
│   ├── config/           # YAML configs (agents, tasks, llms)
│   ├── models/           # Pydantic models and enums
│   ├── routers/          # FastAPI routes (jobs, health, metrics)
│   ├── services/         # Business logic
│   └── main.py           # FastAPI app
├── frontend/             # Static frontend files
├── grafana/             # Grafana configuration
│   ├── provisioning/    # Auto-provisioning configs
│   │   ├── datasources/  # Prometheus datasource
│   │   └── dashboards/   # Dashboard provisioning
│   └── dashboards/       # Dashboard JSON files
├── logs/                 # Application logs (auto-created)
├── docker-compose.full.yml    # Mode 1: Fully dockerized
├── docker-compose.redis.yml   # Mode 2: Redis only
├── prometheus.yml        # Prometheus configuration
├── Dockerfile            # Docker image definition
└── requirements.txt      # Python dependencies
```

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black app/
ruff check app/
```

## License

MIT License
