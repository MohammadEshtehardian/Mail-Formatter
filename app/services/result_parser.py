"""
Result parser service for parsing crew execution results.
"""

import json

from app.core.logging_config import get_logger
from app.models.schemas import EmailResponse

logger = get_logger(__name__)


class ResultParser:
    """Service responsible for parsing crew execution results."""

    def __init__(self, job_id: str):
        self.job_id = job_id

    def parse_result(self, result) -> EmailResponse:
        """Parse crew execution result into EmailResponse."""
        # Try to get Pydantic model result first
        if hasattr(result, "pydantic") and result.pydantic:
            logger.debug(f"Job {self.job_id}: Returning Pydantic model result")
            return result.pydantic

        # Fallback parsing from raw result
        if hasattr(result, "raw"):
            try:
                logger.debug(f"Job {self.job_id}: Parsing raw result as JSON")
                data = json.loads(result.raw)
                return EmailResponse(**data)
            except (json.JSONDecodeError, Exception) as parse_error:
                logger.warning(f"Job {self.job_id}: Failed to parse raw result: {parse_error}")
                pass

        logger.error(f"Job {self.job_id}: Failed to parse structured response")
        raise ValueError("Failed to parse structured response")
