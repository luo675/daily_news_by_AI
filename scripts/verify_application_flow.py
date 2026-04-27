"""Verify application-layer orchestration, mapping and persistence skeleton."""

import io
import sys
from uuid import uuid4

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from src.application.mappers import DomainMapper
from src.application.persistence import MemorySession, PipelinePersistenceService
from src.application.orchestrator import DocumentPipelineOrchestrator, run_document_pipeline
from src.domain.models import DocumentEntity, DocumentTopic, Entity, Topic
from src.ingestion.schemas import RawDocumentInput, SourceType


def build_document() -> RawDocumentInput:
    return RawDocumentInput(
        title="AI startup tooling is getting more opinionated",
        source_type=SourceType.BLOG,
        url="https://example.com/ai-startup-tooling",
        author="Example Author",
        language="en",
        content_text=(
            "AI startup tooling is shifting toward agent workflows. "
            "OpenAI and Anthropic are mentioned alongside developer tooling. "
            "Teams still disagree on deployment readiness, which creates product gaps."
        ),
    )


def build_reuse_document(title: str, url: str, extra_line: str) -> RawDocumentInput:
    return RawDocumentInput(
        title=title,
        source_type=SourceType.BLOG,
        url=url,
        author="Example Author",
        language="en",
        content_text=(
            "OpenAI is shipping more developer tooling for AI startup workflows. "
            "Anthropic is also active in the same developer tooling space. "
            "This document discusses startup tooling and agent workflows. "
            f"{extra_line}"
        ),
    )


def test_process_only_mode() -> None:
    result = run_document_pipeline(build_document(), persist=False, include_daily_brief=True)
    assert result.cleaned.normalized_text
    assert result.summary.zh
    assert isinstance(result.entities, list)
    assert isinstance(result.topics, list)
    assert isinstance(result.conflicts, list)
    assert isinstance(result.opportunities, list)
    assert result.daily_brief is not None
    assert result.persisted is None
    print("  [PASS] process-only mode works without persistence")


def test_mapper_alignment() -> None:
    document = build_document()
    orchestrator = DocumentPipelineOrchestrator()
    processing_result = orchestrator.processing_pipeline.process(document)
    mapper = DomainMapper()
    document_id = uuid4()
    mapped = mapper.map_processing_result(document_id, processing_result)

    assert mapped.document.id == document_id
    assert mapped.summary.document_id == document_id
    assert hasattr(mapped.summary, "summary_zh")
    assert all(item.document_id == document_id for item in mapped.document_entities)
    assert all(item.document_id == document_id for item in mapped.document_topics)

    opportunities = orchestrator.opportunity_scorer.score(processing_result)
    if opportunities:
        opportunity_bundle = mapper.map_opportunity_draft(document_id, opportunities[0], document.url)
        assert opportunity_bundle.assessment.total_score == opportunities[0].score.total
        assert all(
            item.opportunity_id == opportunity_bundle.assessment.id
            for item in opportunity_bundle.evidence_items
        )

    brief = orchestrator.daily_brief_generator.generate([processing_result], opportunities=opportunities)
    brief_record = mapper.map_daily_brief_draft(brief)
    assert brief_record.summary_zh == brief.summary.zh
    assert brief_record.summary_en == brief.summary.en
    assert brief_record.pending_questions == brief.open_questions.items
    assert mapped.notes
    print("  [PASS] mapper output aligns with key domain fields")


def test_memory_persistence_mode() -> None:
    result = run_document_pipeline(build_document(), persist=True, include_daily_brief=True)
    assert result.persisted is not None
    assert result.persisted.saved is True
    assert result.persisted.mode == "memory"
    assert result.persisted.summary_id is not None
    print("  [PASS] persist mode works with in-memory session")


def test_same_document_duplicate_links_are_deduplicated() -> None:
    session = MemorySession()
    orchestrator = DocumentPipelineOrchestrator()
    mapper = DomainMapper()
    persistence = PipelinePersistenceService(session=session)

    document = build_reuse_document(
        title="Startup tooling duplicate link check",
        url="https://example.com/reuse-dup-check",
        extra_line="OpenAI appears again in the same document with the same developer tooling theme.",
    )
    processing_result = orchestrator.processing_pipeline.process(document)
    mapped = mapper.map_processing_result(uuid4(), processing_result)

    if mapped.document_entities:
        first = mapped.document_entities[0]
        mapped.document_entities.append(
            DocumentEntity(
                id=uuid4(),
                document_id=first.document_id,
                entity_id=first.entity_id,
                relevance_score=first.relevance_score,
                context=first.context,
            )
        )
    if mapped.document_topics:
        first = mapped.document_topics[0]
        mapped.document_topics.append(
            DocumentTopic(
                id=uuid4(),
                document_id=first.document_id,
                topic_id=first.topic_id,
                relevance_score=first.relevance_score,
            )
        )

    persistence.save_pipeline_artifacts(
        processing_bundle=mapped,
        opportunity_bundles=[],
        brief=None,
    )

    document_entities = session.list_instances(DocumentEntity)
    document_topics = session.list_instances(DocumentTopic)

    entity_link_keys = [(item.document_id, item.entity_id) for item in document_entities]
    topic_link_keys = [(item.document_id, item.topic_id) for item in document_topics]
    assert len(entity_link_keys) == len(set(entity_link_keys))
    assert len(topic_link_keys) == len(set(topic_link_keys))

    print("  [PASS] duplicate entity/topic links are deduplicated within one document")


def test_multi_document_entity_topic_reuse() -> None:
    session = MemorySession()
    orchestrator = DocumentPipelineOrchestrator()

    first = orchestrator.run_document_pipeline(
        build_reuse_document(
            title="Startup tooling note one",
            url="https://example.com/reuse-one",
            extra_line="Teams want better startup execution visibility.",
        ),
        persist=True,
        include_daily_brief=False,
        session=session,
    )
    second = orchestrator.run_document_pipeline(
        build_reuse_document(
            title="Startup tooling note two",
            url="https://example.com/reuse-two",
            extra_line="Teams still debate how production-ready agent workflows are.",
        ),
        persist=True,
        include_daily_brief=False,
        session=session,
    )

    entities = session.list_instances(Entity)
    document_entities = session.list_instances(DocumentEntity)
    topics = session.list_instances(Topic)
    document_topics = session.list_instances(DocumentTopic)

    openai_entities = [
        item for item in entities
        if item.entity_type == "company" and item.name == "openai"
    ]
    assert len(openai_entities) == 1

    openai_links = [item for item in document_entities if item.entity_id == openai_entities[0].id]
    linked_documents = {item.document_id for item in openai_links}
    assert first.document_id in linked_documents
    assert second.document_id in linked_documents

    developer_tooling_topics = [
        item for item in topics
        if (item.name_en or item.name_zh or "").strip().lower() == "developer tooling"
    ]
    assert len(developer_tooling_topics) == 1

    reused_topic_links = [
        item for item in document_topics if item.topic_id == developer_tooling_topics[0].id
    ]
    linked_topic_documents = {item.document_id for item in reused_topic_links}
    assert first.document_id in linked_topic_documents
    assert second.document_id in linked_topic_documents

    print("  [PASS] multi-document entity/topic reuse works in one memory session")


def main() -> None:
    print("=" * 60)
    print("Application flow verification")
    print("=" * 60)
    test_process_only_mode()
    test_mapper_alignment()
    test_memory_persistence_mode()
    test_same_document_duplicate_links_are_deduplicated()
    test_multi_document_entity_topic_reuse()
    print("=" * 60)
    print("Application flow verification passed")
    print("=" * 60)


if __name__ == "__main__":
    main()
