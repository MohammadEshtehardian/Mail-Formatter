"""
Enums for better code readability and type safety.
"""

from enum import Enum


class JobStatusEnum(str, Enum):
    """Job status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentEventStatusEnum(str, Enum):
    """Agent event status enumeration."""
    STARTED = "started"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentNameEnum(str, Enum):
    """Agent name enumeration."""
    EMAIL_PLANNER = "email_planner"
    TONE_SPECIALIST = "tone_specialist"
    GRAMMAR_SPECIALIST = "grammar_specialist"
    DICTATION_SPECIALIST = "dictation_specialist"
    RESPONSE_FORMATTER = "response_formatter"
    SYSTEM = "system"


class AgentRoleEnum(str, Enum):
    """Agent role enumeration."""
    EMAIL_STRATEGY_PLANNER = "Email Strategy Planner"
    TONE_AND_STYLE_SPECIALIST = "Tone and Style Specialist"
    GRAMMAR_AND_SYNTAX_EXPERT = "Grammar and Syntax Expert"
    SPELLING_AND_WORD_CHOICE_SPECIALIST = "Spelling and Word Choice Specialist"
    RESPONSE_FORMATTER_AND_ANALYSIS_SPECIALIST = "Response Formatter and Analysis Specialist"
    SYSTEM = "System"


class ToneEnum(str, Enum):
    """Email tone enumeration."""
    FORMAL = "formal"
    PROFESSIONAL = "professional"
    CASUAL = "casual"
    FRIENDLY = "friendly"
    POLITE = "polite"
    CONCISE = "concise"


class LanguageEnum(str, Enum):
    """Language enumeration."""
    ENGLISH = "en"
    PERSIAN = "fa"


class TranslationDirectionEnum(str, Enum):
    """Translation direction enumeration."""
    NONE = "none"
    EN_TO_FA = "en_to_fa"
    FA_TO_EN = "fa_to_en"


class AudienceEnum(str, Enum):
    """Audience type enumeration."""
    GENERAL = "general"
    PROFESSIONAL = "professional"
    ACADEMIC = "academic"
    CASUAL = "casual"
    BUSINESS = "business"
    TECHNICAL = "technical"
