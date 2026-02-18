"""
Reasoning extractor service for extracting reasoning/thinking from agent outputs.
"""

import re

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class ReasoningExtractor:
    """Service responsible for extracting reasoning/thinking from various output formats."""

    def __init__(self, job_id: str):
        self.job_id = job_id

    def extract_from_step_output(self, step_output) -> str | None:
        """Extract reasoning from step output."""
        if step_output is None:
            return None

        thinking = None

        if hasattr(step_output, 'output'):
            thought_value = getattr(step_output, 'output')
            if thought_value and str(thought_value).strip() and str(thought_value).strip().lower() != 'none':
                thinking = str(thought_value)
                logger.debug(f"Job {self.job_id}: Found reasoning in step_output.output: {thinking[:100]}...")

        return thinking

    def extract_from_task_output(self, task_output, output_text: str | None = None) -> str | None:
        """Extract reasoning from task output using comprehensive methods."""
        if task_output is None:
            return None

        thinking = None
        logger.debug(f"Job {self.job_id}: Extracting reasoning from task_output type: {type(task_output)}")

        # Method 1: Check for 'thought' attribute first (CrewAI AgentFinish objects)
        if hasattr(task_output, 'thought'):
            thought_value = getattr(task_output, 'thought')
            if thought_value and str(thought_value).strip() and str(thought_value).strip().lower() != 'none':
                thinking = str(thought_value)
                logger.debug(f"Job {self.job_id}: Found reasoning in task_output.thought")
                return thinking

        # Method 2: Try multiple ways to extract reasoning/thinking
        for attr in ['reasoning', 'thinking', 'reasoning_text', 'thoughts', 'plan', 'reasoning_plan']:
            if hasattr(task_output, attr):
                value = getattr(task_output, attr)
                if value and str(value).strip():
                    thinking = str(value)
                    logger.debug(f"Job {self.job_id}: Found reasoning in task_output.{attr}")
                    return thinking

        # Method 3: Dictionary access
        if isinstance(task_output, dict):
            # Check 'thought' first (CrewAI AgentFinish)
            if 'thought' in task_output and task_output['thought']:
                thought_value = task_output['thought']
                if str(thought_value).strip().lower() != 'none':
                    thinking = str(thought_value)
                    logger.debug(f"Job {self.job_id}: Found reasoning in task_output['thought']")
                    return thinking

            # Then check other keys
            for key in ['reasoning', 'thinking', 'reasoning_text', 'thoughts', 'plan', 'reasoning_plan']:
                if key in task_output and task_output[key]:
                    thinking = str(task_output[key])
                    logger.debug(f"Job {self.job_id}: Found reasoning in task_output['{key}']")
                    return thinking

        # Method 4: Check raw output for reasoning markers
        if not thinking and output_text:
            thinking = self._extract_from_text(output_text)

        if thinking:
            logger.debug(f"Job {self.job_id}: Extracted thinking: {thinking[:100]}...")
        else:
            logger.debug(f"Job {self.job_id}: No thinking found in task_output")

        return thinking

    def extract_from_crew_result(self, result) -> dict[str, str]:
        """Extract reasoning from crew execution result for all tasks."""
        reasoning_by_agent = {}

        try:
            if hasattr(result, 'tasks') and result.tasks:
                for task_result in result.tasks:
                    task_output = self._get_task_output(task_result)
                    agent_role = self._get_agent_role(task_result)

                    if task_output and agent_role:
                        reasoning_text = self._extract_from_task_result(task_output)
                        if reasoning_text:
                            reasoning_by_agent[agent_role] = reasoning_text
                            logger.debug(f"Job {self.job_id}: Found reasoning in task result for {agent_role}: {reasoning_text[:100]}...")

        except Exception as e:
            logger.warning(f"Job {self.job_id}: Error extracting reasoning from crew result: {e}", exc_info=True)

        return reasoning_by_agent

    def _extract_from_text(self, text: str) -> str | None:
        """Extract reasoning from text using markers."""
        reasoning_markers = [
            'reasoning:', 'thinking:', 'plan:', 'analysis:',
            'understanding:', 'key steps', 'reasoning plan',
            'execution plan', 'approach:'
        ]

        for marker in reasoning_markers:
            if marker.lower() in text.lower():
                # Use regex to extract reasoning section
                pattern = rf'{re.escape(marker)}\s*(.*?)(?=\n\n|\n---|\n##|\n#|\nTask:|\nExecution:|\nOutput:|$)'
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    return match.group(1).strip()
                else:
                    # Fallback: split and extract
                    parts = text.split(marker, 1)
                    if len(parts) > 1:
                        reasoning_section = parts[1]
                        end_markers = ['\n\n', '\n---', '\n##', '\n#', '\nTask:', '\nExecution:', '\nOutput:']
                        for end_marker in end_markers:
                            if end_marker in reasoning_section:
                                return reasoning_section.split(end_marker)[0].strip()
                        return reasoning_section.strip()

        return None

    def _get_task_output(self, task_result) -> str | dict | None:
        """Get task output from task result."""
        if hasattr(task_result, 'output'):
            return task_result.output
        elif hasattr(task_result, 'raw'):
            return task_result.raw
        elif hasattr(task_result, 'result'):
            return task_result.result
        return None

    def _get_agent_role(self, task_result) -> str | None:
        """Get agent role from task result."""
        if hasattr(task_result, 'agent'):
            agent_obj = task_result.agent
            if hasattr(agent_obj, 'role'):
                return agent_obj.role
        elif hasattr(task_result, 'agent_role'):
            return task_result.agent_role
        elif isinstance(task_result, dict) and 'agent' in task_result:
            agent_info = task_result['agent']
            if isinstance(agent_info, dict) and 'role' in agent_info:
                return agent_info['role']
        return None

    def _extract_from_task_result(self, task_output) -> str | None:
        """Extract reasoning from task result output."""
        # Method 1: Check for 'thought' attribute
        if hasattr(task_output, 'thought'):
            thought_value = getattr(task_output, 'thought')
            if thought_value and str(thought_value).strip() and str(thought_value).strip().lower() != 'none':
                return str(thought_value)

        # Method 2: Check dictionary for 'thought'
        if isinstance(task_output, dict):
            if 'thought' in task_output and task_output['thought']:
                thought_value = task_output['thought']
                if str(thought_value).strip().lower() != 'none':
                    return str(thought_value)

        # Method 3: Check other reasoning attributes
        if hasattr(task_output, 'reasoning'):
            return str(task_output.reasoning)
        elif isinstance(task_output, dict) and 'reasoning' in task_output:
            return str(task_output['reasoning'])

        # Method 4: Look for reasoning patterns in string output
        if isinstance(task_output, str):
            return self._extract_from_text(task_output)

        return None
