"""Application-layer schemas for mapping and orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.briefing.schemas import DailyBriefDraft
from src.domain.models import (
    DailyBrief,
    Document,
    DocumentEntity,
    DocumentSummary,
    Entity,
    OpportunityAssessment,
    OpportunityEvidence,
    Topic,
    DocumentTopic,
)
from src.processing.schemas import (
    CleanedDocument,
    ConflictRecord,
    EntityMention,
    ProcessingResult,
    BilingualSummary,
    TopicAssignment,
)
from src.scoring.schemas import OpportunityDraft


@dataclass(slots=True)
class MapperNote:
    target: str
    field_name: str
    status: Literal["placeholder", "future_algorithm"]
    detail: str


@dataclass(slots=True)
class DocumentMappingBundle:
    document: Document
    summary: DocumentSummary
    entities: list[Entity]
    document_entities: list[DocumentEntity]
    topics: list[Topic]
    document_topics: list[DocumentTopic]
    entity_keys_by_id: dict[UUID, tuple[str, str]] = field(default_factory=dict)
    topic_keys_by_id: dict[UUID, str] = field(default_factory=dict)
    notes: list[MapperNote] = field(default_factory=list)


@dataclass(slots=True)
class OpportunityMappingBundle:
    assessment: OpportunityAssessment
    evidence_items: list[OpportunityEvidence]
    notes: list[MapperNote] = field(default_factory=list)


class PersistedArtifacts(BaseModel):
    mode: Literal["memory", "session"] = Field(..., description="Persistence backend mode.")
    saved: bool = Field(default=False)
    document_id: UUID
    summary_id: UUID | None = None
    entity_ids: list[UUID] = Field(default_factory=list)
    document_entity_ids: list[UUID] = Field(default_factory=list)
    topic_ids: list[UUID] = Field(default_factory=list)
    document_topic_ids: list[UUID] = Field(default_factory=list)
    opportunity_ids: list[UUID] = Field(default_factory=list)
    opportunity_evidence_ids: list[UUID] = Field(default_factory=list)
    daily_brief_id: UUID | None = None
    notes: list[str] = Field(default_factory=list)


class ApplicationPipelineResult(BaseModel):
    document_id: UUID
    cleaned: CleanedDocument
    summary: BilingualSummary
    entities: list[EntityMention] = Field(default_factory=list)
    topics: list[TopicAssignment] = Field(default_factory=list)
    conflicts: list[ConflictRecord] = Field(default_factory=list)
    opportunities: list[OpportunityDraft] = Field(default_factory=list)
    daily_brief: DailyBriefDraft | None = None
    persisted: PersistedArtifacts | None = None


class ApplicationBatchSummaryInfo(BaseModel):
    title: str
    language: str | None = None
    entity_count: int
    topic_count: int
    opportunity_count: int
    daily_brief_generated: bool


class ApplicationBatchItemResult(BaseModel):
    success: bool
    document_id: UUID | None = None
    persisted: PersistedArtifacts | None = None
    summary_info: ApplicationBatchSummaryInfo | None = None
    error: str | None = None


class ApplicationBatchRunResult(BaseModel):
    transaction_mode: Literal["per_document"] = "per_document"
    persist: bool
    include_daily_brief: bool
    total: int
    succeeded: int
    failed: int
    error: str | None = None
    items: list[ApplicationBatchItemResult] = Field(default_factory=list)


@dataclass(slots=True)
class PipelineMappedArtifacts:
    processing: DocumentMappingBundle
    opportunities: list[OpportunityMappingBundle]
    daily_brief: DailyBrief | None
