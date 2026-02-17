from pydantic import BaseModel, Field

from app.models.enums import (
    AgentEventStatusEnum,
    AgentNameEnum,
    AgentRoleEnum,
    JobStatusEnum,
    ToneEnum,
    LanguageEnum,
    TranslationDirectionEnum,
    AudienceEnum,
)


class Email(BaseModel):
    """Request model for email improvement."""
    subject: str = Field(
        ...,
        description="The raw email text to improve. Can include subject and body.",
        min_length=1,
        max_length=10000,
    )
    body: str = Field(
        ...,
        description="The body of the email.",
        min_length=1,
        max_length=10000,
    )


class EmailResponse(BaseModel):
    """Response model for email improvement."""
    email: Email = Field(
        ...,
        description="The email object with the improved subject and body.",
    )
    suggestions: list[str] = Field(
        ...,
        description="The suggestions for future improvements.",
    )
    differences: list[str] = Field(
        ...,
        description="The differences between the original and improved email.",
    )


class JobStatus(BaseModel):
    """Job status model."""
    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatusEnum = Field(..., description="Job status")
    created_at: str = Field(..., description="Job creation timestamp")
    completed_at: str | None = Field(None, description="Job completion timestamp")
    result: EmailResponse | None = Field(None, description="Job result if completed")
    error: str | None = Field(None, description="Error message if failed")


class AgentEvent(BaseModel):
    """Agent progress event model."""
    job_id: str = Field(..., description="Job identifier")
    agent_name: AgentNameEnum = Field(..., description="Name of the agent")
    agent_role: AgentRoleEnum = Field(..., description="Role of the agent")
    status: AgentEventStatusEnum = Field(..., description="Event status")
    progress: float = Field(..., description="Progress percentage (0-100)")
    message: str = Field(..., description="Event message")
    timestamp: str = Field(..., description="Event timestamp")
    output: str | None = Field(None, description="Agent output if completed")
    thinking: str | None = Field(None, description="Agent thinking/reasoning process")


class JobRequest(BaseModel):
    """Request model for creating an async job."""
    email: Email = Field(..., description="Email to improve")
    tone: ToneEnum = Field(default=ToneEnum.PROFESSIONAL, description="Desired tone for the output")
    translation: TranslationDirectionEnum = Field(default=TranslationDirectionEnum.NONE, description="Translation direction")
    audience: AudienceEnum = Field(default=AudienceEnum.GENERAL, description="Target audience type")
    language: LanguageEnum = Field(default=LanguageEnum.ENGLISH, description="UI language preference")


class JobResponse(BaseModel):
    """Response model for job creation."""
    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatusEnum = Field(..., description="Job status")
    message: str = Field(..., description="Response message")
    stream_url: str = Field(..., description="WebSocket URL to connect for real-time updates")


class JobEventsResponse(BaseModel):
    """Response model for job events list."""
    job_id: str = Field(..., description="Job identifier")
    events: list[AgentEvent] = Field(..., description="List of agent events")
    count: int = Field(..., description="Total number of events")
