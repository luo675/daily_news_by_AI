"""Application-layer orchestration for the stage-one document pipeline."""

from __future__ import annotations

from uuid import UUID, uuid4

from src.application.mappers import DomainMapper
from src.application.persistence import PipelinePersistenceService, SessionLike
from src.application.schemas import ApplicationPipelineResult
from src.briefing.service import DailyBriefGenerator
from src.ingestion.schemas import RawDocumentInput
from src.processing.pipeline import ProcessingPipeline
from src.scoring.service import OpportunityScorer


class DocumentPipelineOrchestrator:
    """Connect processing, scoring, mapping, briefing and optional persistence."""

    def __init__(
        self,
        processing_pipeline: ProcessingPipeline | None = None,
        opportunity_scorer: OpportunityScorer | None = None,
        daily_brief_generator: DailyBriefGenerator | None = None,
        mapper: DomainMapper | None = None,
    ) -> None:
        self.processing_pipeline = processing_pipeline or ProcessingPipeline()
        self.opportunity_scorer = opportunity_scorer or OpportunityScorer()
        self.daily_brief_generator = daily_brief_generator or DailyBriefGenerator()
        self.mapper = mapper or DomainMapper()

    def run_document_pipeline(
        self,
        document: RawDocumentInput,
        *,
        persist: bool = False,
        include_daily_brief: bool = True,
        document_id: UUID | None = None,
        session: SessionLike | None = None,
    ) -> ApplicationPipelineResult:
        document_id = document_id or uuid4()
        processing_result = self.processing_pipeline.process(document)
        opportunities = self.opportunity_scorer.score(processing_result)
        daily_brief = (
            self.daily_brief_generator.generate(
                results=[processing_result],
                opportunities=opportunities,
            )
            if include_daily_brief
            else None
        )

        persisted = None
        if persist:
            persistence = PipelinePersistenceService(session=session)
            processing_bundle = self.mapper.map_processing_result(document_id, processing_result)
            opportunity_bundles = [
                self.mapper.map_opportunity_draft(
                    document_id=document_id,
                    draft=draft,
                    source_url=document.url,
                )
                for draft in opportunities
            ]
            brief_record = (
                self.mapper.map_daily_brief_draft(daily_brief)
                if daily_brief is not None
                else None
            )
            persisted = persistence.save_pipeline_artifacts(
                processing_bundle=processing_bundle,
                opportunity_bundles=opportunity_bundles,
                brief=brief_record,
            )

        return ApplicationPipelineResult(
            document_id=document_id,
            cleaned=processing_result.cleaned_document,
            summary=processing_result.summary,
            entities=processing_result.entities,
            topics=processing_result.topics,
            conflicts=processing_result.conflicts,
            opportunities=opportunities,
            daily_brief=daily_brief,
            persisted=persisted,
        )


def run_document_pipeline(
    document: RawDocumentInput,
    *,
    persist: bool = False,
    include_daily_brief: bool = True,
    document_id: UUID | None = None,
    session: SessionLike | None = None,
) -> ApplicationPipelineResult:
    orchestrator = DocumentPipelineOrchestrator()
    return orchestrator.run_document_pipeline(
        document=document,
        persist=persist,
        include_daily_brief=include_daily_brief,
        document_id=document_id,
        session=session,
    )
