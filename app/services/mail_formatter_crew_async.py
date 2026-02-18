"""
Async mail formatter crew with event callbacks for WebSocket streaming.
"""

import asyncio
from datetime import datetime, timezone

from crewai import Crew, Process

from app.core.logging_config import get_logger
from app.core.metrics import (
    jobs_completed_total,
    jobs_in_progress,
    llm_request_errors_total,
)
from app.models.enums import (
    AgentEventStatusEnum,
    AgentNameEnum,
    AgentRoleEnum,
    AudienceEnum,
    JobStatusEnum,
    LanguageEnum,
    ToneEnum,
    TranslationDirectionEnum,
)
from app.models.schemas import AgentEvent, EmailResponse
from app.services.agent_factory import AgentFactory
from app.services.crew_executor import CrewExecutor
from app.services.event_emitter import EventEmitterService
from app.services.llm_provider import LLMProvider
from app.services.llm_tracker import LLMTrackerService
from app.services.progress_tracker import ProgressTrackerService
from app.services.reasoning_extractor import ReasoningExtractor
from app.services.redis_service import RedisService
from app.services.result_parser import ResultParser
from app.services.task_factory import TaskFactory
from app.services.translation_instruction_builder import TranslationInstructionBuilder

logger = get_logger(__name__)


class AsyncMailFormatterCrew:
    """Crew orchestrator with event callbacks for WebSocket streaming."""

    def __init__(
        self, 
        job_id: str, 
        redis_service: RedisService,
        tone: ToneEnum | str = ToneEnum.PROFESSIONAL,
        translation: TranslationDirectionEnum | str = TranslationDirectionEnum.NONE,
        audience: AudienceEnum | str = AudienceEnum.GENERAL,
        language: LanguageEnum | str = LanguageEnum.ENGLISH,
    ):
        self.job_id = job_id
        # Normalize to enums if strings are passed (for backward compatibility)
        self.tone = tone if isinstance(tone, ToneEnum) else ToneEnum(tone)
        self.translation = translation if isinstance(translation, TranslationDirectionEnum) else TranslationDirectionEnum(translation)
        self.audience = audience if isinstance(audience, AudienceEnum) else AudienceEnum(audience)
        self.language = language if isinstance(language, LanguageEnum) else LanguageEnum(language)
        
        logger.info(
            f"Initializing AsyncMailFormatterCrew for job: {job_id} "
            f"(tone={self.tone.value}, translation={self.translation.value}, audience={self.audience.value}, language={self.language.value})"
        )
        
        # Initialize services (dependency injection)
        self._llm = LLMProvider.create_llm()
        self.event_emitter = EventEmitterService(job_id, redis_service)
        self.progress_tracker = ProgressTrackerService(job_id)
        self.llm_tracker = LLMTrackerService(job_id)
        self.reasoning_extractor = ReasoningExtractor(job_id)
        self.result_parser = ResultParser(job_id)
        
        # Register LLM hooks for tracking
        self.llm_tracker.register_hooks()
        
        # Initialize factories
        self.agent_factory = AgentFactory(
            job_id=job_id,
            llm=self._llm,
            event_emitter=self.event_emitter,
            progress_tracker=self.progress_tracker,
            reasoning_extractor=self.reasoning_extractor,
            language=language,
        )
        
        self.task_factory = TaskFactory(
            job_id=job_id,
            event_emitter=self.event_emitter,
            progress_tracker=self.progress_tracker,
            reasoning_extractor=self.reasoning_extractor,
            tone=tone,
            translation=translation,
            audience=audience,
            language=language,
        )
        
        self.crew_executor = CrewExecutor(
            job_id=job_id,
            event_emitter=self.event_emitter,
            reasoning_extractor=self.reasoning_extractor,
        )


    def run(self, email: str) -> EmailResponse:
        """Run the crew workflow with event streaming."""
        logger.info(f"Job {self.job_id}: Starting crew workflow")
        logger.debug(f"Job {self.job_id}: Email length: {len(email)} characters")

        # Create agents
        logger.debug(f"Job {self.job_id}: Creating agents")
        email_planner = self.agent_factory.create_agent("email_planner", "email_planner")
        tone_specialist = self.agent_factory.create_agent("tone_specialist", "tone_specialist")
        grammar_specialist = self.agent_factory.create_agent("grammar_specialist", "grammar_specialist")
        dictation_specialist = self.agent_factory.create_agent("dictation_specialist", "dictation_specialist")
        response_formatter = self.agent_factory.create_agent("response_formatter", "response_formatter")
        logger.info(f"Job {self.job_id}: All agents created")

        # Create tasks
        plan_task = self.task_factory.create_task("plan_email_improvement", email_planner)
        tone_task = self.task_factory.create_task("improve_tone", tone_specialist, [plan_task])
        grammar_task = self.task_factory.create_task("fix_grammar", grammar_specialist, [plan_task, tone_task])
        dictation_task = self.task_factory.create_task("fix_dictation", dictation_specialist, [plan_task, tone_task, grammar_task])
        
        # Format response task with output_pydantic
        format_task = self.task_factory.create_format_task(
            response_formatter,
            [plan_task, tone_task, grammar_task, dictation_task],
            EmailResponse,
        )

        # Create crew
        crew_instance = Crew(
            agents=[email_planner, tone_specialist, grammar_specialist, dictation_specialist, response_formatter],
            tasks=[plan_task, tone_task, grammar_task, dictation_task, format_task],
            process=Process.sequential,
            verbose=True,
        )

        # Build translation inputs
        translation_inputs = TranslationInstructionBuilder.build_instructions(self.translation)
        
        # Build inputs dict for CrewAI
        crew_inputs = {
            "email": email,
            "translation_instruction": translation_inputs["translation_instruction"],
            "output_language_requirement": translation_inputs["output_language_requirement"],
            "format_translation_instruction": translation_inputs["format_translation_instruction"],
            "tone": self.tone,
            "translation": self.translation,
            "audience": self.audience,
            "language": self.language,
        }

        logger.info(
            f"Job {self.job_id}: Crew inputs prepared - "
            f"translation={self.translation}, tone={self.tone}, audience={self.audience}"
        )

        try:
            # Execute crew workflow
            result = self.crew_executor.execute(crew_instance, crew_inputs)
            
            # Parse and return result
            return self.result_parser.parse_result(result)
            
        except Exception as e:
            logger.error(f"Job {self.job_id}: Crew workflow failed: {e}", exc_info=True)
            
            # Track LLM error if it's an LLM-related error
            model_name = getattr(self._llm, "_model_name", "unknown")
            error_type = type(e).__name__
            error_message = str(e).lower()
            
            is_llm_error = (
                "llm" in error_type.lower() or 
                "api" in error_type.lower() or 
                "openai" in error_type.lower() or
                "anthropic" in error_type.lower() or
                "timeout" in error_message or
                "connection" in error_message or
                "429" in error_message or
                "401" in error_message or
                "404" in error_message
            )
            
            if is_llm_error:
                llm_request_errors_total.labels(
                    model=model_name, 
                    agent_name="unknown", 
                    error_type=error_type
                ).inc()
                logger.warning(f"Job {self.job_id}: LLM error tracked - {error_type}: {error_message}")
            
            raise


async def run_async(
    job_id: str, 
    email: str, 
    redis_service: RedisService,
    tone: ToneEnum | str = ToneEnum.PROFESSIONAL,
    translation: TranslationDirectionEnum | str = TranslationDirectionEnum.NONE,
    audience: AudienceEnum | str = AudienceEnum.GENERAL,
    language: LanguageEnum | str = LanguageEnum.ENGLISH,
) -> EmailResponse:
    """Run the crew workflow asynchronously."""
    # Normalize to enums if strings are passed (for backward compatibility)
    tone_enum = tone if isinstance(tone, ToneEnum) else ToneEnum(tone)
    translation_enum = translation if isinstance(translation, TranslationDirectionEnum) else TranslationDirectionEnum(translation)
    audience_enum = audience if isinstance(audience, AudienceEnum) else AudienceEnum(audience)
    language_enum = language if isinstance(language, LanguageEnum) else LanguageEnum(language)
    
    logger.info(
        f"Starting async workflow for job: {job_id} "
        f"(tone={tone_enum.value}, translation={translation_enum.value}, audience={audience_enum.value}, language={language_enum.value})"
    )
    crew_instance = AsyncMailFormatterCrew(
        job_id, 
        redis_service, 
        tone=tone_enum, 
        translation=translation_enum, 
        audience=audience_enum, 
        language=language_enum
    )
    
    # Update job status to processing
    redis_service.update_job_status(job_id, JobStatusEnum.PROCESSING)
    
    try:
        logger.info(f"Job {job_id}: Running crew in thread pool")
        # Run in thread pool to avoid blocking
        result = await asyncio.to_thread(crew_instance.run, email)
        logger.info(f"Job {job_id}: Crew workflow completed")
        
        # Update job status to completed
        redis_service.update_job_status(job_id, JobStatusEnum.COMPLETED, result=result)
        
        # Update metrics
        jobs_completed_total.labels(status="completed").inc()
        jobs_in_progress.dec()
        
        # Emit completion event
        event = AgentEvent(
            job_id=job_id,
            agent_name=AgentNameEnum.SYSTEM,
            agent_role=AgentRoleEnum.SYSTEM,
            status=AgentEventStatusEnum.COMPLETED,
            progress=100,
            message="Email improvement completed successfully",
            timestamp=datetime.now(timezone.utc).isoformat(),
            output=None,
        )
        redis_service.add_event(event)
        redis_service.publish_event(event)
        logger.info(f"Job {job_id}: Successfully completed and result stored")
        
        return result
        
    except Exception as e:
        logger.error(f"Job {job_id}: Async workflow failed: {e}", exc_info=True)
        # Update job status to failed
        redis_service.update_job_status(job_id, JobStatusEnum.FAILED, error=str(e))
        
        # Update metrics
        jobs_completed_total.labels(status="failed").inc()
        jobs_in_progress.dec()
        
        # Emit failure event
        event = AgentEvent(
            job_id=job_id,
            agent_name=AgentNameEnum.SYSTEM,
            agent_role=AgentRoleEnum.SYSTEM,
            status=AgentEventStatusEnum.FAILED,
            progress=0,
            message=f"Email improvement failed: {str(e)}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            output=None,
        )
        redis_service.add_event(event)
        redis_service.publish_event(event)
        
        raise
