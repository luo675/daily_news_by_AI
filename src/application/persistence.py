"""Minimal persistence service for application-layer orchestration."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import func, select

from src.application.schemas import (
    DocumentMappingBundle,
    OpportunityMappingBundle,
    PersistedArtifacts,
)
from src.domain.models import DailyBrief, DocumentEntity, DocumentTopic, Entity, Topic


@runtime_checkable
class SessionLike(Protocol):
    def add(self, instance: Any) -> None: ...
    def add_all(self, instances: list[Any]) -> None: ...
    def flush(self) -> None: ...
    def commit(self) -> None: ...


class MemorySession:
    """In-memory storage with a Session-like surface for verification."""

    def __init__(self) -> None:
        self.storage: dict[str, list[Any]] = {}
        self.entity_index: dict[tuple[str, str], Entity] = {}
        self.topic_index: dict[str, Topic] = {}

    def add(self, instance: Any) -> None:
        if isinstance(instance, Entity):
            key = (instance.entity_type, instance.name)
            existing = self.entity_index.get(key)
            if existing is not None:
                return
            self.entity_index[key] = instance
        elif isinstance(instance, Topic):
            key = build_topic_key(instance)
            existing = self.topic_index.get(key)
            if existing is not None:
                return
            self.topic_index[key] = instance
        self.storage.setdefault(type(instance).__name__, []).append(instance)

    def add_all(self, instances: list[Any]) -> None:
        for instance in instances:
            self.add(instance)

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        return None

    def get_entity_by_key(self, entity_type: str, name: str) -> Entity | None:
        return self.entity_index.get((entity_type, name))

    def get_topic_by_key(self, topic_key: str) -> Topic | None:
        return self.topic_index.get(topic_key)

    def list_instances(self, model_type: type[Any]) -> list[Any]:
        return list(self.storage.get(model_type.__name__, []))


def build_topic_key(topic: Topic) -> str:
    """Stable topic reuse key: prefer English name, then Chinese name."""
    return (topic.name_en or topic.name_zh or "").strip().lower()


def _maybe_get_session_matches(session: SessionLike, method_name: str, *args: object) -> Any | None:
    method = getattr(session, method_name, None)
    if callable(method):
        return method(*args)
    return None


def _maybe_execute_scalar(session: SessionLike, statement: Any) -> Any | None:
    execute = getattr(session, "execute", None)
    if not callable(execute):
        return None

    result = execute(statement)
    scalar_one_or_none = getattr(result, "scalar_one_or_none", None)
    if callable(scalar_one_or_none):
        return scalar_one_or_none()

    scalars = getattr(result, "scalars", None)
    if callable(scalars):
        scalar_result = scalars()
        first = getattr(scalar_result, "first", None)
        if callable(first):
            return first()

    return None


class PipelinePersistenceService:
    """Persist mapped pipeline artifacts to either memory or a provided session."""

    def __init__(self, session: SessionLike | None = None) -> None:
        self.session: SessionLike = session or MemorySession()
        self.mode = "memory" if session is None else "session"

    def save_document_summary(self, bundle: DocumentMappingBundle) -> None:
        self.session.add(bundle.document)
        self.session.add(bundle.summary)

    def save_entities(self, bundle: DocumentMappingBundle) -> None:
        resolved_entities = self._resolve_entities(bundle.entities)
        for document_entity in bundle.document_entities:
            entity_key = bundle.entity_keys_by_id.get(document_entity.entity_id)
            if entity_key is None:
                continue
            resolved = resolved_entities[entity_key]
            document_entity.entity_id = resolved.id

        self.session.add_all(list(resolved_entities.values()))
        self._add_unique_document_entities(bundle.document_entities)

    def save_topics(self, bundle: DocumentMappingBundle) -> None:
        resolved_topics = self._resolve_topics(bundle.topics)
        for document_topic in bundle.document_topics:
            topic_key = bundle.topic_keys_by_id.get(document_topic.topic_id)
            if topic_key is None:
                continue
            resolved = resolved_topics[topic_key]
            document_topic.topic_id = resolved.id

        self.session.add_all(list(resolved_topics.values()))
        self._add_unique_document_topics(bundle.document_topics)

    def save_opportunities(self, bundles: list[OpportunityMappingBundle]) -> None:
        for bundle in bundles:
            self.session.add(bundle.assessment)
            self.session.add_all(bundle.evidence_items)

    def save_daily_brief(self, brief: DailyBrief | None) -> None:
        if brief is not None:
            self.session.add(brief)

    def save_pipeline_artifacts(
        self,
        processing_bundle: DocumentMappingBundle,
        opportunity_bundles: list[OpportunityMappingBundle],
        brief: DailyBrief | None = None,
        commit: bool = True,
    ) -> PersistedArtifacts:
        self.save_document_summary(processing_bundle)
        self.save_entities(processing_bundle)
        self.save_topics(processing_bundle)
        self.save_opportunities(opportunity_bundles)
        self.save_daily_brief(brief)
        self.session.flush()
        if commit:
            self.session.commit()

        notes = [f"{note.target}.{note.field_name}: {note.detail}" for note in processing_bundle.notes]
        for bundle in opportunity_bundles:
            notes.extend(f"{note.target}.{note.field_name}: {note.detail}" for note in bundle.notes)
        if brief is None:
            notes.append("daily_brief: skipped")

        return PersistedArtifacts(
            mode=self.mode,
            saved=True,
            document_id=processing_bundle.document.id,
            summary_id=processing_bundle.summary.id,
            entity_ids=sorted({item.entity_id for item in processing_bundle.document_entities}),
            document_entity_ids=[item.id for item in processing_bundle.document_entities],
            topic_ids=sorted({item.topic_id for item in processing_bundle.document_topics}),
            document_topic_ids=[item.id for item in processing_bundle.document_topics],
            opportunity_ids=[item.assessment.id for item in opportunity_bundles],
            opportunity_evidence_ids=[
                evidence.id
                for bundle in opportunity_bundles
                for evidence in bundle.evidence_items
            ],
            daily_brief_id=brief.id if brief is not None else None,
            notes=notes,
        )

    def _resolve_entities(self, entities: Iterable[Entity]) -> dict[tuple[str, str], Entity]:
        resolved: dict[tuple[str, str], Entity] = {}
        for entity in entities:
            key = (entity.entity_type, entity.name)
            resolved[key] = self._get_or_create_entity(entity)
        return resolved

    def _resolve_topics(self, topics: Iterable[Topic]) -> dict[str, Topic]:
        resolved: dict[str, Topic] = {}
        for topic in topics:
            key = build_topic_key(topic)
            if not key:
                continue
            resolved[key] = self._get_or_create_topic(topic)
        return resolved

    def _get_or_create_entity(self, candidate: Entity) -> Entity:
        existing = _maybe_get_session_matches(
            self.session,
            "get_entity_by_key",
            candidate.entity_type,
            candidate.name,
        )
        if existing is None:
            existing = _maybe_execute_scalar(
                self.session,
                select(Entity).where(
                    Entity.entity_type == candidate.entity_type,
                    Entity.name == candidate.name,
                ),
            )
        if existing is not None:
            return existing

        self.session.add(candidate)
        return candidate

    def _get_or_create_topic(self, candidate: Topic) -> Topic:
        topic_key = build_topic_key(candidate)
        existing = _maybe_get_session_matches(self.session, "get_topic_by_key", topic_key)
        if existing is None and topic_key:
            existing = _maybe_execute_scalar(
                self.session,
                select(Topic).where(
                    Topic.name_en.is_not(None),
                    Topic.name_en != "",
                    func.lower(func.trim(Topic.name_en)) == topic_key,
                ),
            )
        if existing is None and topic_key:
            existing = _maybe_execute_scalar(
                self.session,
                select(Topic).where(
                    (Topic.name_en.is_(None) | (Topic.name_en == "")),
                    Topic.name_zh.is_not(None),
                    Topic.name_zh != "",
                    func.lower(func.trim(Topic.name_zh)) == topic_key,
                ),
            )
        if existing is not None:
            return existing

        self.session.add(candidate)
        return candidate

    def _add_unique_document_entities(self, items: list[DocumentEntity]) -> None:
        seen: set[tuple[UUID, UUID]] = set()
        unique_items: list[DocumentEntity] = []
        for item in items:
            key = (item.document_id, item.entity_id)
            if key in seen:
                continue
            seen.add(key)
            unique_items.append(item)
        self.session.add_all(unique_items)

    def _add_unique_document_topics(self, items: list[DocumentTopic]) -> None:
        seen: set[tuple[UUID, UUID]] = set()
        unique_items: list[DocumentTopic] = []
        for item in items:
            key = (item.document_id, item.topic_id)
            if key in seen:
                continue
            seen.add(key)
            unique_items.append(item)
        self.session.add_all(unique_items)
