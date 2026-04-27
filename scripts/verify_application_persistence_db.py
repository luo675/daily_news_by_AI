"""Verify application persistence against a real PostgreSQL database."""

from __future__ import annotations

import io
import sys
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from src.application.mappers import DomainMapper
from src.application.orchestrator import DocumentPipelineOrchestrator
from src.application.persistence import PipelinePersistenceService
from src.config import (
    DatabaseConfig,
    create_sync_engine,
    get_database_env_snapshot,
    probe_database_connection,
    probe_database_environment,
    probe_pgvector_extension,
)
from src.domain.base import Base
from src.domain.models import (
    Chunk,
    ChunkEmbedding,
    Document,
    DocumentEntity,
    DocumentSummary,
    DocumentTopic,
    Entity,
    OpportunityAssessment,
    OpportunityEvidence,
    Source,
    Topic,
)
from src.ingestion.schemas import RawDocumentInput, SourceType

REQUIRED_TABLES = [
    Source.__table__,
    Document.__table__,
    DocumentSummary.__table__,
    Chunk.__table__,
    ChunkEmbedding.__table__,
    Entity.__table__,
    DocumentEntity.__table__,
    Topic.__table__,
    DocumentTopic.__table__,
    OpportunityAssessment.__table__,
    OpportunityEvidence.__table__,
]


@dataclass
class VerificationRun:
    run_id: str = field(default_factory=lambda: uuid4().hex[:12])
    document_ids: set[UUID] = field(default_factory=set)
    opportunity_ids: set[UUID] = field(default_factory=set)
    created_entity_ids: set[UUID] = field(default_factory=set)
    created_topic_ids: set[UUID] = field(default_factory=set)


@dataclass
class DatabaseRuntime:
    label: str
    reason: str
    isolation: str
    session_factory: sessionmaker[Session]
    cleanup: Callable[[], None]


def print_info(message: str) -> None:
    print(f"[INFO] {message}")


def fail_with_layer(layer: str, detail: str) -> None:
    print(f"[FAIL] Layer: {layer}")
    print(f"[FAIL] Detail: {detail}")
    raise SystemExit(1)


def assert_pass(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


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


def make_run_scoped_title(base: str, run: VerificationRun) -> str:
    return f"{base} [{run.run_id}]"


def make_run_scoped_url(path: str, run: VerificationRun) -> str:
    return f"https://example.com/{path}?run_id={run.run_id}"


def build_runtime() -> DatabaseRuntime:
    config = DatabaseConfig()
    environment_probe = probe_database_environment()
    if not environment_probe.ok:
        fail_with_layer(environment_probe.layer, environment_probe.detail)

    connection_probe = probe_database_connection(config)
    if not connection_probe.ok:
        fail_with_layer(connection_probe.layer, connection_probe.detail)

    pgvector_probe = probe_pgvector_extension(config)
    if not pgvector_probe.ok:
        fail_with_layer(pgvector_probe.layer, pgvector_probe.detail)

    engine = create_sync_engine(config)
    try:
        Base.metadata.create_all(engine, tables=REQUIRED_TABLES)
    except Exception as exc:
        engine.dispose()
        fail_with_layer("schema/bootstrap", f"Schema bootstrap failed on PostgreSQL: {type(exc).__name__}: {exc}")

    return DatabaseRuntime(
        label="PostgreSQL",
        reason="Using explicit DB_* environment variables and the project PostgreSQL engine.",
        isolation=(
            "Generates a unique run_id, writes only run-scoped titles/URLs, records exact document and "
            "opportunity IDs created in this run, and deletes only those rows in finally."
        ),
        session_factory=sessionmaker(bind=engine, expire_on_commit=False),
        cleanup=engine.dispose,
    )


@contextmanager
def managed_session(factory: sessionmaker[Session]):
    session = factory()
    try:
        yield session
    finally:
        session.close()


def require_non_empty_links(items: list[object], label: str) -> None:
    assert_pass(
        bool(items),
        f"Processing result must contain at least one {label} link before duplicate-link verification",
    )


def snapshot_model_ids(session: Session, model) -> set[UUID]:
    return set(session.execute(select(model.id)).scalars().all())


def record_created_entity_topic_ids(
    session: Session,
    run: VerificationRun,
    entity_ids_before: set[UUID],
    topic_ids_before: set[UUID],
) -> None:
    run.created_entity_ids.update(snapshot_model_ids(session, Entity) - entity_ids_before)
    run.created_topic_ids.update(snapshot_model_ids(session, Topic) - topic_ids_before)


def verify_multi_document_reuse(session: Session, run: VerificationRun) -> None:
    orchestrator = DocumentPipelineOrchestrator()
    entity_ids_before = snapshot_model_ids(session, Entity)
    topic_ids_before = snapshot_model_ids(session, Topic)

    first = orchestrator.run_document_pipeline(
        build_reuse_document(
            title=make_run_scoped_title("Startup tooling note one", run),
            url=make_run_scoped_url("verify-db-reuse-one", run),
            extra_line="Teams want better startup execution visibility.",
        ),
        persist=True,
        include_daily_brief=False,
        session=session,
    )
    second = orchestrator.run_document_pipeline(
        build_reuse_document(
            title=make_run_scoped_title("Startup tooling note two", run),
            url=make_run_scoped_url("verify-db-reuse-two", run),
            extra_line="Teams still debate how production-ready agent workflows are.",
        ),
        persist=True,
        include_daily_brief=False,
        session=session,
    )

    if first.persisted is not None:
        run.document_ids.add(first.persisted.document_id)
        run.opportunity_ids.update(first.persisted.opportunity_ids)
    if second.persisted is not None:
        run.document_ids.add(second.persisted.document_id)
        run.opportunity_ids.update(second.persisted.opportunity_ids)

    record_created_entity_topic_ids(session, run, entity_ids_before, topic_ids_before)

    openai_entities = session.execute(
        select(Entity).where(Entity.entity_type == "company", Entity.name == "openai")
    ).scalars().all()
    assert_pass(len(openai_entities) == 1, "Cross-document entity reuse keeps one Entity row for openai")
    openai_entity = openai_entities[0]

    tooling_topics = session.execute(
        select(Topic).where(func.lower(func.trim(Topic.name_en)) == "developer tooling")
    ).scalars().all()
    assert_pass(len(tooling_topics) == 1, "Cross-document topic reuse keeps one Topic row for developer tooling")
    tooling_topic = tooling_topics[0]

    first_openai_link = session.execute(
        select(DocumentEntity).where(
            DocumentEntity.document_id == first.document_id,
            DocumentEntity.entity_id == openai_entity.id,
        )
    ).scalar_one_or_none()
    second_openai_link = session.execute(
        select(DocumentEntity).where(
            DocumentEntity.document_id == second.document_id,
            DocumentEntity.entity_id == openai_entity.id,
        )
    ).scalar_one_or_none()
    assert_pass(
        first_openai_link is not None and second_openai_link is not None,
        "Both documents link to the same reused entity_id",
    )

    first_tooling_link = session.execute(
        select(DocumentTopic).where(
            DocumentTopic.document_id == first.document_id,
            DocumentTopic.topic_id == tooling_topic.id,
        )
    ).scalar_one_or_none()
    second_tooling_link = session.execute(
        select(DocumentTopic).where(
            DocumentTopic.document_id == second.document_id,
            DocumentTopic.topic_id == tooling_topic.id,
        )
    ).scalar_one_or_none()
    assert_pass(
        first_tooling_link is not None and second_tooling_link is not None,
        "Both documents link to the same reused topic_id",
    )


def verify_same_document_dedup(session: Session, run: VerificationRun) -> None:
    orchestrator = DocumentPipelineOrchestrator()
    mapper = DomainMapper()
    persistence = PipelinePersistenceService(session=session)
    entity_ids_before = snapshot_model_ids(session, Entity)
    topic_ids_before = snapshot_model_ids(session, Topic)

    processing_result = orchestrator.processing_pipeline.process(
        build_reuse_document(
            title=make_run_scoped_title("Startup tooling duplicate link check", run),
            url=make_run_scoped_url("verify-db-dup-check", run),
            extra_line="OpenAI appears again in the same document with the same developer tooling theme.",
        )
    )
    mapped = mapper.map_processing_result(uuid4(), processing_result)

    require_non_empty_links(mapped.document_entities, "entity")
    first_entity_link = mapped.document_entities[0]
    mapped.document_entities.append(
        DocumentEntity(
            id=uuid4(),
            document_id=first_entity_link.document_id,
            entity_id=first_entity_link.entity_id,
            relevance_score=first_entity_link.relevance_score,
            context=first_entity_link.context,
        )
    )
    require_non_empty_links(mapped.document_topics, "topic")
    first_topic_link = mapped.document_topics[0]
    mapped.document_topics.append(
        DocumentTopic(
            id=uuid4(),
            document_id=first_topic_link.document_id,
            topic_id=first_topic_link.topic_id,
            relevance_score=first_topic_link.relevance_score,
        )
    )

    persistence.save_pipeline_artifacts(
        processing_bundle=mapped,
        opportunity_bundles=[],
        brief=None,
    )
    run.document_ids.add(mapped.document.id)
    record_created_entity_topic_ids(session, run, entity_ids_before, topic_ids_before)

    entity_link_count = session.execute(
        select(func.count()).select_from(DocumentEntity).where(
            DocumentEntity.document_id == mapped.document.id
        )
    ).scalar_one()
    entity_pair_count = session.execute(
        select(func.count(func.distinct(DocumentEntity.entity_id))).where(
            DocumentEntity.document_id == mapped.document.id
        )
    ).scalar_one()
    topic_link_count = session.execute(
        select(func.count()).select_from(DocumentTopic).where(
            DocumentTopic.document_id == mapped.document.id
        )
    ).scalar_one()
    topic_pair_count = session.execute(
        select(func.count(func.distinct(DocumentTopic.topic_id))).where(
            DocumentTopic.document_id == mapped.document.id
        )
    ).scalar_one()

    assert_pass(
        entity_link_count == entity_pair_count and topic_link_count == topic_pair_count,
        "Duplicate links inside one document are deduplicated before insert",
    )


def cleanup_postgresql_run_data(runtime: DatabaseRuntime, run: VerificationRun) -> None:
    if not run.document_ids and not run.opportunity_ids and not run.created_entity_ids and not run.created_topic_ids:
        return

    with managed_session(runtime.session_factory) as session:
        if run.opportunity_ids:
            session.execute(
                OpportunityEvidence.__table__.delete().where(
                    OpportunityEvidence.opportunity_id.in_(run.opportunity_ids)
                )
            )
            session.execute(
                OpportunityAssessment.__table__.delete().where(
                    OpportunityAssessment.id.in_(run.opportunity_ids)
                )
            )

        if run.document_ids:
            session.execute(
                DocumentEntity.__table__.delete().where(DocumentEntity.document_id.in_(run.document_ids))
            )
            session.execute(
                DocumentTopic.__table__.delete().where(DocumentTopic.document_id.in_(run.document_ids))
            )
            session.execute(
                DocumentSummary.__table__.delete().where(DocumentSummary.document_id.in_(run.document_ids))
            )
            session.execute(
                ChunkEmbedding.__table__.delete().where(
                    ChunkEmbedding.chunk_id.in_(
                        select(Chunk.id).where(Chunk.document_id.in_(run.document_ids))
                    )
                )
            )
            session.execute(Chunk.__table__.delete().where(Chunk.document_id.in_(run.document_ids)))
            session.execute(Document.__table__.delete().where(Document.id.in_(run.document_ids)))

        if run.created_entity_ids:
            deletable_entity_ids = session.execute(
                select(Entity.id).where(
                    Entity.id.in_(run.created_entity_ids),
                    ~Entity.id.in_(select(DocumentEntity.entity_id)),
                )
            ).scalars().all()
            if deletable_entity_ids:
                session.execute(Entity.__table__.delete().where(Entity.id.in_(deletable_entity_ids)))

        if run.created_topic_ids:
            deletable_topic_ids = session.execute(
                select(Topic.id).where(
                    Topic.id.in_(run.created_topic_ids),
                    ~Topic.id.in_(select(DocumentTopic.topic_id)),
                )
            ).scalars().all()
            if deletable_topic_ids:
                session.execute(Topic.__table__.delete().where(Topic.id.in_(deletable_topic_ids)))

        session.commit()


def main() -> None:
    print("=" * 72)
    print("Application persistence verification with real PostgreSQL Session")
    print("=" * 72)
    print_info(f"DB env snapshot: {get_database_env_snapshot()}")

    run = VerificationRun()
    runtime = build_runtime()
    print_info(f"Database mode: {runtime.label}")
    print_info(f"Reason: {runtime.reason}")
    print_info(f"Run ID: {run.run_id}")
    print_info(f"Isolation: {runtime.isolation}")

    try:
        with managed_session(runtime.session_factory) as session:
            print("[PASS] Using a real PostgreSQL SQLAlchemy Session")
            try:
                verify_multi_document_reuse(session, run)
                verify_same_document_dedup(session, run)
            except IntegrityError as exc:
                print(f"[FAIL] Unique constraint conflict: {exc}")
                raise

            print("[PASS] Persisted two documents in one session")
            print(
                "[PASS] No unique constraint conflicts: "
                "uq_entities_type_name / uq_doc_entities_doc_entity / uq_doc_topics_doc_topic"
            )
    except AssertionError as exc:
        print(f"[FAIL] Layer: persistence verification")
        print(f"[FAIL] Detail: {exc}")
        raise SystemExit(1) from exc
    except SQLAlchemyError as exc:
        print(f"[FAIL] Layer: DB connection")
        print(f"[FAIL] Detail: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc
    finally:
        cleanup_postgresql_run_data(runtime, run)
        runtime.cleanup()

    print("=" * 72)
    print("Application persistence verification passed")
    print("=" * 72)


if __name__ == "__main__":
    main()
