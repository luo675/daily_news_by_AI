"""Service helpers for the minimal server-rendered Web MVP."""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import request

from sqlalchemy import Text, cast, desc, func, or_, select
from sqlalchemy.orm import Session, selectinload

from src.admin.review_schemas import ReviewEditCreate
from src.admin.review_service_db import DatabaseReviewService, RESET_TO_AUTO_SENTINEL
from src.application.orchestrator import DocumentPipelineOrchestrator
from src.config import (
    get_session_factory,
    probe_database_connection,
    probe_database_environment,
    probe_pgvector_extension,
)
from src.domain.enums import CredibilityLevel, PriorityLevel, SourceType, WatchlistStatus
from src.domain.models import (
    DailyBrief,
    Document,
    DocumentEntity,
    DocumentSummary,
    DocumentTopic,
    Entity,
    OpportunityAssessment,
    OpportunityEvidence,
    ReviewEdit,
    Source,
    Topic,
    WatchlistItem,
)
from src.ingestion.url_importer import import_url_as_raw_document
from src.web.provider_store import AiProviderConfigRecord
from src.web.qa_history_store import AskHistoryRecord

WEB_CONFIG_DIR = Path("configs/web")
AI_SETTINGS_PATH = WEB_CONFIG_DIR / "ai_settings.json"
QA_HISTORY_PATH = WEB_CONFIG_DIR / "qa_history.json"
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "into",
    "is", "it", "of", "on", "or", "that", "the", "their", "this", "to", "was", "were",
    "what", "when", "where", "which", "who", "why", "with", "you", "your", "about",
    "after", "before", "between", "during", "over", "under", "week", "today", "latest",
    "changed", "change", "changes",
}
_PROVIDER_TYPE_VALUES = {"openai_compatible"}
_MAINTENANCE_STATUS_VALUES = ("ordinary", "formal_seed", "deferred_candidate", "known_failure")
_WEB_ASSIGNABLE_MAINTENANCE_STATUS_VALUES = ("ordinary", "deferred_candidate", "known_failure")
_AI_TASK_VALUES = ("summarization", "analysis", "qa")
_QA_RETRIEVAL_LIMIT = 50
_QA_EVIDENCE_INSPECTION_LIMIT = 8
_QA_EVIDENCE_RETURN_LIMIT = 3
_OPPORTUNITY_REVIEW_FIELD_TO_ATTR = {
    "need_realness": "need_realness",
    "market_gap": "market_gap",
    "feasibility": "feasibility",
    "priority_score": "priority",
    "evidence_score": "evidence_score",
    "total_score": "total_score",
    "uncertainty": "uncertainty",
    "uncertainty_reason": "uncertainty_reason",
    "status": "status",
}
_OPPORTUNITY_REVIEW_FIELDS = tuple(_OPPORTUNITY_REVIEW_FIELD_TO_ATTR.keys())
_OPPORTUNITY_STATUS_VALUES = ("candidate", "confirmed", "dismissed", "watching")
_RISK_REVIEW_FIELDS = ("severity", "description")
_RISK_SEVERITY_VALUES = ("high", "medium", "low")
_UNCERTAINTY_REVIEW_FIELDS = ("uncertainty_note", "uncertainty_status")
_UNCERTAINTY_STATUS_VALUES = ("open", "watching", "resolved")
_SUMMARY_REVIEW_FIELDS = ("summary_zh", "summary_en", "key_points")
_UNCHANGED_UNCERTAINTY_STATUS = "__UNCHANGED__"
_NO_UNCERTAINTY_STATUS_CHANGE = object()


@dataclass(slots=True)
class ProviderConfig:
    id: str
    name: str
    provider_type: str
    base_url: str
    model: str
    api_key: str
    is_enabled: bool
    is_default: bool
    supported_tasks: list[str]
    notes: str
    last_test_status: str | None
    last_test_message: str | None
    updated_at: str

    @property
    def masked_key(self) -> str:
        if not self.api_key:
            return ""
        if len(self.api_key) <= 8:
            return "*" * len(self.api_key)
        return f"{self.api_key[:4]}...{self.api_key[-4:]}"


@dataclass(slots=True)
class SourceView:
    source: Source
    maintenance_status: str
    notes: str
    last_import_at: str | None
    last_result: str | None
    raw_config_json: str


@dataclass(slots=True)
class OpportunityReviewView:
    opportunity: OpportunityAssessment
    auto_values: dict[str, Any]
    effective_values: dict[str, Any]
    history: list[Any]
    source_document_title: str | None


@dataclass(slots=True)
class RiskReviewView:
    brief: DailyBrief
    risk_item: dict[str, Any]
    item_id: str
    route_id: str
    target_id: uuid.UUID
    auto_values: dict[str, Any]
    effective_values: dict[str, Any]
    history: list[Any]


@dataclass(slots=True)
class UncertaintyReviewView:
    brief: DailyBrief
    uncertainty_item: str
    item_id: str
    route_id: str
    target_id: uuid.UUID
    auto_values: dict[str, Any]
    effective_values: dict[str, Any]
    history: list[Any]


@dataclass(slots=True)
class SummaryReviewView:
    document: Document
    summary: DocumentSummary
    auto_values: dict[str, Any]
    effective_values: dict[str, Any]
    history: list[Any]


class WebMvpService:
    """Query and mutation helpers for server-rendered MVP pages."""

    def __init__(self) -> None:
        self._orchestrator = DocumentPipelineOrchestrator()

    def list_sources(self) -> tuple[list[Source], str | None]:
        return self._run_db_read(
            lambda session: list(
                session.scalars(select(Source).order_by(Source.updated_at.desc(), Source.name))
            ),
            empty=[],
        )

    def list_source_views(self) -> tuple[list[SourceView], str | None]:
        sources, error = self.list_sources()
        return [self._build_source_view(source) for source in sources], error

    def list_source_page_views(self) -> tuple[list[dict[str, Any]], str | None]:
        sources, error = self.list_sources()
        return [self._build_source_page_view(source) for source in sources], error

    def get_source(self, source_id: str) -> tuple[Source | None, str | None]:
        return self._run_db_read(
            lambda session: session.get(Source, uuid.UUID(source_id)),
            empty=None,
        )

    def get_source_view(self, source_id: str) -> tuple[SourceView | None, str | None]:
        source, error = self.get_source(source_id)
        if source is None:
            return None, error
        return self._build_source_view(source), error

    def get_source_page_view(self, source_id: str) -> tuple[dict[str, Any] | None, str | None]:
        source, error = self.get_source(source_id)
        if source is None:
            return None, error
        return self._build_source_page_view(source), error

    def create_source(self, form: dict[str, str]) -> str:
        session = self._require_session()
        try:
            source_type = self._validate_str_enum(
                form.get("source_type", ""),
                SourceType,
                label="source type",
            )
            credibility_level = self._validate_str_enum(
                form.get("credibility_level", "C"),
                CredibilityLevel,
                label="credibility level",
            )
            maintenance_status = self._validate_maintenance_status_for_web_edit(
                form.get("maintenance_status", "ordinary"),
                current_status=None,
            )
            config = self._parse_json_field(form.get("config_json"))
            config = self._set_source_web_metadata(
                config,
                maintenance_status=maintenance_status,
                notes=form.get("notes", "").strip(),
                last_import_at=None,
                last_result=None,
            )
            source = Source(
                name=form["name"].strip(),
                source_type=source_type,
                url=form.get("url", "").strip() or None,
                credibility_level=credibility_level,
                is_active=form.get("is_active") == "on",
                fetch_strategy=form.get("fetch_strategy", "manual").strip() or "manual",
                config=config,
            )
            session.add(source)
            session.commit()
            return "Source created."
        except ValueError as exc:
            session.rollback()
            return str(exc)
        except Exception as exc:
            session.rollback()
            return f"Failed to create source: {type(exc).__name__}: {exc}"
        finally:
            session.close()

    def update_source(self, source_id: str, form: dict[str, str]) -> str:
        session = self._require_session()
        try:
            source = session.get(Source, uuid.UUID(source_id))
            if source is None:
                return "Source not found."

            source.source_type = self._validate_str_enum(
                form.get("source_type", source.source_type),
                SourceType,
                label="source type",
            )
            source.credibility_level = self._validate_str_enum(
                form.get("credibility_level", source.credibility_level),
                CredibilityLevel,
                label="credibility level",
            )
            current_meta = self._get_source_web_metadata(source)
            current_status = current_meta.get("maintenance_status", "ordinary")
            maintenance_status = self._validate_maintenance_status_for_web_edit(
                form.get("maintenance_status", current_status),
                current_status=current_status,
            )

            source.name = form.get("name", source.name).strip()
            source.url = form.get("url", "").strip() or None
            source.fetch_strategy = form.get("fetch_strategy", source.fetch_strategy).strip() or source.fetch_strategy
            source.is_active = form.get("is_active") == "on"

            config = self._parse_json_field(form.get("config_json"))
            source.config = self._set_source_web_metadata(
                config,
                maintenance_status=maintenance_status,
                notes=form.get("notes", "").strip(),
                last_import_at=current_meta.get("last_import_at"),
                last_result=current_meta.get("last_result"),
            )
            session.commit()
            return "Source updated."
        except ValueError as exc:
            session.rollback()
            return str(exc)
        except Exception as exc:
            session.rollback()
            return f"Failed to update source: {type(exc).__name__}: {exc}"
        finally:
            session.close()

    def toggle_source(self, source_id: str) -> str:
        session = self._require_session()
        try:
            source = session.get(Source, uuid.UUID(source_id))
            if source is None:
                return "Source not found."
            source.is_active = not source.is_active
            session.commit()
            return f"Source {'enabled' if source.is_active else 'disabled'}."
        except Exception as exc:
            session.rollback()
            return f"Failed to update source: {type(exc).__name__}: {exc}"
        finally:
            session.close()

    def import_source(self, source_id: str) -> str:
        session = self._require_session()
        try:
            source = session.get(Source, uuid.UUID(source_id))
            if source is None:
                return "Source not found."
            if not source.url:
                return "Source has no URL to import."

            raw_document = import_url_as_raw_document(source.url)
            raw_document = raw_document.model_copy(
                update={
                    "source_name": source.name,
                    "source_type": SourceType(source.source_type),
                    "credibility_level": CredibilityLevel(source.credibility_level),
                }
            )
            result = self._orchestrator.run_document_pipeline(
                document=raw_document,
                persist=True,
                include_daily_brief=False,
                session=session,
            )
            document = session.get(Document, result.document_id)
            if document is not None:
                document.source_id = source.id
            source.config = self._set_source_web_metadata(
                source.config,
                maintenance_status=self._get_source_web_metadata(source).get("maintenance_status", "ordinary"),
                notes=self._get_source_web_metadata(source).get("notes", ""),
                last_import_at=datetime.now(timezone.utc).isoformat(),
                last_result=f"success: {result.document_id}",
            )
            session.commit()
            return f"Imported document {result.document_id} from source."
        except Exception as exc:
            session.rollback()
            try:
                source = session.get(Source, uuid.UUID(source_id))
                if source is not None:
                    meta = self._get_source_web_metadata(source)
                    source.config = self._set_source_web_metadata(
                        source.config,
                        maintenance_status=meta.get("maintenance_status", "ordinary"),
                        notes=meta.get("notes", ""),
                        last_import_at=datetime.now(timezone.utc).isoformat(),
                        last_result=f"failed: {type(exc).__name__}: {exc}",
                    )
                    session.commit()
            except Exception:
                session.rollback()
            return f"Source import failed: {type(exc).__name__}: {exc}"
        finally:
            session.close()

    def list_documents(self, query: str = "", source_id: str = "") -> tuple[list[Document], str | None]:
        def _query(session: Session) -> list[Document]:
            stmt = (
                select(Document)
                .options(
                    selectinload(Document.source),
                    selectinload(Document.summary),
                    selectinload(Document.document_entities).selectinload(DocumentEntity.entity),
                    selectinload(Document.document_topics).selectinload(DocumentTopic.topic),
                )
                .order_by(Document.created_at.desc())
                .limit(50)
            )
            if query.strip():
                pattern = f"%{query.strip()}%"
                stmt = stmt.where(
                    or_(
                        Document.title.ilike(pattern),
                        Document.content_text.ilike(pattern),
                        Document.url.ilike(pattern),
                    )
                )
            if source_id.strip():
                stmt = stmt.where(Document.source_id == uuid.UUID(source_id))
            return list(session.scalars(stmt))

        return self._run_db_read(_query, empty=[])

    def list_document_views(self, query: str = "", source_id: str = "") -> tuple[list[dict[str, Any]], str | None]:
        def _query(session: Session) -> list[dict[str, Any]]:
            stmt = (
                select(Document)
                .options(
                    selectinload(Document.source),
                    selectinload(Document.summary),
                    selectinload(Document.document_entities).selectinload(DocumentEntity.entity),
                    selectinload(Document.document_topics).selectinload(DocumentTopic.topic),
                )
                .order_by(Document.created_at.desc())
                .limit(50)
            )
            if query.strip():
                pattern = f"%{query.strip()}%"
                stmt = stmt.where(
                    or_(
                        Document.title.ilike(pattern),
                        Document.content_text.ilike(pattern),
                        Document.url.ilike(pattern),
                    )
                )
            if source_id.strip():
                stmt = stmt.where(Document.source_id == uuid.UUID(source_id))
            documents = list(session.scalars(stmt))
            review_service = DatabaseReviewService(session)
            return [self._build_document_list_view(document, review_service) for document in documents]

        return self._run_db_read(_query, empty=[])

    def get_document(self, document_id: str) -> tuple[Document | None, str | None]:
        def _query(session: Session) -> Document | None:
            stmt = (
                select(Document)
                .options(
                    selectinload(Document.source),
                    selectinload(Document.summary),
                    selectinload(Document.document_entities).selectinload(DocumentEntity.entity),
                    selectinload(Document.document_topics).selectinload(DocumentTopic.topic),
                )
                .where(Document.id == uuid.UUID(document_id))
            )
            return session.scalar(stmt)

        return self._run_db_read(_query, empty=None)

    def get_document_view(self, document_id: str) -> tuple[dict[str, Any] | None, str | None]:
        def _query(session: Session) -> dict[str, Any] | None:
            stmt = (
                select(Document)
                .options(
                    selectinload(Document.source),
                    selectinload(Document.summary),
                    selectinload(Document.document_entities).selectinload(DocumentEntity.entity),
                    selectinload(Document.document_topics).selectinload(DocumentTopic.topic),
                )
                .where(Document.id == uuid.UUID(document_id))
            )
            document = session.scalar(stmt)
            if document is None:
                return None
            review_service = DatabaseReviewService(session)
            return self._build_document_detail_view(document, review_service)

        return self._run_db_read(_query, empty=None)

    def list_review_documents(self) -> tuple[list[SummaryReviewView], str | None]:
        def _query(session: Session) -> list[SummaryReviewView]:
            stmt = (
                select(Document)
                .join(DocumentSummary, DocumentSummary.document_id == Document.id)
                .options(selectinload(Document.summary))
                .order_by(Document.updated_at.desc())
                .limit(20)
            )
            documents = list(session.scalars(stmt).unique())
            review_service = DatabaseReviewService(session)
            return [
                self._build_summary_review_view(review_service, document)
                for document in documents
                if document.summary is not None
            ]

        return self._run_db_read(_query, empty=[])

    def list_review_opportunities(self) -> tuple[list[OpportunityReviewView], str | None]:
        def _query(session: Session) -> list[OpportunityReviewView]:
            stmt = (
                select(OpportunityAssessment)
                .options(
                    selectinload(OpportunityAssessment.evidence_items).selectinload(
                        OpportunityEvidence.document
                    )
                )
                .order_by(OpportunityAssessment.updated_at.desc())
                .limit(20)
            )
            opportunities = list(session.scalars(stmt).unique())
            review_service = DatabaseReviewService(session)
            return [
                self._build_opportunity_review_view(review_service, opportunity)
                for opportunity in opportunities
            ]

        return self._run_db_read(_query, empty=[])

    def list_review_risks(self) -> tuple[list[RiskReviewView], str | None]:
        def _query(session: Session) -> list[RiskReviewView]:
            stmt = (
                select(DailyBrief)
                .where(DailyBrief.risks.is_not(None))
                .order_by(DailyBrief.updated_at.desc())
                .limit(20)
            )
            briefs = list(session.scalars(stmt).unique())
            review_service = DatabaseReviewService(session)
            views: list[RiskReviewView] = []
            for brief in briefs:
                for risk_item, item_id, target_id in self._iter_daily_brief_risk_entries(brief):
                    views.append(
                        self._build_risk_review_view(
                            review_service,
                            brief,
                            risk_item,
                            item_id=item_id,
                            target_id=target_id,
                        )
                    )
            return views

        return self._run_db_read(_query, empty=[])

    def list_review_uncertainties(self) -> tuple[list[UncertaintyReviewView], str | None]:
        def _query(session: Session) -> list[UncertaintyReviewView]:
            stmt = (
                select(DailyBrief)
                .where(DailyBrief.uncertainties.is_not(None))
                .order_by(DailyBrief.updated_at.desc())
                .limit(20)
            )
            briefs = list(session.scalars(stmt).unique())
            review_service = DatabaseReviewService(session)
            views: list[UncertaintyReviewView] = []
            for brief in briefs:
                for uncertainty_item, item_id, target_id in self._iter_daily_brief_uncertainty_entries(brief):
                    views.append(
                        self._build_uncertainty_review_view(
                            review_service,
                            brief,
                            uncertainty_item,
                            item_id=item_id,
                            target_id=target_id,
                        )
                    )
            return views

        return self._run_db_read(_query, empty=[])

    def _build_summary_review_view(
        self,
        review_service: DatabaseReviewService,
        document: Document,
    ) -> SummaryReviewView:
        summary = document.summary
        if summary is None:
            raise ValueError("Document summary is required for summary review view.")
        auto_values = self._get_summary_auto_values(summary)
        effective_values = self._get_summary_effective_values(summary, review_service)
        history = review_service.get_history("summary", summary.id).edits[:5]
        return SummaryReviewView(
            document=document,
            summary=summary,
            auto_values=auto_values,
            effective_values=effective_values,
            history=history,
        )

    def get_review_history(self, summary_id: uuid.UUID) -> list[ReviewEdit]:
        session = self._try_create_db_session()
        if session is None:
            return []
        try:
            stmt = (
                select(ReviewEdit)
                .where(
                    ReviewEdit.target_type == "summary",
                    ReviewEdit.target_id == summary_id,
                )
                .order_by(ReviewEdit.created_at.desc())
            )
            return list(session.scalars(stmt))
        except Exception:
            return []
        finally:
            session.close()

    def save_summary_review(self, summary_id: str, form: dict[str, str]) -> str:
        session = self._require_session()
        try:
            summary = session.get(DocumentSummary, uuid.UUID(summary_id))
            if summary is None:
                return "Summary not found."
            review_service = DatabaseReviewService(session)
            auto_values = self._get_summary_auto_values(summary)
            current_values = {
                field_name: review_service.get_effective_value(
                    "summary",
                    summary.id,
                    field_name,
                    auto_values[field_name],
                )
                for field_name in _SUMMARY_REVIEW_FIELDS
            }
            override_sources = {
                field_name: review_service.get_override_status(
                    "summary",
                    summary.id,
                    field_name,
                ).source
                for field_name in _SUMMARY_REVIEW_FIELDS
            }
            edits: list[ReviewEditCreate] = []

            for field_name in _SUMMARY_REVIEW_FIELDS:
                new_value = self._parse_summary_review_form_value(
                    field_name,
                    form,
                    override_source=override_sources[field_name],
                )
                if new_value == current_values[field_name]:
                    continue
                edits.append(
                    ReviewEditCreate(
                        field_name=field_name,
                        old_value=current_values[field_name],
                        new_value=new_value,
                        reason=form.get("reason") or "Web summary review update",
                        reviewer="owner",
                    )
                )
            if not edits:
                return "No summary changes detected."

            review_service.create_batch("summary", summary.id, edits, reason=form.get("reason"))
            return "Summary review saved."
        except Exception as exc:
            session.rollback()
            return f"Failed to save review: {type(exc).__name__}: {exc}"
        finally:
            session.close()

    def save_opportunity_review(self, opportunity_id: str, form: dict[str, str]) -> str:
        session = self._require_session()
        try:
            opportunity = session.get(OpportunityAssessment, uuid.UUID(opportunity_id))
            if opportunity is None:
                return "Opportunity not found."

            review_service = DatabaseReviewService(session)
            auto_values = self._get_opportunity_auto_values(opportunity)
            current_values = {
                field_name: review_service.get_effective_value(
                    "opportunity_score",
                    opportunity.id,
                    field_name,
                    auto_values[field_name],
                )
                for field_name in _OPPORTUNITY_REVIEW_FIELDS
            }
            override_sources = {
                field_name: review_service.get_override_status(
                    "opportunity_score",
                    opportunity.id,
                    field_name,
                ).source
                for field_name in _OPPORTUNITY_REVIEW_FIELDS
            }
            edits: list[ReviewEditCreate] = []

            for field_name in _OPPORTUNITY_REVIEW_FIELDS:
                new_value = self._parse_opportunity_review_form_value(
                    field_name,
                    form,
                    auto_value=auto_values[field_name],
                    override_source=override_sources[field_name],
                )
                if new_value == current_values[field_name]:
                    continue
                edits.append(
                    ReviewEditCreate(
                        field_name=field_name,
                        old_value=current_values[field_name],
                        new_value=new_value,
                        reason=form.get("reason") or "Web opportunity review update",
                        reviewer="owner",
                    )
                )

            if not edits:
                return "No opportunity changes detected."

            review_service.create_batch(
                "opportunity_score",
                opportunity.id,
                edits,
                reason=form.get("reason"),
            )
            return "Opportunity review saved."
        except ValueError as exc:
            session.rollback()
            return str(exc)
        except Exception as exc:
            session.rollback()
            return f"Failed to save review: {type(exc).__name__}: {exc}"
        finally:
            session.close()

    def save_risk_review(self, brief_id: str, route_id: str, form: dict[str, str]) -> str:
        session = self._require_session()
        try:
            brief = session.get(DailyBrief, uuid.UUID(brief_id))
            if brief is None:
                return "Risk brief not found."

            risk_entry = self._find_daily_brief_risk_entry_by_route_id(brief, route_id)
            if risk_entry is None:
                return "Risk item not found."
            risk_item, _, target_id = risk_entry

            review_service = DatabaseReviewService(session)
            auto_values = self._get_risk_auto_values(risk_item)
            current_values = {
                field_name: review_service.get_effective_value(
                    "risk",
                    target_id,
                    field_name,
                    auto_values[field_name],
                )
                for field_name in _RISK_REVIEW_FIELDS
            }
            override_sources = {
                field_name: review_service.get_override_status(
                    "risk",
                    target_id,
                    field_name,
                ).source
                for field_name in _RISK_REVIEW_FIELDS
            }
            edits: list[ReviewEditCreate] = []

            for field_name in _RISK_REVIEW_FIELDS:
                new_value = self._parse_risk_review_form_value(
                    field_name,
                    form,
                    override_source=override_sources[field_name],
                )
                if new_value == current_values[field_name]:
                    continue
                edits.append(
                    ReviewEditCreate(
                        field_name=field_name,
                        old_value=current_values[field_name],
                        new_value=new_value,
                        reason=form.get("reason") or "Web risk review update",
                        reviewer="owner",
                    )
                )

            if not edits:
                return "No risk changes detected."

            review_service.create_batch(
                "risk",
                target_id,
                edits,
                reason=form.get("reason"),
            )
            return "Risk review saved."
        except ValueError as exc:
            session.rollback()
            return str(exc)
        except Exception as exc:
            session.rollback()
            return f"Failed to save review: {type(exc).__name__}: {exc}"
        finally:
            session.close()

    def save_uncertainty_review(self, brief_id: str, route_id: str, form: dict[str, str]) -> str:
        session = self._require_session()
        try:
            brief = session.get(DailyBrief, uuid.UUID(brief_id))
            if brief is None:
                return "Uncertainty brief not found."

            uncertainty_entry = self._find_daily_brief_uncertainty_entry_by_route_id(brief, route_id)
            if uncertainty_entry is None:
                return "Uncertainty item not found."
            uncertainty_item, _, target_id = uncertainty_entry

            review_service = DatabaseReviewService(session)
            auto_values = self._get_uncertainty_auto_values(uncertainty_item)
            current_values = {
                field_name: review_service.get_effective_value(
                    "uncertainty",
                    target_id,
                    field_name,
                    auto_values[field_name],
                )
                for field_name in _UNCERTAINTY_REVIEW_FIELDS
            }
            override_sources = {
                field_name: review_service.get_override_status(
                    "uncertainty",
                    target_id,
                    field_name,
                ).source
                for field_name in _UNCERTAINTY_REVIEW_FIELDS
            }
            edits: list[ReviewEditCreate] = []

            for field_name in _UNCERTAINTY_REVIEW_FIELDS:
                new_value = self._parse_uncertainty_review_form_value(
                    field_name,
                    form,
                    override_source=override_sources[field_name],
                )
                if new_value is _NO_UNCERTAINTY_STATUS_CHANGE:
                    continue
                if new_value == current_values[field_name]:
                    continue
                edits.append(
                    ReviewEditCreate(
                        field_name=field_name,
                        old_value=current_values[field_name],
                        new_value=new_value,
                        reason=form.get("reason") or "Web uncertainty review update",
                        reviewer="owner",
                    )
                )

            if not edits:
                return "No uncertainty changes detected."

            review_service.create_batch(
                "uncertainty",
                target_id,
                edits,
                reason=form.get("reason"),
            )
            return "Uncertainty review saved."
        except ValueError as exc:
            session.rollback()
            return str(exc)
        except Exception as exc:
            session.rollback()
            return f"Failed to save review: {type(exc).__name__}: {exc}"
        finally:
            session.close()

    def list_watchlist_items(self) -> tuple[list[WatchlistItem], str | None]:
        return self._run_db_read(
            lambda session: list(
                session.scalars(
                    select(WatchlistItem)
                    .options(selectinload(WatchlistItem.entity))
                    .order_by(WatchlistItem.updated_at.desc(), WatchlistItem.item_value)
                )
            ),
            empty=[],
        )

    def create_watchlist_item(self, form: dict[str, str]) -> str:
        session = self._require_session()
        try:
            priority_level = self._validate_str_enum(
                form.get("priority_level", PriorityLevel.MEDIUM),
                PriorityLevel,
                label="watchlist priority",
            )
            item = WatchlistItem(
                item_type=form["item_type"].strip(),
                item_value=form["item_value"].strip(),
                priority_level=priority_level,
                group_name=form.get("group_name", "").strip() or None,
                status=WatchlistStatus.ACTIVE,
                notes=form.get("notes", "").strip() or None,
            )
            session.add(item)
            session.commit()
            return "Watchlist item created."
        except ValueError as exc:
            session.rollback()
            return str(exc)
        except Exception as exc:
            session.rollback()
            return f"Failed to create watchlist item: {type(exc).__name__}: {exc}"
        finally:
            session.close()

    def update_watchlist_status(self, item_id: str, status: str) -> str:
        session = self._require_session()
        try:
            validated_status = self._validate_str_enum(
                status,
                WatchlistStatus,
                label="watchlist status",
            )
            item = session.get(WatchlistItem, uuid.UUID(item_id))
            if item is None:
                return "Watchlist item not found."
            item.status = validated_status
            session.commit()
            return f"Watchlist item marked {validated_status}."
        except ValueError as exc:
            session.rollback()
            return str(exc)
        except Exception as exc:
            session.rollback()
            return f"Failed to update watchlist item: {type(exc).__name__}: {exc}"
        finally:
            session.close()

    def list_watchlist_hits(self, item_value: str) -> list[Document]:
        item_value = item_value.strip()
        if not item_value:
            return []

        session = self._try_create_db_session()
        if session is None:
            return []
        try:
            pattern = f"%{item_value}%"
            stmt = (
                select(Document)
                .options(selectinload(Document.summary), selectinload(Document.source))
                .where(
                    or_(
                        Document.title.ilike(pattern),
                        Document.content_text.ilike(pattern),
                        Document.url.ilike(pattern),
                    )
                )
                .order_by(Document.created_at.desc())
                .limit(10)
            )
            return list(session.scalars(stmt))
        except Exception:
            return []
        finally:
            session.close()

    def list_ai_providers(self) -> list[ProviderConfig]:
        records = self._list_ai_provider_records_from_db()
        if not records:
            records = self._read_json_records(AI_SETTINGS_PATH)
        providers: list[ProviderConfig] = []
        for record in records:
            providers.append(
                self._build_provider_config_from_record(record)
            )
        return providers

    def get_ai_provider(self, provider_id: str) -> ProviderConfig | None:
        for provider in self.list_ai_providers():
            if provider.id == provider_id:
                return provider
        return None

    def save_ai_provider(self, form: dict[str, str]) -> str:
        session = self._try_create_db_session()
        if session is not None:
            try:
                return self._save_ai_provider_to_db(session, form)
            except ValueError as exc:
                return str(exc)
            except Exception:
                try:
                    session.rollback()
                except Exception:
                    pass
            finally:
                session.close()
        try:
            providers = self._read_json_records(AI_SETTINGS_PATH)
            provider_id = form.get("provider_id") or str(uuid.uuid4())
            is_default = form.get("is_default") == "on"
            provider_type = self._validate_provider_type(form.get("provider_type", "openai_compatible"))
            supported_tasks = self._extract_supported_tasks(form)
            existing_record = next((provider for provider in providers if provider.get("id") == provider_id), None)
            submitted_api_key = form.get("api_key", "").strip()
            effective_api_key = submitted_api_key or (
                str(existing_record.get("api_key", "")).strip() if existing_record else ""
            )
            if is_default:
                for provider in providers:
                    provider["is_default"] = False

            record = {
                "id": provider_id,
                "name": form["name"].strip(),
                "provider_type": provider_type,
                "base_url": form.get("base_url", "https://api.openai.com/v1").strip() or "https://api.openai.com/v1",
                "model": form.get("model", "").strip(),
                "api_key": effective_api_key,
                "is_enabled": form.get("is_enabled") == "on",
                "is_default": is_default,
                "supported_tasks": supported_tasks,
                "notes": form.get("notes", "").strip(),
                "last_test_status": "valid" if form.get("model", "").strip() and effective_api_key else "incomplete",
                "last_test_message": "Configuration saved locally." if form.get("model", "").strip() else "Model is empty.",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            updated = False
            for index, provider in enumerate(providers):
                if provider["id"] == provider_id:
                    providers[index] = record
                    updated = True
                    break
            if not updated:
                if not any(provider.get("is_default") for provider in providers):
                    record["is_default"] = True
                providers.append(record)

            self._write_json_records(AI_SETTINGS_PATH, providers)
            return "AI provider saved."
        except ValueError as exc:
            return str(exc)

    def test_ai_provider(self, provider_id: str) -> str:
        session = self._try_create_db_session()
        if session is not None:
            try:
                db_message = self._test_ai_provider_in_db(session, provider_id)
                if db_message != "AI provider not found.":
                    return db_message
            except ValueError as exc:
                return str(exc)
            except Exception:
                try:
                    session.rollback()
                except Exception:
                    pass
            finally:
                session.close()
        providers = self._read_json_records(AI_SETTINGS_PATH)
        target_index = next((index for index, provider in enumerate(providers) if provider.get("id") == provider_id), None)
        if target_index is None:
            return "AI provider not found."

        provider = providers[target_index]
        provider_type = self._validate_provider_type(provider.get("provider_type", "openai_compatible"))
        base_url = str(provider.get("base_url", "")).strip()
        api_key = str(provider.get("api_key", "")).strip()
        model = str(provider.get("model", "")).strip()
        if not base_url or not api_key or not model:
            provider["last_test_status"] = "incomplete"
            provider["last_test_message"] = "Base URL, API key, and model are required for testing."
            provider["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._write_json_records(AI_SETTINGS_PATH, providers)
            return "Provider test recorded as incomplete."

        status = "failed"
        message = "Unknown provider test failure."
        try:
            if provider_type == "openai_compatible":
                endpoint = base_url.rstrip("/") + "/models"
                req = request.Request(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    method="GET",
                )
                with request.urlopen(req, timeout=20) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                data = payload.get("data", [])
                if isinstance(data, list):
                    status = "valid"
                    message = f"Connected successfully. Model configured: {model}."
                else:
                    message = "Provider responded without a valid model list."
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"

        provider["last_test_status"] = status
        provider["last_test_message"] = message
        provider["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_json_records(AI_SETTINGS_PATH, providers)
        return f"Provider test status: {status}."

    def ask_question(self, question: str, provider_id: str = "") -> dict[str, Any]:
        providers = self.list_ai_providers()
        provider = self._select_provider_for_task(providers, provider_id=provider_id, task="qa")
        documents, document_error = self.search_documents_for_question(question)
        briefs, brief_error = self.search_briefs_for_question(question)
        db_error = self._merge_error_messages(document_error, brief_error)
        evidence = self._build_ask_evidence(
            documents[:_QA_EVIDENCE_INSPECTION_LIMIT],
            briefs[:_QA_EVIDENCE_INSPECTION_LIMIT],
            question,
        )
        evidence_sufficient, sufficiency_note = self._assess_evidence_sufficiency(evidence)

        answer = ""
        answer_mode = "local_only"
        answer_error = db_error
        provider_used_name: str | None = None
        if not evidence_sufficient:
            answer = self._build_insufficient_evidence_answer(question, evidence, sufficiency_note)
            answer_mode = "insufficient_local_evidence"
        elif provider is not None and provider.is_enabled and provider.api_key and provider.model:
            try:
                answer = self._call_openai_compatible(provider, question, evidence, sufficiency_note)
                answer_mode = "local_with_external_reasoning"
                answer_error = None
                provider_used_name = provider.name
            except Exception as exc:
                answer = self._build_local_answer(question, evidence, sufficiency_note)
                answer_mode = "local_fallback"
                answer_error = f"{type(exc).__name__}: {exc}"
                provider_used_name = provider.name
        else:
            answer = self._build_local_answer(question, evidence, sufficiency_note)

        record = {
            "id": str(uuid.uuid4()),
            "question": question,
            "answer": answer,
            "answer_mode": answer_mode,
            "provider_name": provider_used_name,
            "error": answer_error,
            "note": sufficiency_note,
            "evidence": evidence,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._persist_qa_history_record(record)
        return record

    def list_qa_history(self) -> list[dict[str, Any]]:
        db_records = self._list_qa_history_from_db(limit=50)
        if not db_records:
            return self._read_json_records(QA_HISTORY_PATH)[:50]
        return db_records[:50]

    def get_dashboard_data(self) -> dict[str, Any]:
        counts = {
            "sources": 0,
            "documents": 0,
            "watchlist": 0,
            "reviews": 0,
        }
        recent_documents: list[dict[str, Any]] = []
        top_topics: list[tuple[str, int]] = []
        db_error = None
        session = self._try_create_db_session()
        if session is not None:
            try:
                counts["sources"] = int(session.scalar(select(func.count()).select_from(Source)) or 0)
                counts["documents"] = int(session.scalar(select(func.count()).select_from(Document)) or 0)
                counts["watchlist"] = int(session.scalar(select(func.count()).select_from(WatchlistItem)) or 0)
                counts["reviews"] = int(session.scalar(select(func.count()).select_from(ReviewEdit)) or 0)
                raw_recent_documents = list(
                    session.scalars(
                        select(Document)
                        .options(selectinload(Document.summary), selectinload(Document.source))
                        .order_by(Document.created_at.desc())
                        .limit(5)
                    )
                )
                review_service = DatabaseReviewService(session)
                recent_documents = [
                    self._build_dashboard_recent_document_view(document, review_service)
                    for document in raw_recent_documents
                ]
                topic_rows = session.execute(
                    select(Topic.name_en, func.count(DocumentTopic.id))
                    .join(DocumentTopic, DocumentTopic.topic_id == Topic.id)
                    .group_by(Topic.name_en)
                    .order_by(func.count(DocumentTopic.id).desc())
                    .limit(5)
                ).all()
                top_topics = [(name or "Unnamed", count) for name, count in topic_rows]
            except Exception as exc:
                db_error = f"{type(exc).__name__}: {exc}"
            finally:
                session.close()
        else:
            db_error = "Database session unavailable."

        providers = self.list_ai_providers()
        qa_history = self.list_qa_history()[:5]

        return {
            "counts": counts,
            "recent_documents": recent_documents,
            "top_topics": top_topics,
            "providers": providers,
            "qa_history": qa_history,
            "db_error": db_error,
            "system_status": self._build_dashboard_system_status(
                db_error=db_error,
                providers=providers,
                recent_documents=recent_documents,
            ),
        }

    def get_system_status(self) -> dict[str, Any]:
        environment_result = probe_database_environment()
        try:
            connection_result = probe_database_connection()
        except Exception as exc:
            connection_result = type("ProbeResult", (), {"ok": False, "detail": f"{type(exc).__name__}: {exc}"})()
        try:
            vector_result = probe_pgvector_extension()
        except Exception as exc:
            vector_result = type("ProbeResult", (), {"ok": False, "detail": f"{type(exc).__name__}: {exc}"})()

        file_status = []
        for path in [AI_SETTINGS_PATH, QA_HISTORY_PATH]:
            file_status.append(
                {
                    "path": str(path),
                    "exists": path.exists(),
                    "size_bytes": path.stat().st_size if path.exists() else 0,
                }
            )

        counts: dict[str, int] = {}
        counts_error: str | None = None
        session = self._try_create_db_session()
        if session is not None:
            try:
                counts = {
                    "sources": int(session.scalar(select(func.count()).select_from(Source)) or 0),
                    "documents": int(session.scalar(select(func.count()).select_from(Document)) or 0),
                    "summaries": int(session.scalar(select(func.count()).select_from(DocumentSummary)) or 0),
                    "entities": int(session.scalar(select(func.count()).select_from(Entity)) or 0),
                    "topics": int(session.scalar(select(func.count()).select_from(Topic)) or 0),
                    "watchlist": int(session.scalar(select(func.count()).select_from(WatchlistItem)) or 0),
                    "review_edits": int(session.scalar(select(func.count()).select_from(ReviewEdit)) or 0),
                }
            except Exception as exc:
                counts = {}
                counts_error = f"{type(exc).__name__}: {exc}"
            finally:
                session.close()
        else:
            counts_error = "Database session unavailable."

        return {
            "database_environment": environment_result,
            "database_connection": connection_result,
            "pgvector": vector_result,
            "files": file_status,
            "counts": counts,
            "counts_error": counts_error,
        }

    def get_system_page_data(self) -> dict[str, Any]:
        status = self.get_system_status()
        checks = [
            self._build_system_check_view("Database environment", status.get("database_environment")),
            self._build_system_check_view("Database connection", status.get("database_connection")),
            self._build_system_check_view("pgvector", status.get("pgvector")),
        ]
        storage_files = [
            {
                "path": self._coalesce_text(item.get("path"), default="-"),
                "exists_label": "yes" if bool(item.get("exists")) else "no",
                "size_bytes": int(item.get("size_bytes") or 0),
            }
            for item in status.get("files") or []
        ]
        database_counts = [
            {"name": str(name), "count": int(count)}
            for name, count in (status.get("counts") or {}).items()
        ]
        counts_error = None
        if not database_counts:
            counts_error = str(status.get("counts_error") or "").strip() or self._infer_system_counts_error(checks)
        return {
            "checks": checks,
            "database_counts": database_counts,
            "counts_error": counts_error,
            "storage_files": storage_files,
        }

    def list_source_type_values(self) -> list[str]:
        return [item.value for item in SourceType]

    def list_credibility_values(self) -> list[str]:
        return [item.value for item in CredibilityLevel]

    def list_watchlist_type_values(self) -> list[str]:
        return ["person", "company", "product", "model", "topic", "track", "keyword"]

    def list_priority_values(self) -> list[str]:
        return [item.value for item in PriorityLevel]

    def list_maintenance_status_values(self) -> list[str]:
        return list(_MAINTENANCE_STATUS_VALUES)

    def list_web_assignable_maintenance_status_values(self) -> list[str]:
        return list(_WEB_ASSIGNABLE_MAINTENANCE_STATUS_VALUES)

    def list_ai_task_values(self) -> list[str]:
        return list(_AI_TASK_VALUES)

    def search_documents_for_question(self, question: str) -> tuple[list[Document], str | None]:
        terms = self._build_query_terms(question)
        if not terms:
            return self.list_documents(query=question)

        def _query(session: Session) -> list[Document]:
            conditions = []
            for term in terms:
                pattern = f"%{term}%"
                conditions.extend(
                    [
                        Document.title.ilike(pattern),
                        Document.content_text.ilike(pattern),
                        Document.url.ilike(pattern),
                        DocumentSummary.summary_en.ilike(pattern),
                        DocumentSummary.summary_zh.ilike(pattern),
                        cast(DocumentSummary.key_points, Text).ilike(pattern),
                    ]
                )

            stmt = (
                select(Document)
                .outerjoin(DocumentSummary, DocumentSummary.document_id == Document.id)
                .options(
                    selectinload(Document.source),
                    selectinload(Document.summary),
                    selectinload(Document.document_entities).selectinload(DocumentEntity.entity),
                    selectinload(Document.document_topics).selectinload(DocumentTopic.topic),
                )
                .where(or_(*conditions))
                .limit(_QA_RETRIEVAL_LIMIT)
            )
            documents = list(session.scalars(stmt).unique())
            return self._rank_documents_by_terms(documents, terms)

        return self._run_db_read(_query, empty=[])

    def search_briefs_for_question(self, question: str) -> tuple[list[DailyBrief], str | None]:
        terms = self._build_query_terms(question)

        def _query(session: Session) -> list[DailyBrief]:
            stmt = (
                select(DailyBrief)
                .order_by(DailyBrief.updated_at.desc())
                .limit(_QA_RETRIEVAL_LIMIT)
            )
            if terms:
                conditions = []
                for term in terms:
                    pattern = f"%{term}%"
                    conditions.extend(
                        [
                            DailyBrief.summary_en.ilike(pattern),
                            DailyBrief.summary_zh.ilike(pattern),
                            DailyBrief.content_en.ilike(pattern),
                            DailyBrief.content_zh.ilike(pattern),
                            cast(DailyBrief.risks, Text).ilike(pattern),
                            cast(DailyBrief.uncertainties, Text).ilike(pattern),
                        ]
                    )
                stmt = stmt.where(or_(*conditions))
            return self._rank_briefs_by_terms(list(session.scalars(stmt).unique()), terms)

        return self._run_db_read(_query, empty=[])

    def _build_ask_evidence(
        self,
        documents: list[Document],
        briefs: list[DailyBrief],
        question: str,
    ) -> list[dict[str, Any]]:
        session = self._try_create_db_session()
        review_service = DatabaseReviewService(session) if session is not None else None
        try:
            evidence = self._build_evidence_from_documents(documents, question, review_service=review_service)
            evidence.extend(self._build_evidence_from_briefs(briefs, question, review_service=review_service))
            evidence.sort(key=lambda item: item["score"], reverse=True)
            return evidence[:_QA_EVIDENCE_RETURN_LIMIT]
        finally:
            if session is not None:
                session.close()

    def _build_evidence_from_documents(
        self,
        documents: list[Document],
        question: str,
        *,
        review_service: DatabaseReviewService | None = None,
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        question_terms = self._build_query_terms(question)
        opportunities_by_document = self._collect_opportunities_by_document(documents, review_service)
        for document in documents:
            summary_text = self._build_document_ask_summary(
                document,
                opportunities_by_document.get(document.id, []),
                review_service,
            )
            score, matched_terms = self._score_document_for_terms(
                document,
                question_terms,
                summary_text=summary_text,
                review_service=review_service,
            )
            if score <= 0:
                continue
            snippet, rendered_summary, match_basis = self._pick_snippet(
                document,
                question_terms,
                summary_text=summary_text,
                review_service=review_service,
            )
            evidence.append(
                {
                    "evidence_type": "document",
                    "document_id": str(document.id),
                    "title": document.title,
                    "source": document.source.name if document.source else None,
                    "summary": rendered_summary,
                    "snippet": snippet,
                    "match_basis": match_basis,
                    "matched_terms": matched_terms,
                    "score": score,
                    "url": document.url,
                }
            )
        evidence.sort(key=lambda item: item["score"], reverse=True)
        return evidence[:_QA_EVIDENCE_RETURN_LIMIT]

    def _build_evidence_from_briefs(
        self,
        briefs: list[DailyBrief],
        question: str,
        *,
        review_service: DatabaseReviewService | None = None,
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        question_terms = self._build_query_terms(question)
        for brief in briefs:
            summary_text = self._build_brief_ask_summary(brief, review_service)
            score, matched_terms = self._score_brief_for_terms(brief, question_terms, summary_text=summary_text)
            if score <= 0:
                continue
            snippet = self._clip_matching_text(summary_text, question_terms, default_size=220)
            if not snippet:
                snippet = self._clip_matching_text(
                    f"{brief.content_en or ''} {brief.content_zh or ''}",
                    question_terms,
                    default_size=220,
                )
            evidence.append(
                {
                    "evidence_type": "brief",
                    "document_id": None,
                    "brief_id": str(brief.id),
                    "title": f"Daily Brief {brief.brief_date.date()}",
                    "source": "Daily Brief",
                    "summary": summary_text,
                    "snippet": snippet or summary_text,
                    "match_basis": "summary" if summary_text else "content",
                    "matched_terms": matched_terms,
                    "score": score,
                    "url": None,
                }
            )
        evidence.sort(key=lambda item: item["score"], reverse=True)
        return evidence[:_QA_EVIDENCE_RETURN_LIMIT]

    def _pick_snippet(
        self,
        document: Document,
        question_terms: list[str],
        *,
        summary_text: str | None = None,
        review_service: DatabaseReviewService | None = None,
    ) -> tuple[str, str | None, str]:
        effective_key_points = []
        if document.summary is not None:
            effective_key_points = self._get_summary_effective_values(document.summary, review_service).get("key_points") or []
        key_point = self._pick_matching_line(effective_key_points, question_terms)
        if key_point:
            return key_point, summary_text or self._build_summary_text(document, review_service), "key_point"

        effective_summary = (
            summary_text if summary_text is not None else self._build_summary_text(document, review_service)
        )
        if effective_summary:
            summary_snippet = self._clip_matching_text(effective_summary, question_terms, default_size=220)
            if summary_snippet:
                return summary_snippet, effective_summary, "summary"

        content_snippet = self._clip_matching_text(document.content_text or "", question_terms, default_size=220)
        if content_snippet:
            return content_snippet, effective_summary or None, "content"

        fallback = effective_summary or self._clip_matching_text(document.content_text or "", question_terms, default_size=220)
        return fallback, effective_summary or None, "fallback"

    def _build_local_answer(self, question: str, evidence: list[dict[str, Any]], sufficiency_note: str) -> str:
        if not evidence:
            return (
                "No local evidence matched the question. Add sources, import documents, "
                "or broaden the query before relying on external reasoning."
            )
        lines = [f"Question: {question}", "", "Local evidence summary:"]
        for item in evidence[:_QA_EVIDENCE_RETURN_LIMIT]:
            lines.append(f"- {item['title']}: {item.get('snippet') or item.get('summary') or 'No snippet.'}")
        lines.append("")
        lines.append(f"Evidence note: {sufficiency_note}")
        lines.append("")
        lines.append("This answer is retrieval-first and synthesized locally because no external AI reply was used.")
        return "\n".join(lines)

    def _build_insufficient_evidence_answer(
        self,
        question: str,
        evidence: list[dict[str, Any]],
        sufficiency_note: str,
    ) -> str:
        lines = [
            f"Question: {question}",
            "",
            "Local knowledge does not currently provide enough evidence for a reliable answer.",
            f"Evidence note: {sufficiency_note}",
        ]
        if evidence:
            lines.extend(["", "Partial local matches:"])
            for item in evidence[:_QA_EVIDENCE_RETURN_LIMIT]:
                lines.append(f"- {item['title']}: {item.get('snippet') or item.get('summary') or 'No snippet.'}")
        lines.extend(
            [
                "",
                "Add or review more local sources before relying on external reasoning.",
            ]
        )
        return "\n".join(lines)

    def _call_openai_compatible(
        self,
        provider: ProviderConfig,
        question: str,
        evidence: list[dict[str, Any]],
        sufficiency_note: str,
    ) -> str:
        evidence_lines = []
        for item in evidence:
            evidence_lines.append(
                f"Title: {item['title']}\n"
                f"Source: {item.get('source') or 'unknown'}\n"
                f"Match basis: {item.get('match_basis') or 'unknown'}\n"
                f"Snippet: {item.get('snippet') or item.get('summary') or ''}"
            )
        payload = {
            "model": provider.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You answer strictly from provided local knowledge evidence. "
                        "Do not add outside facts. If evidence is insufficient, say so explicitly."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Question:\n{question}\n\n"
                        f"Evidence sufficiency note:\n{sufficiency_note}\n\n"
                        f"Local evidence:\n\n{chr(10).join(evidence_lines) or 'No evidence.'}"
                    ),
                },
            ],
            "temperature": 0.2,
        }
        body = json.dumps(payload).encode("utf-8")
        endpoint = provider.base_url.rstrip("/") + "/chat/completions"
        req = request.Request(
            endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {provider.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload["choices"][0]["message"]["content"].strip()

    def _select_provider_for_task(
        self,
        providers: list[ProviderConfig],
        *,
        provider_id: str,
        task: str,
    ) -> ProviderConfig | None:
        enabled = [provider for provider in providers if provider.is_enabled and task in provider.supported_tasks]
        if provider_id:
            for provider in enabled:
                if provider.id == provider_id:
                    return provider
            return None
        for provider in enabled:
            if provider.is_default:
                return provider
        return enabled[0] if enabled else None

    def _tokenize(self, value: str) -> list[str]:
        return [token.lower() for token in _TOKEN_PATTERN.findall(value or "") if token.strip()]

    def _build_query_terms(self, value: str) -> list[str]:
        seen: set[str] = set()
        terms: list[str] = []
        for token in self._tokenize(value):
            if token in seen:
                continue
            if token in _STOPWORDS:
                continue
            if token.isdigit():
                continue
            if len(token) < 3 and token.isascii():
                continue
            seen.add(token)
            terms.append(token)
        return terms

    def _rank_documents_by_terms(self, documents: list[Document], terms: list[str]) -> list[Document]:
        scored: list[tuple[int, datetime, Document]] = []
        for document in documents:
            score, _ = self._score_document_for_terms(document, terms)
            recency = document.created_at or datetime.fromtimestamp(0, tz=timezone.utc)
            scored.append((score, recency, document))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [document for score, _, document in scored if score > 0]

    def _rank_briefs_by_terms(self, briefs: list[DailyBrief], terms: list[str]) -> list[DailyBrief]:
        scored: list[tuple[int, datetime, DailyBrief]] = []
        for brief in briefs:
            score, _ = self._score_brief_for_terms(brief, terms)
            recency = brief.updated_at or brief.brief_date or datetime.fromtimestamp(0, tz=timezone.utc)
            scored.append((score, recency, brief))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [brief for score, _, brief in scored if score > 0] if terms else [brief for _, _, brief in scored]

    def _score_document_for_terms(
        self,
        document: Document,
        terms: list[str],
        *,
        summary_text: str | None = None,
        review_service: DatabaseReviewService | None = None,
    ) -> tuple[int, int]:
        if not terms:
            return (0, 0)

        title_text = (document.title or "").lower()
        content_text = (document.content_text or "").lower()
        url_text = (document.url or "").lower()
        summary_text = (
            summary_text if summary_text is not None else self._build_summary_text(document, review_service)
        ).lower()
        key_points_text = self._build_key_points_text(document, review_service).lower()

        summary_matches = 0
        title_matches = 0
        content_matches = 0
        url_matches = 0
        for term in terms:
            if term in key_points_text or term in summary_text:
                summary_matches += 1
            if term in title_text:
                title_matches += 1
            if term in content_text:
                content_matches += 1
            if term in url_text:
                url_matches += 1

        score = (summary_matches * 6) + (title_matches * 4) + (content_matches * 2) + url_matches
        matched_terms = summary_matches + title_matches + content_matches + url_matches
        return score, matched_terms

    def _score_brief_for_terms(
        self,
        brief: DailyBrief,
        terms: list[str],
        *,
        summary_text: str | None = None,
    ) -> tuple[int, int]:
        if not terms:
            return (0, 0)

        effective_summary = (summary_text if summary_text is not None else self._build_brief_search_text(brief)).lower()
        content_text = self._build_brief_search_text(brief).lower()
        summary_matches = 0
        content_matches = 0
        for term in terms:
            if term in effective_summary:
                summary_matches += 1
            if term in content_text:
                content_matches += 1
        score = (summary_matches * 6) + (content_matches * 2)
        matched_terms = summary_matches + content_matches
        return score, matched_terms

    def _build_summary_text(
        self,
        document: Document,
        review_service: DatabaseReviewService | None = None,
    ) -> str:
        if document.summary is None:
            return ""
        effective_values = self._get_summary_effective_values(document.summary, review_service)
        return str(effective_values.get("summary_en") or effective_values.get("summary_zh") or "")

    def _build_document_summary_text(
        self,
        document: Document,
        review_service: DatabaseReviewService | None = None,
    ) -> str:
        summary_text = self._build_summary_text(document, review_service).strip()
        if summary_text:
            return summary_text
        if document.summary is None:
            return ""
        effective_values = self._get_summary_effective_values(document.summary, review_service)
        key_points = effective_values.get("key_points") or []
        normalized_key_points = [str(point).strip() for point in key_points if str(point).strip()]
        return "; ".join(normalized_key_points)

    def _get_summary_auto_values(self, summary: DocumentSummary) -> dict[str, Any]:
        return {
            "summary_zh": summary.summary_zh,
            "summary_en": summary.summary_en,
            "key_points": list(summary.key_points or []),
        }

    def _get_summary_effective_values(
        self,
        summary: DocumentSummary,
        review_service: DatabaseReviewService | None,
    ) -> dict[str, Any]:
        auto_values = self._get_summary_auto_values(summary)
        if review_service is None:
            return auto_values
        return {
            field_name: review_service.get_effective_value(
                "summary",
                summary.id,
                field_name,
                auto_values[field_name],
            )
            for field_name in _SUMMARY_REVIEW_FIELDS
        }

    def _parse_summary_review_form_value(
        self,
        field_name: str,
        form: dict[str, str],
        *,
        override_source: str,
    ) -> Any:
        reset_requested = form.get(f"reset_{field_name}") == "on"
        raw_value = form.get(field_name, "")
        if reset_requested:
            return RESET_TO_AUTO_SENTINEL
        if field_name == "key_points":
            return [line.strip() for line in str(raw_value).splitlines() if line.strip()]
        value = str(raw_value).strip()
        if value == "" and override_source == "manual":
            return None
        return value or None

    def _build_document_ask_summary(
        self,
        document: Document,
        opportunities: list[OpportunityAssessment],
        review_service: DatabaseReviewService | None,
    ) -> str:
        base_summary = self._build_summary_text(document, review_service)
        reviewed_opportunities = self._build_reviewed_opportunity_summary(opportunities, review_service)
        if reviewed_opportunities and base_summary:
            return f"{base_summary}\n\nReviewed opportunities: {reviewed_opportunities}"
        if reviewed_opportunities:
            return f"Reviewed opportunities: {reviewed_opportunities}"
        return base_summary

    def _build_key_points_text(
        self,
        document: Document,
        review_service: DatabaseReviewService | None = None,
    ) -> str:
        if document.summary is None:
            return ""
        effective_values = self._get_summary_effective_values(document.summary, review_service)
        key_points = effective_values.get("key_points") or []
        return " ".join(str(point).strip() for point in key_points if str(point).strip())

    def _build_document_list_view(
        self,
        document: Document,
        review_service: DatabaseReviewService | None = None,
    ) -> dict[str, Any]:
        key_points = self._get_document_effective_key_points(document, review_service)
        return {
            "id": str(document.id),
            "title": self._coalesce_text(document.title, default="Untitled document"),
            "source_name": self._coalesce_text(document.source.name if document.source else None),
            "status": self._coalesce_text(document.status),
            "language": self._coalesce_text(document.language),
            "published_at": self._coalesce_text(str(document.published_at) if document.published_at else None),
            "summary_text": self._coalesce_text(
                self._truncate_text(self._build_document_summary_text(document, review_service), limit=160)
            ),
            "key_points": key_points,
            "created_at": self._coalesce_text(str(document.created_at) if document.created_at else None),
        }

    def _build_document_detail_view(
        self,
        document: Document,
        review_service: DatabaseReviewService | None = None,
    ) -> dict[str, Any]:
        effective_values = (
            self._get_summary_effective_values(document.summary, review_service)
            if document.summary is not None
            else {"summary_en": "", "summary_zh": "", "key_points": []}
        )
        entity_labels = [self._build_entity_label(link.entity) for link in document.document_entities or []]
        topic_labels = [self._build_topic_label(link.topic) for link in document.document_topics or []]
        return {
            "id": str(document.id),
            "title": self._coalesce_text(document.title, default="Untitled document"),
            "source_name": self._coalesce_text(document.source.name if document.source else None),
            "url": self._coalesce_text(document.url, default=""),
            "status": self._coalesce_text(document.status),
            "language": self._coalesce_text(document.language),
            "published_at": self._coalesce_text(str(document.published_at) if document.published_at else None),
            "summary_en": self._coalesce_text(effective_values.get("summary_en"), default=""),
            "summary_zh": self._coalesce_text(effective_values.get("summary_zh"), default=""),
            "key_points": self._normalize_string_list(effective_values.get("key_points")),
            "entities": entity_labels,
            "topics": topic_labels,
            "content_preview": self._coalesce_text(
                self._truncate_text(document.content_text or "", limit=2400),
                default="",
            ),
        }

    def _build_dashboard_recent_document_view(
        self,
        document: Document,
        review_service: DatabaseReviewService | None = None,
    ) -> dict[str, Any]:
        summary_text = self._build_document_summary_text(document, review_service)
        return {
            "id": str(document.id),
            "title": self._coalesce_text(document.title, default="Untitled document"),
            "source_name": self._coalesce_text(document.source.name if document.source else None),
            "created_at": self._coalesce_text(str(document.created_at) if document.created_at else None),
            "published_at": self._coalesce_text(str(document.published_at) if document.published_at else None),
            "status": self._coalesce_text(document.status),
            "summary_text": self._coalesce_text(self._truncate_text(summary_text, limit=160), default="-"),
        }

    def _build_dashboard_system_status(
        self,
        *,
        db_error: str | None,
        providers: list[ProviderConfig],
        recent_documents: list[dict[str, Any]],
    ) -> dict[str, str]:
        enabled_providers = [provider for provider in providers if provider.is_enabled]
        if db_error:
            database_label = "degraded"
            database_detail = db_error
            knowledge_label = "Recent knowledge changes are unavailable."
        else:
            database_label = "available"
            database_detail = "Counts and recent knowledge changes are available."
            knowledge_label = self._format_dashboard_knowledge_label(recent_documents)
        provider_label = self._format_dashboard_provider_label(enabled_providers, providers)
        return {
            "database_label": database_label,
            "database_detail": database_detail,
            "provider_label": provider_label,
            "knowledge_label": knowledge_label,
        }

    def _format_dashboard_provider_label(
        self,
        enabled_providers: list[ProviderConfig],
        providers: list[ProviderConfig],
    ) -> str:
        if enabled_providers:
            count = len(enabled_providers)
            noun = "provider" if count == 1 else "providers"
            return f"{count} {noun} enabled"
        if providers:
            return "Providers configured but currently disabled"
        return "No provider configured"

    def _format_dashboard_knowledge_label(self, recent_documents: list[dict[str, Any]]) -> str:
        count = len(recent_documents)
        if count == 0:
            return "No recent knowledge changes yet."
        noun = "document" if count == 1 else "documents"
        return f"{count} recent {noun} available in the dashboard"

    def _build_system_check_view(self, label: str, result: Any) -> dict[str, str]:
        ok = bool(getattr(result, "ok", False))
        detail = self._coalesce_text(getattr(result, "detail", None))
        return {
            "label": label,
            "status": "available" if ok else "degraded",
            "detail": detail,
        }

    def _infer_system_counts_error(self, checks: list[dict[str, str]]) -> str | None:
        degraded_details = [
            check["detail"]
            for check in checks
            if check.get("status") == "degraded" and str(check.get("detail") or "").strip()
        ]
        if degraded_details:
            return degraded_details[0]
        return None

    def _get_document_effective_key_points(
        self,
        document: Document,
        review_service: DatabaseReviewService | None = None,
    ) -> list[str]:
        if document.summary is None:
            return []
        effective_values = self._get_summary_effective_values(document.summary, review_service)
        return self._normalize_string_list(effective_values.get("key_points"))

    def _build_entity_label(self, entity: Entity | None) -> str:
        if entity is None:
            return "Unnamed entity"
        name = self._coalesce_text(getattr(entity, "name", None), default="")
        entity_type = self._coalesce_text(getattr(entity, "entity_type", None), default="")
        if name and entity_type:
            return f"{name} ({entity_type})"
        if name:
            return name
        return "Unnamed entity"

    def _build_topic_label(self, topic: Topic | None) -> str:
        if topic is None:
            return "Unnamed topic"
        label = self._coalesce_text(
            getattr(topic, "name_en", None) or getattr(topic, "name_zh", None),
            default="",
        )
        return label or "Unnamed topic"

    def _normalize_string_list(self, value: Any, *, fallback: str | None = None) -> list[str]:
        items = value if isinstance(value, list) else []
        normalized = [str(item).strip() for item in items if str(item).strip()]
        if normalized:
            return normalized
        return [fallback] if fallback else []

    def _coalesce_text(self, value: Any, *, default: str = "-") -> str:
        text = str(value or "").strip()
        return text or default

    def _truncate_text(self, value: Any, *, limit: int) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return f"{text[: max(limit - 1, 0)].rstrip()}..."

    def _build_brief_search_text(self, brief: DailyBrief) -> str:
        values = [
            brief.summary_en or "",
            brief.summary_zh or "",
            brief.content_en or "",
            brief.content_zh or "",
            json.dumps(brief.risks or [], ensure_ascii=False),
            json.dumps(brief.uncertainties or [], ensure_ascii=False),
        ]
        return " ".join(value for value in values if value).strip()

    def _build_brief_ask_summary(
        self,
        brief: DailyBrief,
        review_service: DatabaseReviewService | None,
    ) -> str:
        sections = []
        base_summary = brief.summary_en or brief.summary_zh or ""
        if base_summary:
            sections.append(base_summary)

        reviewed_risks = self._build_reviewed_risk_summary(brief, review_service)
        if reviewed_risks:
            sections.append(f"Reviewed risks: {reviewed_risks}")

        reviewed_uncertainties = self._build_reviewed_uncertainty_summary(brief, review_service)
        if reviewed_uncertainties:
            sections.append(f"Reviewed uncertainties: {reviewed_uncertainties}")

        if sections:
            return "\n\n".join(sections)
        return self._build_brief_search_text(brief)

    def _pick_matching_line(self, values: list[Any], question_terms: list[str]) -> str | None:
        cleaned_values = [str(value).strip() for value in values if str(value).strip()]
        for value in cleaned_values:
            lowered = value.lower()
            if any(term in lowered for term in question_terms):
                return value
        return None

    def _clip_matching_text(self, text: str, question_terms: list[str], *, default_size: int) -> str:
        normalized = (text or "").replace("\n", " ").strip()
        if not normalized:
            return ""
        lowered = normalized.lower()
        for term in question_terms:
            index = lowered.find(term.lower())
            if index >= 0:
                start = max(0, index - 80)
                end = min(len(normalized), index + default_size)
                return normalized[start:end].strip()
        return normalized[:default_size].strip()

    def _merge_error_messages(self, *messages: str | None) -> str | None:
        cleaned = [message for message in messages if message]
        if not cleaned:
            return None
        return "; ".join(cleaned)

    def _assess_evidence_sufficiency(self, evidence: list[dict[str, Any]]) -> tuple[bool, str]:
        if not evidence:
            return False, "No local evidence matched the question."

        strong_items = [
            item
            for item in evidence
            if item.get("match_basis") in {"key_point", "summary", "content"} and int(item.get("score", 0)) >= 6
        ]
        total_matched_terms = sum(int(item.get("matched_terms", 0)) for item in evidence)

        if len(strong_items) >= 2:
            return True, "Multiple local evidence items matched the question."
        if strong_items and total_matched_terms >= 2 and strong_items[0].get("match_basis") in {"key_point", "summary"}:
            return True, "A focused local summary/key-point match was found."
        return False, "Only weak or partial local evidence was found."

    def _build_opportunity_review_view(
        self,
        review_service: DatabaseReviewService,
        opportunity: OpportunityAssessment,
    ) -> OpportunityReviewView:
        auto_values = self._get_opportunity_auto_values(opportunity)
        effective_values = {
            field_name: review_service.get_effective_value(
                "opportunity_score",
                opportunity.id,
                field_name,
                auto_values[field_name],
            )
            for field_name in _OPPORTUNITY_REVIEW_FIELDS
        }
        history = review_service.get_history("opportunity_score", opportunity.id).edits[:5]
        return OpportunityReviewView(
            opportunity=opportunity,
            auto_values=auto_values,
            effective_values=effective_values,
            history=history,
            source_document_title=self._pick_opportunity_source_document_title(opportunity),
        )

    def _get_opportunity_auto_values(self, opportunity: OpportunityAssessment) -> dict[str, Any]:
        return {
            field_name: getattr(opportunity, attr_name)
            for field_name, attr_name in _OPPORTUNITY_REVIEW_FIELD_TO_ATTR.items()
        }

    def _pick_opportunity_source_document_title(self, opportunity: OpportunityAssessment) -> str | None:
        for evidence_item in getattr(opportunity, "evidence_items", []) or []:
            document = getattr(evidence_item, "document", None)
            if document is not None and document.title:
                return document.title
        fallback_document = getattr(opportunity, "_review_test_document", None)
        if fallback_document is not None:
            return getattr(fallback_document, "title", None)
        return None

    def _collect_opportunities_by_document(
        self,
        documents: list[Document],
        review_service: DatabaseReviewService | None,
    ) -> dict[uuid.UUID, list[OpportunityAssessment]]:
        opportunities_by_document: dict[uuid.UUID, list[OpportunityAssessment]] = {
            document.id: [] for document in documents
        }
        document_ids = [document.id for document in documents]
        if not document_ids:
            return opportunities_by_document

        for document in documents:
            for opportunity in getattr(document, "_ask_test_opportunities", []) or []:
                opportunities_by_document.setdefault(document.id, []).append(opportunity)

        if review_service is None or not hasattr(review_service.session, "scalars"):
            return opportunities_by_document

        stmt = (
            select(OpportunityAssessment)
            .join(OpportunityEvidence, OpportunityEvidence.opportunity_id == OpportunityAssessment.id)
            .options(selectinload(OpportunityAssessment.evidence_items))
            .where(OpportunityEvidence.document_id.in_(document_ids))
            .order_by(OpportunityAssessment.updated_at.desc())
        )
        opportunities = list(review_service.session.scalars(stmt).unique())
        for opportunity in opportunities:
            linked_document_ids = {
                evidence_item.document_id
                for evidence_item in opportunity.evidence_items or []
                if evidence_item.document_id in opportunities_by_document
            }
            for document_id in linked_document_ids:
                if all(existing.id != opportunity.id for existing in opportunities_by_document[document_id]):
                    opportunities_by_document[document_id].append(opportunity)
        return opportunities_by_document

    def _build_reviewed_opportunity_summary(
        self,
        opportunities: list[OpportunityAssessment],
        review_service: DatabaseReviewService | None,
    ) -> str:
        rendered: list[str] = []
        for opportunity in opportunities:
            auto_values = self._get_opportunity_auto_values(opportunity)
            effective_values = {
                field_name: (
                    review_service.get_effective_value("opportunity_score", opportunity.id, field_name, auto_value)
                    if review_service is not None
                    else auto_value
                )
                for field_name, auto_value in auto_values.items()
            }
            title = opportunity.title_en or opportunity.title_zh or "Untitled opportunity"
            details = [
                f"status={effective_values.get('status')}",
                f"priority_score={effective_values.get('priority_score')}",
                f"total_score={effective_values.get('total_score')}",
                f"uncertainty={effective_values.get('uncertainty')}",
            ]
            if effective_values.get("uncertainty_reason"):
                details.append(f"uncertainty_reason={effective_values['uncertainty_reason']}")
            rendered.append(f"{title} ({', '.join(details)})")
        return " | ".join(rendered)

    def _parse_opportunity_review_form_value(
        self,
        field_name: str,
        form: dict[str, str],
        *,
        auto_value: Any,
        override_source: str,
    ) -> Any:
        raw_value = form.get(field_name, "")
        reset_requested = form.get(f"reset_{field_name}") == "on"
        value = str(raw_value).strip()
        if reset_requested or (value == "" and override_source == "manual" and field_name != "uncertainty"):
            return RESET_TO_AUTO_SENTINEL
        if field_name in {"need_realness", "market_gap", "feasibility", "priority_score", "evidence_score"}:
            if not value:
                return None
            parsed = int(value)
            if not 1 <= parsed <= 10:
                raise ValueError(f"{field_name} must be between 1 and 10.")
            return parsed
        if field_name == "total_score":
            return float(value) if value else None
        if field_name == "uncertainty":
            lowered = value.lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off", ""}:
                return False
            raise ValueError("uncertainty must be true or false.")
        if field_name == "status":
            if value not in _OPPORTUNITY_STATUS_VALUES:
                allowed = ", ".join(_OPPORTUNITY_STATUS_VALUES)
                raise ValueError(f"Invalid opportunity status: {value!r}. Allowed values: {allowed}.")
            return value
        return value or None

    def _build_risk_review_view(
        self,
        review_service: DatabaseReviewService,
        brief: DailyBrief,
        risk_item: dict[str, Any],
        *,
        item_id: str,
        target_id: uuid.UUID,
    ) -> RiskReviewView:
        auto_values = self._get_risk_auto_values(risk_item)
        effective_values = {
            field_name: review_service.get_effective_value(
                "risk",
                target_id,
                field_name,
                auto_values[field_name],
            )
            for field_name in _RISK_REVIEW_FIELDS
        }
        history = review_service.get_history("risk", target_id).edits[:5]
        return RiskReviewView(
            brief=brief,
            risk_item=risk_item,
            item_id=item_id,
            route_id=str(target_id),
            target_id=target_id,
            auto_values=auto_values,
            effective_values=effective_values,
            history=history,
        )

    def _build_daily_brief_risk_item_id(self, risk_item: dict[str, Any]) -> str:
        return self._build_daily_brief_risk_base_item_id(risk_item)

    def _build_daily_brief_risk_base_item_id(self, risk_item: dict[str, Any]) -> str:
        existing = str(risk_item.get("item_id") or "").strip()
        if existing:
            return existing
        title = str(risk_item.get("title") or "").strip()
        description = str(risk_item.get("description") or "").strip()
        severity = str(risk_item.get("severity") or "").strip()
        seed = f"{title}|{description}|{severity}"
        return uuid.uuid5(uuid.NAMESPACE_URL, seed).hex

    def _build_daily_brief_risk_target_id(self, brief_id: uuid.UUID, item_id: str) -> uuid.UUID:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"{brief_id}:risk:{item_id}")

    def _iter_daily_brief_risk_entries(
        self,
        brief: DailyBrief,
    ) -> list[tuple[dict[str, Any], str, uuid.UUID]]:
        entries: list[tuple[dict[str, Any], str, uuid.UUID]] = []
        seen_counts: dict[str, int] = {}
        for risk_item in brief.risks or []:
            if not isinstance(risk_item, dict):
                continue
            base_item_id = self._build_daily_brief_risk_base_item_id(risk_item)
            occurrence = seen_counts.get(base_item_id, 0)
            seen_counts[base_item_id] = occurrence + 1
            item_id = f"{base_item_id}:{occurrence}"
            entries.append((risk_item, item_id, self._build_daily_brief_risk_target_id(brief.id, item_id)))
        return entries

    def _find_daily_brief_risk_entry_by_route_id(
        self,
        brief: DailyBrief,
        route_id: str,
    ) -> tuple[dict[str, Any], str, uuid.UUID] | None:
        for risk_item, item_id, target_id in self._iter_daily_brief_risk_entries(brief):
            if str(target_id) == route_id:
                return risk_item, item_id, target_id
        return None

    def _get_risk_auto_values(self, risk_item: dict[str, Any]) -> dict[str, Any]:
        return {
            "severity": risk_item.get("severity"),
            "description": risk_item.get("description"),
        }

    def _build_reviewed_risk_summary(
        self,
        brief: DailyBrief,
        review_service: DatabaseReviewService | None,
    ) -> str:
        rendered: list[str] = []
        for risk_item, _, target_id in self._iter_daily_brief_risk_entries(brief):
            auto_values = self._get_risk_auto_values(risk_item)
            effective_values = {
                field_name: (
                    review_service.get_effective_value("risk", target_id, field_name, auto_value)
                    if review_service is not None
                    else auto_value
                )
                for field_name, auto_value in auto_values.items()
            }
            title = str(risk_item.get("title") or "Untitled risk")
            rendered.append(
                f"{title} (severity={effective_values.get('severity')}, description={effective_values.get('description')})"
            )
        return " | ".join(rendered)

    def _parse_risk_review_form_value(
        self,
        field_name: str,
        form: dict[str, str],
        *,
        override_source: str,
    ) -> Any:
        raw_value = form.get(field_name, "")
        reset_requested = form.get(f"reset_{field_name}") == "on"
        value = str(raw_value).strip()
        if reset_requested or (value == "" and override_source == "manual"):
            return RESET_TO_AUTO_SENTINEL
        if field_name == "severity":
            if value not in _RISK_SEVERITY_VALUES:
                allowed = ", ".join(_RISK_SEVERITY_VALUES)
                raise ValueError(f"Invalid risk severity: {value!r}. Allowed values: {allowed}.")
            return value
        return value or None

    def _build_uncertainty_review_view(
        self,
        review_service: DatabaseReviewService,
        brief: DailyBrief,
        uncertainty_item: str,
        *,
        item_id: str,
        target_id: uuid.UUID,
    ) -> UncertaintyReviewView:
        auto_values = self._get_uncertainty_auto_values(uncertainty_item)
        effective_values = {
            field_name: review_service.get_effective_value(
                "uncertainty",
                target_id,
                field_name,
                auto_values[field_name],
            )
            for field_name in _UNCERTAINTY_REVIEW_FIELDS
        }
        history = review_service.get_history("uncertainty", target_id).edits[:5]
        return UncertaintyReviewView(
            brief=brief,
            uncertainty_item=uncertainty_item,
            item_id=item_id,
            route_id=str(target_id),
            target_id=target_id,
            auto_values=auto_values,
            effective_values=effective_values,
            history=history,
        )

    def _build_daily_brief_uncertainty_item_id(self, uncertainty_item: str) -> str:
        normalized = str(uncertainty_item or "").strip()
        return uuid.uuid5(uuid.NAMESPACE_URL, normalized).hex

    def _build_daily_brief_uncertainty_target_id(self, brief_id: uuid.UUID, item_id: str) -> uuid.UUID:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"{brief_id}:uncertainty:{item_id}")

    def _iter_daily_brief_uncertainty_entries(
        self,
        brief: DailyBrief,
    ) -> list[tuple[str, str, uuid.UUID]]:
        entries: list[tuple[str, str, uuid.UUID]] = []
        seen_counts: dict[str, int] = {}
        for uncertainty_item in brief.uncertainties or []:
            normalized = str(uncertainty_item or "").strip()
            if not normalized:
                continue
            base_item_id = self._build_daily_brief_uncertainty_item_id(normalized)
            occurrence = seen_counts.get(base_item_id, 0)
            seen_counts[base_item_id] = occurrence + 1
            item_id = f"{base_item_id}:{occurrence}"
            entries.append(
                (
                    normalized,
                    item_id,
                    self._build_daily_brief_uncertainty_target_id(brief.id, item_id),
                )
            )
        return entries

    def _find_daily_brief_uncertainty_entry_by_route_id(
        self,
        brief: DailyBrief,
        route_id: str,
    ) -> tuple[str, str, uuid.UUID] | None:
        for uncertainty_item, item_id, target_id in self._iter_daily_brief_uncertainty_entries(brief):
            if str(target_id) == route_id:
                return uncertainty_item, item_id, target_id
        return None

    def _get_uncertainty_auto_values(self, uncertainty_item: str) -> dict[str, Any]:
        return {
            "uncertainty_note": uncertainty_item,
            "uncertainty_status": None,
        }

    def _build_reviewed_uncertainty_summary(
        self,
        brief: DailyBrief,
        review_service: DatabaseReviewService | None,
    ) -> str:
        rendered: list[str] = []
        for uncertainty_item, _, target_id in self._iter_daily_brief_uncertainty_entries(brief):
            auto_values = self._get_uncertainty_auto_values(uncertainty_item)
            effective_values = {
                field_name: (
                    review_service.get_effective_value("uncertainty", target_id, field_name, auto_value)
                    if review_service is not None
                    else auto_value
                )
                for field_name, auto_value in auto_values.items()
            }
            detail = str(effective_values.get("uncertainty_note") or "")
            status = effective_values.get("uncertainty_status")
            if status:
                detail = f"{detail} (status={status})"
            rendered.append(detail)
        return " | ".join(item for item in rendered if item)

    def _parse_uncertainty_review_form_value(
        self,
        field_name: str,
        form: dict[str, str],
        *,
        override_source: str,
    ) -> Any:
        raw_value = form.get(field_name, "")
        reset_requested = form.get(f"reset_{field_name}") == "on"
        value = str(raw_value).strip()
        if reset_requested or (value == "" and override_source == "manual"):
            return RESET_TO_AUTO_SENTINEL
        if field_name == "uncertainty_status":
            if value == _UNCHANGED_UNCERTAINTY_STATUS:
                return _NO_UNCERTAINTY_STATUS_CHANGE
            if value == "":
                return None
            if value not in _UNCERTAINTY_STATUS_VALUES:
                allowed = ", ".join(_UNCERTAINTY_STATUS_VALUES)
                raise ValueError(f"Invalid uncertainty status: {value!r}. Allowed values: {allowed}.")
            return value
        return value or None

    def _validate_str_enum(self, raw_value: str | Any, enum_type: type, *, label: str) -> str:
        value = str(raw_value or "").strip()
        try:
            return enum_type(value).value
        except ValueError as exc:
            allowed = ", ".join(item.value for item in enum_type)
            raise ValueError(f"Invalid {label}: {value!r}. Allowed values: {allowed}.") from exc

    def _validate_provider_type(self, raw_value: str | Any) -> str:
        value = str(raw_value or "").strip() or "openai_compatible"
        if value not in _PROVIDER_TYPE_VALUES:
            allowed = ", ".join(sorted(_PROVIDER_TYPE_VALUES))
            raise ValueError(f"Invalid provider type: {value!r}. Allowed values: {allowed}.")
        return value

    def _normalize_supported_tasks(self, raw_value: Any) -> list[str]:
        if not raw_value:
            return list(_AI_TASK_VALUES)
        if not isinstance(raw_value, list):
            return list(_AI_TASK_VALUES)
        normalized: list[str] = []
        for task in raw_value:
            task_name = str(task).strip()
            if task_name in _AI_TASK_VALUES and task_name not in normalized:
                normalized.append(task_name)
        return normalized or list(_AI_TASK_VALUES)

    def _extract_supported_tasks(self, form: dict[str, str]) -> list[str]:
        selected: list[str] = []
        for task in _AI_TASK_VALUES:
            if form.get(f"task_{task}") == "on":
                selected.append(task)
        return selected or list(_AI_TASK_VALUES)

    def _validate_maintenance_status(self, raw_value: str | Any) -> str:
        value = str(raw_value or "").strip() or "ordinary"
        allowed_values = self.list_maintenance_status_values()
        if value not in allowed_values:
            allowed = ", ".join(allowed_values)
            raise ValueError(f"Invalid maintenance status: {value!r}. Allowed values: {allowed}.")
        return value

    def _validate_maintenance_status_for_web_edit(
        self,
        raw_value: str | Any,
        *,
        current_status: str | None,
    ) -> str:
        value = self._validate_maintenance_status(raw_value)
        if value == "formal_seed":
            if current_status == "formal_seed":
                return value
            raise ValueError(
                "formal_seed cannot be assigned through ordinary web editing. "
                "Formal seed governance remains in the maintenance workflow."
            )
        if current_status == "formal_seed" and value != "formal_seed":
            raise ValueError(
                "formal_seed cannot be changed through ordinary web editing. "
                "Formal seed governance remains in the maintenance workflow."
            )
        if value not in _WEB_ASSIGNABLE_MAINTENANCE_STATUS_VALUES:
            allowed = ", ".join(_WEB_ASSIGNABLE_MAINTENANCE_STATUS_VALUES)
            raise ValueError(
                f"Invalid maintenance status for web editing: {value!r}. Allowed values: {allowed}."
            )
        return value

    def _parse_json_field(self, raw_value: str | None) -> dict[str, Any] | None:
        if not raw_value or not raw_value.strip():
            return None
        return json.loads(raw_value)

    def _build_source_view(self, source: Source) -> SourceView:
        meta = self._get_source_web_metadata(source)
        config = dict(source.config or {})
        config.pop("_web", None)
        raw_config_json = json.dumps(config, ensure_ascii=False, indent=2) if config else ""
        return SourceView(
            source=source,
            maintenance_status=meta.get("maintenance_status", "ordinary"),
            notes=meta.get("notes", ""),
            last_import_at=meta.get("last_import_at"),
            last_result=meta.get("last_result"),
            raw_config_json=raw_config_json,
        )

    def _build_source_page_view(self, source: Source) -> dict[str, Any]:
        source_view = self._build_source_view(source)
        return {
            "id": str(source.id),
            "name": self._coalesce_text(source.name, default="Unnamed source"),
            "editable_name": str(source.name or ""),
            "source_type": self._coalesce_text(source.source_type),
            "url": self._coalesce_text(source.url),
            "credibility_level": self._coalesce_text(source.credibility_level),
            "fetch_strategy": self._coalesce_text(source.fetch_strategy),
            "is_active": bool(source.is_active),
            "activity_label": "active" if source.is_active else "disabled",
            "maintenance_status": self._coalesce_text(source_view.maintenance_status, default="ordinary"),
            "notes": str(source_view.notes or "").strip(),
            "last_import_at": self._coalesce_text(source_view.last_import_at),
            "last_result": self._coalesce_text(source_view.last_result),
            "raw_config_json": source_view.raw_config_json,
        }

    def _get_source_web_metadata(self, source: Source) -> dict[str, Any]:
        config = source.config or {}
        web_meta = config.get("_web", {})
        return dict(web_meta) if isinstance(web_meta, dict) else {}

    def _set_source_web_metadata(
        self,
        config: dict[str, Any] | None,
        *,
        maintenance_status: str,
        notes: str,
        last_import_at: str | None,
        last_result: str | None,
    ) -> dict[str, Any]:
        merged = dict(config or {})
        merged["_web"] = {
            "maintenance_status": maintenance_status,
            "notes": notes,
            "last_import_at": last_import_at,
            "last_result": last_result,
        }
        return merged

    def _read_json_records(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

    def _write_json_records(self, path: Path, records: list[dict[str, Any]]) -> None:
        WEB_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(records, ensure_ascii=False, indent=2)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.stem}-",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_file.write(payload)
            temp_name = temp_file.name
        os.replace(temp_name, path)

    def _persist_qa_history_record(self, record: dict[str, Any]) -> None:
        session = self._try_create_db_session()
        if session is None:
            self._append_qa_history_json_fallback(record)
            return
        try:
            session.add(self._build_qa_history_db_record(record))
            session.commit()
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass
            self._append_qa_history_json_fallback(record)
        finally:
            session.close()

    def _append_qa_history_json_fallback(self, record: dict[str, Any]) -> None:
        history = self._read_json_records(QA_HISTORY_PATH)
        history.insert(0, record)
        self._write_json_records(QA_HISTORY_PATH, history[:50])

    def _build_qa_history_db_record(self, record: dict[str, Any]) -> AskHistoryRecord:
        created_at = self._parse_datetime(record.get("created_at")) or datetime.now(timezone.utc)
        return AskHistoryRecord(
            id=uuid.UUID(str(record["id"])),
            question=str(record.get("question") or ""),
            answer=str(record.get("answer") or ""),
            answer_mode=str(record.get("answer_mode") or "local_only"),
            provider_name=str(record["provider_name"]) if record.get("provider_name") is not None else None,
            evidence=list(record.get("evidence") or []),
            error=str(record["error"]) if record.get("error") is not None else None,
            note=str(record["note"]) if record.get("note") is not None else None,
            created_at=created_at,
        )

    def _list_qa_history_from_db(self, *, limit: int) -> list[dict[str, Any]]:
        session = self._try_create_db_session()
        if session is None:
            return []
        try:
            rows = list(
                session.scalars(
                    select(AskHistoryRecord).order_by(desc(AskHistoryRecord.created_at)).limit(limit)
                )
            )
            return [self._serialize_qa_history_db_record(row) for row in rows]
        except Exception:
            return []
        finally:
            session.close()

    def _serialize_qa_history_db_record(self, row: AskHistoryRecord) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "question": row.question,
            "answer": row.answer,
            "answer_mode": row.answer_mode,
            "provider_name": row.provider_name,
            "evidence": list(row.evidence or []),
            "error": row.error,
            "note": row.note,
            "created_at": row.created_at.isoformat(),
        }

    def _parse_datetime(self, raw_value: Any) -> datetime | None:
        value = str(raw_value or "").strip()
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _build_provider_config_from_record(self, record: Any) -> ProviderConfig:
        updated_at = record.updated_at if hasattr(record, "updated_at") else record.get("updated_at", "")
        updated_at_value = updated_at.isoformat() if isinstance(updated_at, datetime) else str(updated_at or "")
        return ProviderConfig(
            id=str(record.id if hasattr(record, "id") else record["id"]),
            name=str(record.name if hasattr(record, "name") else record["name"]),
            provider_type=str(
                record.provider_type if hasattr(record, "provider_type") else record.get("provider_type", "openai_compatible")
            ),
            base_url=str(record.base_url if hasattr(record, "base_url") else record.get("base_url", "https://api.openai.com/v1")),
            model=str(record.model if hasattr(record, "model") else record.get("model", "")),
            api_key=str(record.api_key if hasattr(record, "api_key") else record.get("api_key", "")),
            is_enabled=bool(record.is_enabled if hasattr(record, "is_enabled") else record.get("is_enabled", True)),
            is_default=bool(record.is_default if hasattr(record, "is_default") else record.get("is_default", False)),
            supported_tasks=self._normalize_supported_tasks(
                record.supported_tasks if hasattr(record, "supported_tasks") else record.get("supported_tasks")
            ),
            notes=str(record.notes if hasattr(record, "notes") else record.get("notes", "")),
            last_test_status=record.last_test_status if hasattr(record, "last_test_status") else record.get("last_test_status"),
            last_test_message=record.last_test_message if hasattr(record, "last_test_message") else record.get("last_test_message"),
            updated_at=updated_at_value,
        )

    def _list_ai_provider_records_from_db(self) -> list[AiProviderConfigRecord]:
        session = self._try_create_db_session()
        if session is None:
            return []
        try:
            return list(session.scalars(select(AiProviderConfigRecord).order_by(desc(AiProviderConfigRecord.updated_at))))
        except Exception:
            return []
        finally:
            session.close()

    def _save_ai_provider_to_db(self, session: Session, form: dict[str, str]) -> str:
        provider_id = form.get("provider_id") or str(uuid.uuid4())
        is_default = form.get("is_default") == "on"
        provider_type = self._validate_provider_type(form.get("provider_type", "openai_compatible"))
        supported_tasks = self._extract_supported_tasks(form)
        existing_record = session.get(AiProviderConfigRecord, provider_id)
        submitted_api_key = form.get("api_key", "").strip()
        effective_api_key = submitted_api_key or (str(existing_record.api_key).strip() if existing_record else "")
        provider_rows = list(session.scalars(select(AiProviderConfigRecord)))
        if is_default:
            for provider in provider_rows:
                if provider.id != provider_id:
                    provider.is_default = False
        record = existing_record or AiProviderConfigRecord(id=provider_id)
        if existing_record is None and not any(provider.is_default for provider in provider_rows):
            is_default = True
        record.name = form["name"].strip()
        record.provider_type = provider_type
        record.base_url = form.get("base_url", "https://api.openai.com/v1").strip() or "https://api.openai.com/v1"
        record.model = form.get("model", "").strip()
        record.api_key = effective_api_key
        record.is_enabled = form.get("is_enabled") == "on"
        record.is_default = is_default
        record.supported_tasks = supported_tasks
        record.notes = form.get("notes", "").strip()
        record.last_test_status = "valid" if form.get("model", "").strip() and effective_api_key else "incomplete"
        record.last_test_message = "Configuration saved locally." if form.get("model", "").strip() else "Model is empty."
        record.updated_at = datetime.now(timezone.utc)
        session.add(record)
        session.commit()
        return "AI provider saved."

    def _test_ai_provider_in_db(self, session: Session, provider_id: str) -> str:
        provider = session.get(AiProviderConfigRecord, provider_id)
        if provider is None:
            return "AI provider not found."
        provider_type = self._validate_provider_type(provider.provider_type)
        base_url = str(provider.base_url or "").strip()
        api_key = str(provider.api_key or "").strip()
        model = str(provider.model or "").strip()
        if not base_url or not api_key or not model:
            provider.last_test_status = "incomplete"
            provider.last_test_message = "Base URL, API key, and model are required for testing."
            provider.updated_at = datetime.now(timezone.utc)
            session.add(provider)
            session.commit()
            return "Provider test recorded as incomplete."

        status = "failed"
        message = "Unknown provider test failure."
        try:
            if provider_type == "openai_compatible":
                endpoint = base_url.rstrip("/") + "/models"
                req = request.Request(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    method="GET",
                )
                with request.urlopen(req, timeout=20) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                data = payload.get("data", [])
                if isinstance(data, list):
                    status = "valid"
                    message = f"Connected successfully. Model configured: {model}."
                else:
                    message = "Provider responded without a valid model list."
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"

        provider.last_test_status = status
        provider.last_test_message = message
        provider.updated_at = datetime.now(timezone.utc)
        session.add(provider)
        session.commit()
        return f"Provider test status: {status}."

    def _run_db_read(self, operation, *, empty):
        session = self._try_create_db_session()
        if session is None:
            return empty, "Database session unavailable."
        try:
            return operation(session), None
        except Exception as exc:
            return empty, f"{type(exc).__name__}: {exc}"
        finally:
            session.close()

    def _require_session(self) -> Session:
        session = self._try_create_db_session()
        if session is None:
            raise RuntimeError("Database session unavailable.")
        return session

    def _try_create_db_session(self) -> Session | None:
        try:
            session_factory = get_session_factory()
            return session_factory()
        except Exception:
            return None
