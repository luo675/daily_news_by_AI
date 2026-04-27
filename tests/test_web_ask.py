from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.routes import web as web_routes
from src.domain.models import Document, DocumentSummary, Source
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
