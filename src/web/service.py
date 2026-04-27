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

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from src.admin.review_schemas import ReviewEditCreate
from src.admin.review_service_db import DatabaseReviewService
from src.application.orchestrator import DocumentPipelineOrchestrator
from src.config import (
    get_session_factory,
    probe_database_connection,
    probe_database_environment,
    probe_pgvector_extension,
)
from src.domain.enums import CredibilityLevel, PriorityLevel, SourceType, WatchlistStatus
from src.domain.models import (
    Document,
    DocumentEntity,
    DocumentSummary,
    DocumentTopic,
    Entity,
    ReviewEdit,
    Source,
    Topic,
    WatchlistItem,
)
from src.ingestion.url_importer import import_url_as_raw_document

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

    def list_review_documents(self) -> tuple[list[Document], str | None]:
        def _query(session: Session) -> list[Document]:
            stmt = (
                select(Document)
                .join(DocumentSummary, DocumentSummary.document_id == Document.id)
                .options(selectinload(Document.summary))
                .order_by(Document.updated_at.desc())
                .limit(20)
            )
            return list(session.scalars(stmt).unique())

        return self._run_db_read(_query, empty=[])

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
            service = DatabaseReviewService(session)
            edits: list[ReviewEditCreate] = []
            summary_zh = form.get("summary_zh", "").strip()
            summary_en = form.get("summary_en", "").strip()
            key_points_text = form.get("key_points", "").strip()
            new_key_points = [line.strip() for line in key_points_text.splitlines() if line.strip()]

            if summary_zh != (summary.summary_zh or "").strip():
                edits.append(
                    ReviewEditCreate(
                        field_name="summary_zh",
                        old_value=summary.summary_zh,
                        new_value=summary_zh or None,
                        reason=form.get("reason") or "Web summary review update",
                        reviewer="owner",
                    )
                )
                summary.summary_zh = summary_zh or None
            if summary_en != (summary.summary_en or "").strip():
                edits.append(
                    ReviewEditCreate(
                        field_name="summary_en",
                        old_value=summary.summary_en,
                        new_value=summary_en or None,
                        reason=form.get("reason") or "Web summary review update",
                        reviewer="owner",
                    )
                )
                summary.summary_en = summary_en or None
            if new_key_points != (summary.key_points or []):
                edits.append(
                    ReviewEditCreate(
                        field_name="key_points",
                        old_value=summary.key_points or [],
                        new_value=new_key_points,
                        reason=form.get("reason") or "Web summary review update",
                        reviewer="owner",
                    )
                )
                summary.key_points = new_key_points
            if not edits:
                return "No summary changes detected."

            service.create_batch("summary", summary.id, edits, reason=form.get("reason"))
            session.commit()
            return "Summary review saved."
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
        records = self._read_json_records(AI_SETTINGS_PATH)
        providers: list[ProviderConfig] = []
        for record in records:
            providers.append(
                ProviderConfig(
                    id=record["id"],
                    name=record["name"],
                    provider_type=record.get("provider_type", "openai_compatible"),
                    base_url=record.get("base_url", "https://api.openai.com/v1"),
                    model=record.get("model", ""),
                    api_key=record.get("api_key", ""),
                    is_enabled=bool(record.get("is_enabled", True)),
                    is_default=bool(record.get("is_default", False)),
                    supported_tasks=self._normalize_supported_tasks(record.get("supported_tasks")),
                    notes=record.get("notes", ""),
                    last_test_status=record.get("last_test_status"),
                    last_test_message=record.get("last_test_message"),
                    updated_at=record.get("updated_at", ""),
                )
            )
        return providers

    def get_ai_provider(self, provider_id: str) -> ProviderConfig | None:
        for provider in self.list_ai_providers():
            if provider.id == provider_id:
                return provider
        return None

    def save_ai_provider(self, form: dict[str, str]) -> str:
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
        documents, db_error = self.search_documents_for_question(question)
        evidence = self._build_evidence_from_documents(documents[:_QA_EVIDENCE_INSPECTION_LIMIT], question)
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
        history = self._read_json_records(QA_HISTORY_PATH)
        history.insert(0, record)
        self._write_json_records(QA_HISTORY_PATH, history[:50])
        return record

    def list_qa_history(self) -> list[dict[str, Any]]:
        return self._read_json_records(QA_HISTORY_PATH)

    def get_dashboard_data(self) -> dict[str, Any]:
        counts = {
            "sources": 0,
            "documents": 0,
            "watchlist": 0,
            "reviews": 0,
        }
        recent_documents: list[Document] = []
        top_topics: list[tuple[str, int]] = []
        db_error = None
        session = self._try_create_db_session()
        if session is not None:
            try:
                counts["sources"] = int(session.scalar(select(func.count()).select_from(Source)) or 0)
                counts["documents"] = int(session.scalar(select(func.count()).select_from(Document)) or 0)
                counts["watchlist"] = int(session.scalar(select(func.count()).select_from(WatchlistItem)) or 0)
                counts["reviews"] = int(
                    session.scalar(
                        select(func.count()).select_from(ReviewEdit).where(ReviewEdit.target_type == "summary")
                    )
                    or 0
                )
                recent_documents = list(
                    session.scalars(
                        select(Document)
                        .options(selectinload(Document.summary), selectinload(Document.source))
                        .order_by(Document.created_at.desc())
                        .limit(5)
                    )
                )
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

        return {
            "counts": counts,
            "recent_documents": recent_documents,
            "top_topics": top_topics,
            "providers": self.list_ai_providers(),
            "qa_history": self.list_qa_history()[:5],
            "db_error": db_error,
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
            except Exception:
                counts = {}
            finally:
                session.close()

        return {
            "database_environment": environment_result,
            "database_connection": connection_result,
            "pgvector": vector_result,
            "files": file_status,
            "counts": counts,
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

    def _build_evidence_from_documents(self, documents: list[Document], question: str) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        question_terms = self._build_query_terms(question)
        for document in documents:
            score, matched_terms = self._score_document_for_terms(document, question_terms)
            if score <= 0:
                continue
            snippet, summary_text, match_basis = self._pick_snippet(document, question_terms)
            evidence.append(
                {
                    "document_id": str(document.id),
                    "title": document.title,
                    "source": document.source.name if document.source else None,
                    "summary": summary_text,
                    "snippet": snippet,
                    "match_basis": match_basis,
                    "matched_terms": matched_terms,
                    "score": score,
                    "url": document.url,
                }
            )
        evidence.sort(key=lambda item: item["score"], reverse=True)
        return evidence[:_QA_EVIDENCE_RETURN_LIMIT]

    def _pick_snippet(self, document: Document, question_terms: list[str]) -> tuple[str, str | None, str]:
        key_point = self._pick_matching_line(document.summary.key_points or [], question_terms) if document.summary else None
        if key_point:
            return key_point, self._build_summary_text(document), "key_point"

        summary_text = self._build_summary_text(document)
        if summary_text:
            summary_snippet = self._clip_matching_text(summary_text, question_terms, default_size=220)
            if summary_snippet:
                return summary_snippet, summary_text, "summary"

        content_snippet = self._clip_matching_text(document.content_text or "", question_terms, default_size=220)
        if content_snippet:
            return content_snippet, summary_text or None, "content"

        fallback = summary_text or self._clip_matching_text(document.content_text or "", question_terms, default_size=220)
        return fallback, summary_text or None, "fallback"

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

    def _score_document_for_terms(self, document: Document, terms: list[str]) -> tuple[int, int]:
        if not terms:
            return (0, 0)

        title_text = (document.title or "").lower()
        content_text = (document.content_text or "").lower()
        url_text = (document.url or "").lower()
        summary_text = self._build_summary_text(document).lower()
        key_points_text = self._build_key_points_text(document).lower()

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

    def _build_summary_text(self, document: Document) -> str:
        if document.summary is None:
            return ""
        return document.summary.summary_en or document.summary.summary_zh or ""

    def _build_key_points_text(self, document: Document) -> str:
        if document.summary is None or not document.summary.key_points:
            return ""
        return " ".join(str(point).strip() for point in document.summary.key_points if str(point).strip())

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
