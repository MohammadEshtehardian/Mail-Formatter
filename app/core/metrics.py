"""
Prometheus metrics configuration for the application.
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client.openmetrics.exposition import generate_latest as generate_latest_openmetrics

from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Job metrics
jobs_created_total = Counter(
    "mail_formatter_jobs_created_total",
    "Total number of email improvement jobs created",
    ["status"]
)

jobs_completed_total = Counter(
    "mail_formatter_jobs_completed_total",
    "Total number of jobs completed",
    ["status"]  # completed, failed
)

jobs_in_progress = Gauge(
    "mail_formatter_jobs_in_progress",
    "Number of jobs currently in progress"
)

job_duration_seconds = Histogram(
    "mail_formatter_job_duration_seconds",
    "Time spent processing jobs",
    ["agent_name"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)

# Agent metrics
agent_events_total = Counter(
    "mail_formatter_agent_events_total",
    "Total number of agent events",
    ["agent_name", "status"]
)

agent_progress = Gauge(
    "mail_formatter_agent_progress",
    "Current progress of agents",
    ["agent_name", "job_id"]
)

# Redis metrics
redis_operations_total = Counter(
    "mail_formatter_redis_operations_total",
    "Total number of Redis operations",
    ["operation"]  # create_job, update_status, add_event, publish_event, get_job, get_events
)

redis_operation_duration_seconds = Histogram(
    "mail_formatter_redis_operation_duration_seconds",
    "Time spent on Redis operations",
    ["operation"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

redis_connection_status = Gauge(
    "mail_formatter_redis_connection_status",
    "Redis connection status (1 = connected, 0 = disconnected)"
)

# API metrics
api_requests_total = Counter(
    "mail_formatter_api_requests_total",
    "Total number of API requests",
    ["method", "endpoint", "status_code"]
)

api_request_duration_seconds = Histogram(
    "mail_formatter_api_request_duration_seconds",
    "Time spent processing API requests",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# WebSocket metrics
websocket_connections_total = Counter(
    "mail_formatter_websocket_connections_total",
    "Total number of WebSocket connections",
    ["status"]  # opened, closed
)

websocket_events_sent_total = Counter(
    "mail_formatter_websocket_events_sent_total",
    "Total number of WebSocket events sent",
    ["event_type"]
)

websocket_connection_duration_seconds = Histogram(
    "mail_formatter_websocket_connection_duration_seconds",
    "Duration of WebSocket connections",
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0]
)

active_websocket_connections = Gauge(
    "mail_formatter_active_websocket_connections",
    "Number of active WebSocket connections"
)

# LLM metrics
llm_requests_total = Counter(
    "mail_formatter_llm_requests_total",
    "Total number of LLM API requests",
    ["model", "agent_name"]
)

llm_tokens_total = Counter(
    "mail_formatter_llm_tokens_total",
    "Total number of LLM tokens used",
    ["model", "agent_name", "type"]  # type: prompt, completion, total
)

llm_request_duration_seconds = Histogram(
    "mail_formatter_llm_request_duration_seconds",
    "Time spent on LLM API requests",
    ["model", "agent_name"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0]
)

llm_request_errors_total = Counter(
    "mail_formatter_llm_request_errors_total",
    "Total number of LLM API request errors",
    ["model", "agent_name", "error_type"]
)


def get_metrics():
    """
    Get Prometheus metrics in text format.
    
    Returns:
        bytes: Prometheus metrics in text format
    """
    # Prometheus client automatically exports all registered metrics
    # Metrics will appear with HELP and TYPE even if they haven't been used yet
    # Actual metric values will appear once they're used with real labels
    return generate_latest()


def get_metrics_openmetrics():
    """
    Get Prometheus metrics in OpenMetrics format.
    
    Returns:
        bytes: Prometheus metrics in OpenMetrics format
    """
    return generate_latest_openmetrics()
