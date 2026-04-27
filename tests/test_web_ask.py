from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.routes import web as web_routes
from src.domain.models import DailyBrief, Document, DocumentSummary, OpportunityAssessment, OpportunityEvidence, Source
from src.web import service as web_service_module
from src.web.service import ProviderConfig, WebMvpService


@pytest.fixture
def workspace_tmp_path() -> Path:
    root = Path("tests") / ".tmp" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _configure_web_storage(monkeypatch, tmp_path: Path) -> None:
    web_dir = tmp_path / "web"
    monkeypatch.setattr(web_service_module, "WEB_CONFIG_DIR", web_dir)
    monkeypatch.setattr(web_service_module, "AI_SETTINGS_PATH", web_dir / "ai_settings.json")
    monkeypatch.setattr(web_service_module, "QA_HISTORY_PATH", web_dir / "qa_history.json")


def _build_provider() -> ProviderConfig:
    return ProviderConfig(
        id="provider-1",
        name="Local QA Provider",
        provider_type="openai_compatible",
        base_url="https://example.com",
        model="test-model",
        api_key="secret-key",
        is_enabled=True,
        is_default=True,
        supported_tasks=["qa"],
        notes="",
        last_test_status=None,
        last_test_message=None,
        updated_at="2026-04-26T00:00:00+00:00",
    )


def _build_document(*, key_points: list[str] | None = None) -> Document:
    document = Document(
        id=uuid.uuid4(),
        title="Weekly AI coding tools update",
        content_text="AI coding tools changed this week with new code review and editing workflows.",
        url="https://example.com/ai-coding-tools",
        created_at=datetime.now(timezone.utc),
    )
    document.source = Source(name="Example Source")
    document.summary = DocumentSummary(
        summary_en="This document summarizes changes in AI coding tools.",
        key_points=key_points or [],
    )
    return document


def _build_opportunity(document: Document) -> OpportunityAssessment:
    opportunity = OpportunityAssessment(
        id=uuid.uuid4(),
        title_en="AI coding workflow assistant",
        description_en="Workflow automation for AI-assisted code review.",
        priority=4,
        total_score=6.0,
        uncertainty=False,
        status="candidate",
    )
    opportunity.evidence_items = [
        OpportunityEvidence(
            id=uuid.uuid4(),
            opportunity_id=opportunity.id,
            document_id=document.id,
            evidence_type="quote",
            content="Supporting evidence from the document.",
        )
    ]
    return opportunity


def _build_brief() -> DailyBrief:
    return DailyBrief(
        id=uuid.uuid4(),
        brief_date=datetime.now(timezone.utc),
        brief_type="on_demand",
        summary_en="Daily brief covering AI coding workflow changes.",
        content_en="Risk outlook and unresolved uncertainty for AI coding tools.",
        risks=[
            {
                "title": "Vendor dependence",
                "severity": "low",
                "description": "Current workflow depends on one hosted provider.",
            }
        ],
        uncertainties=["Long-term review accuracy remains unclear."],
    )


class _DummySession:
    def close(self) -> None:
        return None


class _FakeQaHistoryScalarResult:
    def __init__(self, items):
        self._items = items

    def __iter__(self):
        return iter(self._items)


class _FakeQaHistorySession:
    def __init__(self, existing=None):
        self.existing = existing or []
        self.pending = []
        self.persisted = []
        self.closed = False
        self.commit_count = 0
        self.rollback_count = 0

    def add(self, item) -> None:
        self.pending.append(item)

    def commit(self) -> None:
        self.commit_count += 1
        self.persisted.extend(self.pending)
        self.pending = []

    def rollback(self) -> None:
        self.rollback_count += 1
        self.pending = []

    def scalars(self, stmt):
        return _FakeQaHistoryScalarResult(self.existing)

    def close(self) -> None:
        self.closed = True


class _FakeQaHistoryCommitFailureSession(_FakeQaHistorySession):
    def commit(self) -> None:
        self.commit_count += 1
        raise RuntimeError("db commit failed")


class _FakeProviderScalarResult:
    def __init__(self, items):
        self._items = items

    def __iter__(self):
        return iter(self._items)


class _FakeProviderSession:
    def __init__(self, existing=None):
        self.existing = list(existing or [])
        self.pending = []
        self.closed = False
        self.commit_count = 0
        self.rollback_count = 0

    def add(self, item) -> None:
        self.pending.append(item)

    def get(self, model, object_id):
        object_id = str(object_id)
        for item in self.existing:
            if str(item.id) == object_id:
                return item
        return None

    def commit(self) -> None:
        self.commit_count += 1
        for item in self.pending:
            replaced = False
            for index, existing in enumerate(self.existing):
                if str(existing.id) == str(item.id):
                    self.existing[index] = item
                    replaced = True
                    break
            if not replaced:
                self.existing.append(item)
        self.pending = []

    def rollback(self) -> None:
        self.rollback_count += 1
        self.pending = []

    def scalars(self, stmt):
        return _FakeProviderScalarResult(self.existing)

    def close(self) -> None:
        self.closed = True


def test_ask_page_renders_history_and_local_evidence_note(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    monkeypatch.setattr(web_routes.service, "list_ai_providers", lambda: [_build_provider()])
    monkeypatch.setattr(
        web_routes.service,
        "list_qa_history",
        lambda: [
            {
                "question": "What changed in AI coding tools this week?",
                "answer_mode": "local_only",
                "provider_name": None,
                "note": "Multiple local evidence items matched the question.",
                "answer": "Local answer body",
            }
        ],
    )

    client = TestClient(create_app())
    response = client.get("/web/ask")

    assert response.status_code == 200
    assert "Ask from Local Knowledge" in response.text
    assert "may only reason over the retrieved local evidence" in response.text
    assert "Multiple local evidence items matched the question." in response.text


def test_ask_submit_renders_answer_mode_and_note(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    monkeypatch.setattr(
        web_routes.service,
        "ask_question",
        lambda question, provider_id="": {
            "question": question,
            "answer": "Bounded answer from local evidence.",
            "answer_mode": "local_with_external_reasoning",
            "provider_name": "Local QA Provider",
            "note": "A focused local summary/key-point match was found.",
            "error": None,
            "evidence": [
                {
                    "document_id": str(uuid.uuid4()),
                    "title": "Weekly AI coding tools update",
                    "summary": "This document summarizes changes in AI coding tools.",
                    "snippet": "AI coding tools changed this week.",
                    "url": "https://example.com/ai-coding-tools",
                }
            ],
        },
    )

    client = TestClient(create_app())
    response = client.post(
        "/web/ask",
        data={"question": "What changed in AI coding tools this week?", "provider_id": ""},
    )

    assert response.status_code == 200
    assert "mode=local_with_external_reasoning" in response.text
    assert "A focused local summary/key-point match was found." in response.text
    assert "Bounded answer from local evidence." in response.text


def test_ask_question_returns_insufficient_local_evidence_without_external_call(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    provider = _build_provider()
    called = {"external": False}

    monkeypatch.setattr(service, "list_ai_providers", lambda: [provider])
    monkeypatch.setattr(service, "search_documents_for_question", lambda question: ([], None))

    def _unexpected_external_call(*args, **kwargs):
        called["external"] = True
        raise AssertionError("external provider should not be called without sufficient local evidence")

    monkeypatch.setattr(service, "_call_openai_compatible", _unexpected_external_call)

    result = service.ask_question("What changed in AI coding tools this week?")

    assert result["answer_mode"] == "insufficient_local_evidence"
    assert result["note"] == "No local evidence matched the question."
    assert called["external"] is False
    assert len(result["evidence"]) == 0


def test_ask_question_persists_history_to_db_first(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    session = _FakeQaHistorySession()

    monkeypatch.setattr(service, "_try_create_db_session", lambda: session)
    monkeypatch.setattr(service, "list_ai_providers", lambda: [])
    monkeypatch.setattr(service, "search_documents_for_question", lambda question: ([], None))
    monkeypatch.setattr(service, "search_briefs_for_question", lambda question: ([], None), raising=False)
    monkeypatch.setattr(
        service,
        "_write_json_records",
        lambda path, records: (_ for _ in ()).throw(AssertionError("JSON fallback should not run when DB write works")),
    )

    result = service.ask_question("What changed in AI coding tools this week?")

    assert result["answer_mode"] == "insufficient_local_evidence"
    assert session.commit_count == 1
    assert len(session.persisted) == 1
    saved = session.persisted[0]
    assert saved.question == "What changed in AI coding tools this week?"
    assert saved.answer == result["answer"]
    assert saved.answer_mode == "insufficient_local_evidence"
    assert saved.provider_name is None
    assert saved.error is None
    assert saved.note == "No local evidence matched the question."
    assert saved.evidence == []


def test_ask_question_falls_back_to_json_when_db_commit_fails(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    session = _FakeQaHistoryCommitFailureSession()
    captured: dict[str, object] = {}

    monkeypatch.setattr(service, "_try_create_db_session", lambda: session)
    monkeypatch.setattr(service, "list_ai_providers", lambda: [])
    monkeypatch.setattr(service, "search_documents_for_question", lambda question: ([], None))
    monkeypatch.setattr(service, "search_briefs_for_question", lambda question: ([], None), raising=False)
    monkeypatch.setattr(service, "_read_json_records", lambda path: [])

    def _capture_write(path, records):
        captured["path"] = path
        captured["records"] = records

    monkeypatch.setattr(service, "_write_json_records", _capture_write)

    result = service.ask_question("What changed in AI coding tools this week?")

    assert result["answer_mode"] == "insufficient_local_evidence"
    assert result["note"] == "No local evidence matched the question."
    assert session.commit_count == 1
    assert session.rollback_count == 1
    assert session.closed is True
    assert captured["path"] == web_service_module.QA_HISTORY_PATH
    written = captured["records"]
    assert len(written) == 1
    assert written[0]["question"] == "What changed in AI coding tools this week?"
    assert written[0]["answer"] == result["answer"]
    assert written[0]["answer_mode"] == "insufficient_local_evidence"


def test_list_qa_history_reads_from_db(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    created_at = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    row = type(
        "AskHistoryRow",
        (),
        {
            "id": uuid.uuid4(),
            "question": "What changed in AI coding tools this week?",
            "answer": "Stored DB answer.",
            "answer_mode": "local_only",
            "provider_name": None,
            "evidence": [{"title": "DB evidence"}],
            "error": None,
            "note": "Stored DB note.",
            "created_at": created_at,
        },
    )()

    monkeypatch.setattr(service, "_try_create_db_session", lambda: _FakeQaHistorySession(existing=[row]))
    monkeypatch.setattr(
        service,
        "_read_json_records",
        lambda path: (_ for _ in ()).throw(AssertionError("JSON fallback should not run when DB read works")),
    )

    history = service.list_qa_history()

    assert len(history) == 1
    assert history[0]["question"] == "What changed in AI coding tools this week?"
    assert history[0]["answer"] == "Stored DB answer."
    assert history[0]["note"] == "Stored DB note."
    assert history[0]["created_at"] == created_at.isoformat()


def test_list_qa_history_falls_back_to_legacy_json_when_db_unavailable(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    legacy = [
        {
            "id": "legacy-1",
            "question": "Legacy JSON question",
            "answer": "Legacy JSON answer",
            "answer_mode": "local_only",
            "provider_name": None,
            "evidence": [],
            "error": None,
            "note": "Legacy note",
            "created_at": "2026-04-26T08:07:31.977231+00:00",
        }
    ]

    monkeypatch.setattr(service, "_try_create_db_session", lambda: None)
    monkeypatch.setattr(service, "_read_json_records", lambda path: legacy)

    history = service.list_qa_history()

    assert history == legacy


def test_ask_question_prefers_key_points_and_uses_external_reasoning(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    provider = _build_provider()
    document = _build_document(key_points=["AI coding tools changed this week with better review workflows."])
    external_calls = {"count": 0}

    monkeypatch.setattr(service, "list_ai_providers", lambda: [provider])
    monkeypatch.setattr(service, "search_documents_for_question", lambda question: ([document], None))

    def _external_answer(*args, **kwargs):
        external_calls["count"] += 1
        return "External reasoning bounded by local evidence."

    monkeypatch.setattr(service, "_call_openai_compatible", _external_answer)

    result = service.ask_question("What changed in AI coding tools this week?")

    assert result["answer_mode"] == "local_with_external_reasoning"
    assert result["provider_name"] == provider.name
    assert result["note"] == "A focused local summary/key-point match was found."
    assert result["answer"] == "External reasoning bounded by local evidence."
    assert result["evidence"][0]["match_basis"] == "key_point"
    assert "AI coding tools changed this week" in result["evidence"][0]["snippet"]
    assert external_calls["count"] == 1


def test_ask_question_falls_back_to_local_answer_when_provider_fails(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    provider = _build_provider()
    document = _build_document(key_points=["AI coding tools changed this week with better review workflows."])

    monkeypatch.setattr(service, "list_ai_providers", lambda: [provider])
    monkeypatch.setattr(service, "search_documents_for_question", lambda question: ([document], None))

    def _failing_external(*args, **kwargs):
        raise RuntimeError("provider timeout")

    monkeypatch.setattr(service, "_call_openai_compatible", _failing_external)

    result = service.ask_question("What changed in AI coding tools this week?")

    assert result["answer_mode"] == "local_fallback"
    assert result["provider_name"] == provider.name
    assert result["error"] == "RuntimeError: provider timeout"
    assert "Evidence note: A focused local summary/key-point match was found." in result["answer"]


def test_ask_question_prefers_reviewed_opportunity_values_in_evidence(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    document = _build_document()
    opportunity = _build_opportunity(document)
    document._ask_test_opportunities = [opportunity]

    monkeypatch.setattr(service, "_try_create_db_session", lambda: _DummySession())
    monkeypatch.setattr(service, "list_ai_providers", lambda: [])
    monkeypatch.setattr(service, "search_documents_for_question", lambda question: ([document], None))
    monkeypatch.setattr(service, "search_briefs_for_question", lambda question: ([], None), raising=False)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            overrides = {
                "priority_score": 8,
                "total_score": 9.5,
                "status": "dismissed",
                "uncertainty": True,
                "uncertainty_reason": "Manual review: customer demand remains unproven.",
            }
            return overrides.get(field_name, auto_value)

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    result = service.ask_question("What changed in AI coding tools this week?")

    assert result["answer_mode"] == "local_only"
    assert "Reviewed opportunities:" in result["evidence"][0]["summary"]
    assert "status=dismissed" in result["evidence"][0]["summary"]
    assert "priority_score=8" in result["evidence"][0]["summary"]
    assert "customer demand remains unproven" in result["evidence"][0]["summary"]


def test_ask_question_uses_auto_opportunity_values_without_manual_review(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    document = _build_document()
    opportunity = _build_opportunity(document)
    document._ask_test_opportunities = [opportunity]

    monkeypatch.setattr(service, "_try_create_db_session", lambda: _DummySession())
    monkeypatch.setattr(service, "list_ai_providers", lambda: [])
    monkeypatch.setattr(service, "search_documents_for_question", lambda question: ([document], None))
    monkeypatch.setattr(service, "search_briefs_for_question", lambda question: ([], None), raising=False)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            return auto_value

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    result = service.ask_question("What changed in AI coding tools this week?")

    assert "Reviewed opportunities:" in result["evidence"][0]["summary"]
    assert "status=candidate" in result["evidence"][0]["summary"]
    assert "status=dismissed" not in result["evidence"][0]["summary"]


def test_ask_question_does_not_fake_key_point_match(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    provider = _build_provider()
    document = _build_document(key_points=["Unrelated note about funding activity."])
    document.summary.summary_en = "This document summarizes changes in AI coding tools."
    external_calls = {"count": 0}

    monkeypatch.setattr(service, "list_ai_providers", lambda: [provider])
    monkeypatch.setattr(service, "search_documents_for_question", lambda question: ([document], None))

    def _external_answer(*args, **kwargs):
        external_calls["count"] += 1
        return "External reasoning bounded by summary evidence."

    monkeypatch.setattr(service, "_call_openai_compatible", _external_answer)

    result = service.ask_question("What changed in AI coding tools this week?")

    assert result["answer_mode"] == "local_with_external_reasoning"
    assert result["evidence"][0]["match_basis"] == "summary"
    assert "Unrelated note about funding activity." not in result["evidence"][0]["snippet"]
    assert external_calls["count"] == 1


def test_ask_question_adds_reviewed_brief_risk_and_uncertainty_evidence(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    brief = _build_brief()

    monkeypatch.setattr(service, "_try_create_db_session", lambda: _DummySession())
    monkeypatch.setattr(service, "list_ai_providers", lambda: [])
    monkeypatch.setattr(service, "search_documents_for_question", lambda question: ([], None))
    monkeypatch.setattr(service, "search_briefs_for_question", lambda question: ([brief], None), raising=False)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            overrides = {
                ("risk", "severity"): "high",
                ("risk", "description"): "Manual review: concentration risk remains high.",
                ("uncertainty", "uncertainty_note"): "Manual review: benchmark quality is still unclear.",
                ("uncertainty", "uncertainty_status"): "watching",
            }
            return overrides.get((target_type, field_name), auto_value)

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    result = service.ask_question("What risks and uncertainties remain in AI coding workflows?")

    assert result["answer_mode"] == "local_only"
    assert any(item["title"].startswith("Daily Brief") for item in result["evidence"])
    brief_evidence = next(item for item in result["evidence"] if item["title"].startswith("Daily Brief"))
    assert "severity=high" in brief_evidence["summary"]
    assert "concentration risk remains high" in brief_evidence["summary"]
    assert "benchmark quality is still unclear" in brief_evidence["summary"]
    assert "status=watching" in brief_evidence["summary"]


def test_ask_question_does_not_invent_uncertainty_status_without_manual_review(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    brief = _build_brief()

    monkeypatch.setattr(service, "_try_create_db_session", lambda: _DummySession())
    monkeypatch.setattr(service, "list_ai_providers", lambda: [])
    monkeypatch.setattr(service, "search_documents_for_question", lambda question: ([], None))
    monkeypatch.setattr(service, "search_briefs_for_question", lambda question: ([brief], None), raising=False)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            return auto_value

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    result = service.ask_question("What uncertainties remain in AI coding workflows?")

    brief_evidence = next(item for item in result["evidence"] if item["title"].startswith("Daily Brief"))
    assert "status=open" not in brief_evidence["summary"]
    assert "status=watching" not in brief_evidence["summary"]
    assert "status=resolved" not in brief_evidence["summary"]


def test_local_only_and_insufficient_modes_do_not_report_provider_name(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    provider = _build_provider()
    document = _build_document(key_points=["AI coding tools changed this week with better review workflows."])

    monkeypatch.setattr(service, "list_ai_providers", lambda: [provider])
    monkeypatch.setattr(service, "search_documents_for_question", lambda question: ([document], None))
    monkeypatch.setattr(service, "_select_provider_for_task", lambda providers, **kwargs: None)

    local_only_result = service.ask_question("What changed in AI coding tools this week?")
    assert local_only_result["answer_mode"] == "local_only"
    assert local_only_result["provider_name"] is None

    monkeypatch.setattr(service, "search_documents_for_question", lambda question: ([], None))
    insufficient_result = service.ask_question("What changed in AI coding tools this week?")
    assert insufficient_result["answer_mode"] == "insufficient_local_evidence"
    assert insufficient_result["provider_name"] is None


def test_ask_submit_renders_brief_evidence_without_document_link(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    monkeypatch.setattr(
        web_routes.service,
        "ask_question",
        lambda question, provider_id="": {
            "question": question,
            "answer": "Bounded answer from local evidence.",
            "answer_mode": "local_only",
            "provider_name": None,
            "note": "A focused local summary/key-point match was found.",
            "error": None,
            "evidence": [
                {
                    "title": "Daily Brief 2026-04-27",
                    "summary": "Reviewed risk and uncertainty evidence.",
                    "snippet": "Reviewed risk and uncertainty evidence.",
                    "url": None,
                }
            ],
        },
    )

    client = TestClient(create_app())
    response = client.post(
        "/web/ask",
        data={"question": "What risks remain?", "provider_id": ""},
    )

    assert response.status_code == 200
    assert "Daily Brief 2026-04-27" in response.text
    assert "Reviewed risk and uncertainty evidence." in response.text


def test_ask_page_reads_history_from_db(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    created_at = datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    row = type(
        "AskHistoryRow",
        (),
        {
            "id": uuid.uuid4(),
            "question": "What changed in AI coding tools this week?",
            "answer": "Stored DB answer.",
            "answer_mode": "local_only",
            "provider_name": None,
            "evidence": [],
            "error": None,
            "note": "Stored DB note.",
            "created_at": created_at,
        },
    )()

    monkeypatch.setattr(web_routes.service, "_try_create_db_session", lambda: _FakeQaHistorySession(existing=[row]))
    monkeypatch.setattr(web_routes.service, "_read_json_records", lambda path: [])
    monkeypatch.setattr(web_routes.service, "list_ai_providers", lambda: [])

    client = TestClient(create_app())
    response = client.get("/web/ask")

    assert response.status_code == 200
    assert "What changed in AI coding tools this week?" in response.text
    assert "Stored DB answer." in response.text
    assert "Stored DB note." in response.text


def test_ai_provider_edit_page_hides_plaintext_key(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    provider = _build_provider()
    monkeypatch.setattr(web_routes.service, "get_ai_provider", lambda provider_id: provider)

    client = TestClient(create_app())
    response = client.get("/web/ai-settings/provider-1")

    assert response.status_code == 200
    assert 'value="secret-key"' not in response.text
    assert "Leave blank to keep current saved key" in response.text
    assert provider.masked_key in response.text


def test_list_ai_providers_reads_from_db(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    row = type(
        "ProviderRow",
        (),
        {
            "id": "provider-1",
            "name": "DB Provider",
            "provider_type": "openai_compatible",
            "base_url": "https://example.com",
            "model": "test-model",
            "api_key": "secret-key",
            "is_enabled": True,
            "is_default": True,
            "supported_tasks": ["qa"],
            "notes": "db notes",
            "last_test_status": "valid",
            "last_test_message": "ok",
            "updated_at": datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc),
        },
    )()

    monkeypatch.setattr(service, "_try_create_db_session", lambda: _FakeProviderSession(existing=[row]))
    monkeypatch.setattr(
        service,
        "_read_json_records",
        lambda path: (_ for _ in ()).throw(AssertionError("JSON fallback should not run when DB read works")),
    )

    providers = service.list_ai_providers()

    assert len(providers) == 1
    assert providers[0].name == "DB Provider"
    assert providers[0].api_key == "secret-key"
    assert providers[0].notes == "db notes"


def test_list_ai_providers_falls_back_to_legacy_json_when_db_unavailable(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    legacy = [
        {
            "id": "provider-1",
            "name": "Legacy Provider",
            "provider_type": "openai_compatible",
            "base_url": "https://example.com",
            "model": "legacy-model",
            "api_key": "legacy-secret",
            "is_enabled": True,
            "is_default": True,
            "supported_tasks": ["qa"],
            "notes": "legacy notes",
            "last_test_status": "valid",
            "last_test_message": "ok",
            "updated_at": "2026-04-26T00:00:00+00:00",
        }
    ]

    monkeypatch.setattr(service, "_try_create_db_session", lambda: None)
    monkeypatch.setattr(service, "_read_json_records", lambda path: legacy)

    providers = service.list_ai_providers()

    assert len(providers) == 1
    assert providers[0].name == "Legacy Provider"
    assert providers[0].api_key == "legacy-secret"


def test_save_ai_provider_preserves_existing_key_when_edit_input_blank(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    existing = {
        "id": "provider-1",
        "name": "Existing Provider",
        "provider_type": "openai_compatible",
        "base_url": "https://example.com",
        "model": "test-model",
        "api_key": "persisted-secret",
        "is_enabled": True,
        "is_default": True,
        "supported_tasks": ["qa"],
        "notes": "existing",
        "last_test_status": "valid",
        "last_test_message": "ok",
        "updated_at": "2026-04-26T00:00:00+00:00",
    }
    captured: dict[str, object] = {}

    monkeypatch.setattr(service, "_try_create_db_session", lambda: None)
    monkeypatch.setattr(service, "_read_json_records", lambda path: [existing.copy()])

    def _capture_write(path, records):
        captured["records"] = records

    monkeypatch.setattr(service, "_write_json_records", _capture_write)

    message = service.save_ai_provider(
        {
            "provider_id": "provider-1",
            "name": "Existing Provider Updated",
            "provider_type": "openai_compatible",
            "base_url": "https://example.com",
            "model": "test-model",
            "api_key": "",
            "notes": "changed",
            "is_enabled": "on",
            "is_default": "on",
            "task_qa": "on",
        }
    )

    assert message == "AI provider saved."
    saved = captured["records"][0]
    assert saved["api_key"] == "persisted-secret"
    assert saved["last_test_status"] == "valid"


def test_save_ai_provider_writes_to_db_and_preserves_existing_key_when_edit_input_blank(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    existing = type(
        "ProviderRow",
        (),
        {
            "id": "provider-1",
            "name": "Existing Provider",
            "provider_type": "openai_compatible",
            "base_url": "https://example.com",
            "model": "test-model",
            "api_key": "persisted-secret",
            "is_enabled": True,
            "is_default": True,
            "supported_tasks": ["qa"],
            "notes": "existing",
            "last_test_status": "valid",
            "last_test_message": "ok",
            "updated_at": datetime(2026, 4, 26, 0, 0, tzinfo=timezone.utc),
        },
    )()
    session = _FakeProviderSession(existing=[existing])

    monkeypatch.setattr(service, "_try_create_db_session", lambda: session)
    monkeypatch.setattr(
        service,
        "_write_json_records",
        lambda path, records: (_ for _ in ()).throw(AssertionError("JSON fallback should not run when DB write works")),
    )

    message = service.save_ai_provider(
        {
            "provider_id": "provider-1",
            "name": "Existing Provider Updated",
            "provider_type": "openai_compatible",
            "base_url": "https://example.com",
            "model": "test-model",
            "api_key": "",
            "notes": "changed",
            "is_enabled": "on",
            "is_default": "on",
            "task_qa": "on",
        }
    )

    assert message == "AI provider saved."
    assert session.commit_count == 1
    saved = session.get(None, "provider-1")
    assert saved.name == "Existing Provider Updated"
    assert saved.api_key == "persisted-secret"
    assert saved.notes == "changed"


def test_test_ai_provider_updates_db_status(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    existing = type(
        "ProviderRow",
        (),
        {
            "id": "provider-1",
            "name": "Existing Provider",
            "provider_type": "openai_compatible",
            "base_url": "https://example.com",
            "model": "test-model",
            "api_key": "persisted-secret",
            "is_enabled": True,
            "is_default": True,
            "supported_tasks": ["qa"],
            "notes": "existing",
            "last_test_status": "incomplete",
            "last_test_message": "missing",
            "updated_at": datetime(2026, 4, 26, 0, 0, tzinfo=timezone.utc),
        },
    )()
    session = _FakeProviderSession(existing=[existing])

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return b'{\"data\": []}'

    monkeypatch.setattr(service, "_try_create_db_session", lambda: session)
    monkeypatch.setattr(
        web_service_module.request,
        "urlopen",
        lambda req, timeout=20: _FakeResponse(),
    )
    monkeypatch.setattr(
        service,
        "_write_json_records",
        lambda path, records: (_ for _ in ()).throw(AssertionError("JSON fallback should not run when DB write works")),
    )

    message = service.test_ai_provider("provider-1")

    assert message == "Provider test status: valid."
    assert session.commit_count == 1
    saved = session.get(None, "provider-1")
    assert saved.last_test_status == "valid"
    assert "Connected successfully" in saved.last_test_message
