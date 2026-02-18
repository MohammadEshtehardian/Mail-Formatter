"""
Translation instruction builder service.
"""

from app.core.logging_config import get_logger
from app.models.enums import TranslationDirectionEnum

logger = get_logger(__name__)


class TranslationInstructionBuilder:
    """Service responsible for building translation instructions."""

    @staticmethod
    def build_instructions(translation: TranslationDirectionEnum | str) -> dict[str, str]:
        """Build translation instructions based on translation direction."""
        # Normalize to enum if string is passed
        if isinstance(translation, str):
            translation = TranslationDirectionEnum(translation)
        
        translation_instruction = ""
        output_language_requirement = "Same language as original."
        format_translation_instruction = ""

        if translation == TranslationDirectionEnum.EN_TO_FA:
            translation_instruction = f"""
{'='*80}
CRITICAL TRANSLATION REQUIREMENT - THIS OVERRIDES ALL OTHER INSTRUCTIONS
{'='*80}

YOU MUST TRANSLATE THE ENTIRE EMAIL FROM ENGLISH TO PERSIAN (فارسی).

REQUIREMENTS:
- The output email MUST be completely in Persian (فارسی).
- Translate ALL content: subject line, body text, greetings, closings, everything.
- Maintain the same meaning, tone, and structure as the original.
- Use proper Persian grammar, vocabulary, and script.
- This translation requirement OVERRIDES any instruction about "same language" or "preserving language".

IMPORTANT: If the task description mentions "same language as original" or similar, IGNORE IT.
You MUST translate to Persian.

{'='*80}

"""
            output_language_requirement = "The output email MUST be in Persian (فارسی)."
            format_translation_instruction = "\n\nIMPORTANT: The improved email from context should already be in Persian (فارسی). Extract and format it as-is. All suggestions and differences must be in Persian."

        elif translation == TranslationDirectionEnum.FA_TO_EN:
            translation_instruction = f"""
{'='*80}
CRITICAL TRANSLATION REQUIREMENT - THIS OVERRIDES ALL OTHER INSTRUCTIONS
{'='*80}

YOU MUST TRANSLATE THE ENTIRE EMAIL FROM PERSIAN (فارسی) TO ENGLISH.

REQUIREMENTS:
- The output email MUST be completely in English.
- Translate ALL content: subject line, body text, greetings, closings, everything.
- Maintain the same meaning, tone, and structure as the original.
- Use proper English grammar and vocabulary.
- This translation requirement OVERRIDES any instruction about "same language" or "preserving language".

IMPORTANT: If the task description mentions "same language as original" or similar, IGNORE IT.
You MUST translate to English.

{'='*80}

"""
            output_language_requirement = "The output email MUST be in English."
            format_translation_instruction = "\n\nIMPORTANT: The improved email from context should already be in English. Extract and format it as-is. All suggestions and differences must be in English."

        return {
            "translation_instruction": translation_instruction,
            "output_language_requirement": output_language_requirement,
            "format_translation_instruction": format_translation_instruction,
        }
