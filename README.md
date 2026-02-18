# 📧 Mail Formatter - AI Email Enhancement Service

A production-ready FastAPI application that leverages CrewAI's multi-agent workflow to automatically enhance email quality. Features real-time progress tracking, comprehensive monitoring, and a modern web interface.

## ✨ Key Features

### 🤖 AI-Powered Email Enhancement
- **Multi-Agent Workflow**: 5 specialized AI agents working in sequence
- **Tone & Style Adjustment**: Adapts email tone to match desired style
- **Grammar & Punctuation**: Professional proofreading and correction
- **Context-Aware**: Maintains original meaning while improving clarity

### 🚀 Performance & Reliability
- ⚡ **Real-time Updates**: Server-Sent Events (SSE) for live progress
- 🔄 **Asynchronous Processing**: Non-blocking job processing
- 🛡️ **Robust Error Handling**: Graceful degradation and recovery
- � **Containerized**: Easy deployment with Docker

### 📊 Monitoring & Observability
- � **Prometheus Metrics**: Comprehensive system and application metrics
- 📊 **Grafana Dashboards**: Pre-configured monitoring dashboards
- 🔍 **Structured Logging**: JSON-formatted logs with rotation
- �️ **Redis Monitoring**: Real-time Redis performance insights

### 🔄 Deployment Flexibility
- 🐳 **Docker Compose**: Single-command deployment
- 🔧 **Modular Architecture**: Mix of containerized and local services
- 🔄 **CI/CD Ready**: Easy integration with CI/CD pipelines
- 🌐 **Production-Grade**: Built for scalability and reliability

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

## 🚀 Quick Start

Get up and running with Mail Formatter in minutes. Choose between a fully containerized setup or a hybrid approach with local development.

### Prerequisites

#### For Mode 1 (Fully Dockerized)
- 🐳 Docker 20.10+
- 🐙 Docker Compose 2.0+
- 4GB+ free RAM

#### For Mode 2 (Development with Local Redis)
- 🐍 Python 3.11+
- 🐳 Docker (for Redis container)
- 🧰 Git
- 2GB+ free RAM

### 🛠️ Setup Instructions

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/mail-formatter.git
   cd mail-formatter
   ```

2. **Configure environment**
   ```bash
   # Copy example environment file
   cp .env.example .env
   
   # Edit configuration (update API keys and settings)
   nano .env  # or use your preferred editor
   ```
   
   > 💡 **Important**: Set `API_KEY` with your OpenAI API key and adjust other settings as needed.

3. **Choose your deployment mode**

   #### 🐳 Mode 1: Fully Dockerized (Recommended for Production)
   ```bash
   # Start all services (app, Redis, monitoring)
   docker compose -f deploy/compose/docker-compose.full.yml up -d
   
   # Verify containers are running
   docker ps
   ```

   #### 💻 Mode 2: Local Development with Redis in Docker
   ```bash
   # Start Redis and monitoring services
   docker compose -f deploy/compose/docker-compose.redis.yml up -d
   
   # Create and activate virtual environment (recommended)
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\activate
   
   # Install dependencies
   pip install -r requirements.txt
   
   # Start the application
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. **Verify Installation**
   - Open your browser and navigate to: http://localhost:8000
   - You should see the Mail Formatter interface
   - Check API documentation at: http://localhost:8000/docs
   - Verify health status: http://localhost:8000/api/v1/health

5. **Access Monitoring Tools** (if using Mode 1 or Redis monitoring)
   - Grafana: http://localhost:3000 (admin/admin)
   - Prometheus: http://localhost:9090
   - Redis Insight: http://localhost:8001

### 🧪 Running Your First Email

1. Open the web interface at http://localhost:8000
2. Paste your email text in the input box
3. Click "Improve Email"
4. Watch the real-time progress as the AI agents enhance your email
5. View the improved version with highlighted changes

### 🚦 Troubleshooting

- **Port conflicts**: Ensure ports 8000, 3000, 9090, 8001, and 9121 are available
- **Docker issues**: Try `docker system prune` to clean up unused containers and images
- **API errors**: Verify your `API_KEY` in `.env` and ensure it has sufficient credits
- **Logs**: Check container logs with `docker compose -f <compose-file> logs -f`
- **Redis connection**: Ensure Redis is running and accessible at the configured host/port

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

## 🏗️ Project Structure

Here's a detailed breakdown of the project's directory structure and key components:

```
mail-formatter/
├── app/                           # Main application package
│   ├── config/                   # Configuration files
│   ├── core/                     # Core application components
│   ├── models/                   # Data models and schemas
│   ├── routers/                  # FastAPI route handlers
│   └── services/                 # Business logic
│
├── deploy/                       # Deployment configurations
│   ├── compose/                  # Docker Compose files
│   │   ├── docker-compose.full.yml    # Full stack with monitoring
│   │   ├── docker-compose.redis.yml   # Redis-only setup
│   │   └── docker-compose.yml         # Base compose file
│   └── prometheus/               # Monitoring configuration
│       └── prometheus.yml        # Prometheus server config
│
├── frontend/                     # Web interface
│   └── templates/                # HTML templates and static files
│
├── grafana/                      # Monitoring dashboards
│   └── provisioning/            # Auto-configuration
│
└── logs/                         # Application logs (auto-created)

# Root level files
├── .env.example                 # Example environment variables
├── .gitignore                   # Git ignore rules
├── docker-compose.yml           # Main Docker Compose file
└── requirements.txt             # Python dependencies
```

### Key Directories

#### Application (`/app`)
- **`config/`**: YAML configurations for agents, tasks, and LLMs
- **`core/`**: Core application setup (config, logging, metrics)
- **`models/`**: Pydantic models and data schemas
- **`routers/`**: API route handlers
- **`services/`**: Business logic and agent implementations

#### Deployment (`/deploy`)
- **`compose/`**: Docker Compose configurations for different environments
- **`prometheus/`**: Monitoring and metrics configuration

#### Frontend (`/frontend`)
- **`templates/`**: HTML templates and static assets

#### Monitoring (`/grafana`)
- **`provisioning/`**: Auto-configuration for Grafana dashboards and data sources

### Key Files

- **`docker-compose.yml`**: Main Docker Compose configuration
- **`.env.example`**: Template for environment variables
- **`requirements.txt`**: Python dependencies
- **`main.py`**: FastAPI application entry point

### Key Components

#### 1. Application Core (`app/core/`)
- **config.py**: Centralized configuration management
- **logging.py**: Structured logging setup with file rotation
- **metrics.py**: Prometheus metrics configuration

#### 2. Agent System (`app/services/agents/`)
- Email enhancement workflow implementation
- Agent coordination and task management
- Error handling and retry logic

#### 3. API Layer (`app/routers/`)
- RESTful endpoints for job management
- WebSocket support for real-time updates
- Health checks and system status

#### 4. Data Models (`app/models/`)
- Request/response schemas
- Database models (if applicable)
- Enumerations and constants

#### 5. Monitoring & Observability
- **Grafana**: Pre-configured dashboards
- **Prometheus**: Metrics collection
- **Redis Insight**: Database monitoring

#### 6. Infrastructure
- **Docker Compose**: Multi-container orchestration
- **Nginx**: Reverse proxy and static file serving
- **Redis**: Job queue and caching
