"""处理流水线编排骨架。"""

from __future__ import annotations

from src.ingestion.schemas import RawDocumentInput
from src.processing.cleaning import CleaningPipeline
from src.processing.conflicts import ConflictDetector
from src.processing.extraction import EntityExtractor, TopicExtractor
from src.processing.schemas import ProcessingResult
from src.processing.summarization import SummaryBuilder


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
