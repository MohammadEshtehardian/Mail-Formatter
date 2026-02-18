"""
LLM provider service for creating and managing LLM instances.
"""

import os

from crewai import LLM

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class LLMProvider:
    """Service responsible for providing LLM instances."""

    @staticmethod
    def create_llm() -> LLM:
        """Build LLM from .env environment variables."""
        logger.info("Initializing LLM configuration from environment variables")

        # Required parameters
        model = os.getenv("MODEL_NAME", "gpt-4")
        api_key = os.getenv("API_KEY", "")
        base_url = os.getenv("BASE_URL")

        # Optional parameters with defaults
        temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))
        max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))
        timeout = int(os.getenv("LLM_TIMEOUT", "60"))

        # Ensure BASE_URL ends with /v1 for OpenAI-compatible APIs if not empty
        if base_url and not base_url.endswith("/v1") and not base_url.endswith("/v1/"):
            base_url = base_url.rstrip("/") + "/v1"
            logger.warning(f"BASE_URL adjusted to include /v1: {base_url}")

        logger.info(f"LLM Model: {model}")
        logger.info(f"LLM Base URL: {base_url or 'default (OpenAI)'}")
        logger.info(f"LLM API Key: {'*' * 10 if api_key else 'NOT SET'}")
        logger.info(f"LLM Temperature: {temperature}")
        logger.info(f"LLM Max Tokens: {max_tokens}")
        logger.info(f"LLM Timeout: {timeout}s")

        if not api_key:
            logger.warning("API_KEY is not set! LLM calls will fail.")

        if not base_url:
            logger.warning("BASE_URL is not set! Using default OpenAI endpoint.")

        llm_instance = LLM(
            model=model,
            api_key=api_key,
            base_url=base_url or None,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )

        # Store model name on LLM instance for metrics tracking
        llm_instance._model_name = model

        return llm_instance
