"""处理流水线编排骨架。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.ingestion.schemas import RawDocumentInput
from src.processing.cleaning import CleaningPipeline
from src.processing.conflicts import ConflictDetector
from src.processing.extraction import EntityExtractor, TopicExtractor
from src.processing.schemas import ProcessingResult
from src.processing.summarization import SummaryBuilder

if TYPE_CHECKING:
    from uuid import UUID

    from src.application.persistence import SessionLike
    from src.application.schemas import ApplicationPipelineResult


class ProcessingPipeline:
    """串联处理层骨架。"""

    def __init__(
        self,
        cleaner: CleaningPipeline | None = None,
        summarizer: SummaryBuilder | None = None,
        entity_extractor: EntityExtractor | None = None,
        topic_extractor: TopicExtractor | None = None,
        conflict_detector: ConflictDetector | None = None,
    ) -> None:
        self.cleaner = cleaner or CleaningPipeline()
        self.summarizer = summarizer or SummaryBuilder()
        self.entity_extractor = entity_extractor or EntityExtractor()
        self.topic_extractor = topic_extractor or TopicExtractor()
        self.conflict_detector = conflict_detector or ConflictDetector()

    def process(self, document: RawDocumentInput) -> ProcessingResult:
        """执行完整处理骨架。"""
        cleaned = self.cleaner.clean(document)
        summary = self.summarizer.build(cleaned)
        entities = self.entity_extractor.extract(cleaned)
        topics = self.topic_extractor.extract(cleaned)

        result = ProcessingResult(
            cleaned_document=cleaned,
            summary=summary,
            entities=entities,
            topics=topics,
        )
        result.conflicts = self.conflict_detector.detect(result)
        return result


def run_document_pipeline(
    document: RawDocumentInput,
    *,
    persist: bool = False,
    include_daily_brief: bool = True,
    document_id: "UUID | None" = None,
    session: "SessionLike | None" = None,
) -> "ApplicationPipelineResult":
    """Application-layer wrapper kept close to the processing pipeline entry."""
    from src.application.orchestrator import run_document_pipeline as _run_document_pipeline

    return _run_document_pipeline(
        document=document,
        persist=persist,
        include_daily_brief=include_daily_brief,
        document_id=document_id,
        session=session,
    )
