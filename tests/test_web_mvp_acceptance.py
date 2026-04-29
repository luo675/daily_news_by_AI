from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.routes import web as web_routes
from src.domain.models import Document, DocumentSummary
from src.web.service import SummaryReviewView


def _dashboard_payload() -> dict[str, object]:
    return {
        "counts": {"sources": 1, "documents": 2, "watchlist": 0, "reviews": 1},
        "recent_documents": [
            {
                "id": str(uuid.uuid4()),
                "title": "Weekly AI coding tools update",
                "source_name": "Example Source",
                "status": "processed",
                "published_at": "2026-04-27 12:00:00+00:00",
                "created_at": "2026-04-28 09:30:00+00:00",
                "summary_text": "Manual effective summary for AI coding tools.",
            }
        ],
        "top_topics": [("AI Coding", 2)],
        "providers": [],
        "qa_history": [],
        "db_error": None,
        "system_status": {
            "database_label": "available",
            "database_detail": "Counts and recent knowledge changes are available.",
            "provider_label": "No provider configured",
            "knowledge_label": "1 recent document available in the dashboard",
        },
    }


def _document_list_item(document_id: str) -> dict[str, object]:
    return {
        "id": document_id,
        "title": "Weekly AI coding tools update",
        "source_name": "Example Source",
        "status": "processed",
        "language": "en",
        "published_at": "2026-04-27 12:00:00+00:00",
        "summary_text": "Manual effective summary for AI coding tools.",
        "key_points": ["Manual key point about AI coding workflows."],
        "created_at": "2026-04-28 09:30:00+00:00",
    }


def _document_detail_item(document_id: str) -> dict[str, object]:
    return {
        "id": document_id,
        "title": "Weekly AI coding tools update",
        "source_name": "Example Source",
        "url": "https://example.com/doc",
        "status": "processed",
        "language": "en",
        "published_at": "2026-04-27 12:00:00+00:00",
        "summary_en": "Manual effective summary for AI coding tools.",
        "summary_zh": "",
        "key_points": ["Manual key point about AI coding workflows."],
        "entities": ["OpenAI (company)"],
        "topics": ["AI Coding"],
        "content_preview": "Preview text.",
    }


def _source_page_item(source_id: str) -> dict[str, object]:
    return {
        "id": source_id,
        "name": "Example Source",
        "editable_name": "Example Source",
        "source_type": "manual_import",
        "url": "https://example.com/source",
        "credibility_level": "B",
        "fetch_strategy": "manual",
        "is_active": True,
        "activity_label": "active",
        "maintenance_status": "ordinary",
        "notes": "Stable manual source.",
        "last_import_at": "2026-04-28T09:30:00+00:00",
        "last_result": "success",
        "raw_config_json": "{\n  \"rss_url\": \"https://example.com/rss.xml\"\n}",
    }


def _review_summary_item() -> SummaryReviewView:
    document = Document(id=uuid.uuid4(), title="Reviewed summary document")
    summary = DocumentSummary(id=uuid.uuid4(), document_id=document.id, summary_en="Automatic English summary")
    document.summary = summary
    return SummaryReviewView(
        document=document,
        summary=summary,
        auto_values={"summary_zh": "", "summary_en": "Automatic English summary", "key_points": []},
        effective_values={"summary_zh": "", "summary_en": "Automatic English summary", "key_points": []},
        history=[],
    )


def _system_payload() -> dict[str, object]:
    return {
        "checks": [
            {"label": "Database environment", "status": "available", "detail": "ok"},
            {"label": "Database connection", "status": "available", "detail": "ok"},
            {"label": "pgvector", "status": "available", "detail": "ok"},
        ],
        "database_counts": [{"name": "sources", "count": 1}],
        "counts_error": None,
        "storage_files": [{"path": "configs/web/ai_settings.json", "exists_label": "yes", "size_bytes": 64}],
    }


def test_web_mvp_route_level_read_smoke(monkeypatch) -> None:
    document_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    review_item = _review_summary_item()

    monkeypatch.setattr(web_routes.service, "get_dashboard_data", _dashboard_payload)
    monkeypatch.setattr(web_routes.service, "list_document_views", lambda query="", source_id="": ([_document_list_item(document_id)], None))
    monkeypatch.setattr(web_routes.service, "get_document_view", lambda document_id_arg: (_document_detail_item(document_id_arg), None))
    monkeypatch.setattr(web_routes.service, "list_sources", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_source_page_views", lambda: ([_source_page_item(source_id)], None))
    monkeypatch.setattr(web_routes.service, "get_source_page_view", lambda source_id_arg: (_source_page_item(source_id_arg), None))
    monkeypatch.setattr(web_routes.service, "list_review_uncertainties", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_risks", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_opportunities", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_documents", lambda: ([review_item], None))
    monkeypatch.setattr(web_routes.service, "list_ai_providers", lambda: [])
    monkeypatch.setattr(web_routes.service, "list_qa_history", lambda: [])
    monkeypatch.setattr(web_routes.service, "get_system_page_data", _system_payload)

    client = TestClient(create_app())

    dashboard_response = client.get("/web/dashboard")
    documents_response = client.get("/web/documents")
    document_detail_response = client.get(f"/web/documents/{document_id}")
    sources_response = client.get("/web/sources")
    source_detail_response = client.get(f"/web/sources/{source_id}")
    review_response = client.get("/web/review")
    ask_response = client.get("/web/ask")
    system_response = client.get("/web/system")

    assert dashboard_response.status_code == 200
    assert "System Status" in dashboard_response.text
    assert "Weekly AI coding tools update" in dashboard_response.text

    assert documents_response.status_code == 200
    assert "Document List" in documents_response.text
    assert "Filters currently applied" in documents_response.text
    assert "Manual effective summary for AI coding tools." in documents_response.text

    assert document_detail_response.status_code == 200
    assert "Summary EN:" in document_detail_response.text
    assert "OpenAI (company)" in document_detail_response.text

    assert sources_response.status_code == 200
    assert "Source Registry" in sources_response.text
    assert "ordinary" in sources_response.text

    assert source_detail_response.status_code == 200
    assert "Edit Source" in source_detail_response.text
    assert "Maintenance status:" in source_detail_response.text

    assert review_response.status_code == 200
    assert "Summary Review" in review_response.text
    assert "Reviewed summary document" in review_response.text

    assert ask_response.status_code == 200
    assert "Ask from Local Knowledge" in ask_response.text

    assert system_response.status_code == 200
    assert "System Checks" in system_response.text
    assert "Storage Files" in system_response.text


def test_web_mvp_route_level_write_smoke(monkeypatch) -> None:
    review_item = _review_summary_item()
    source_id = str(uuid.uuid4())

    monkeypatch.setattr(web_routes.service, "save_summary_review", lambda summary_id, form: "Summary review saved.")
    monkeypatch.setattr(web_routes.service, "toggle_source", lambda source_id_arg: "Source toggled.")
    monkeypatch.setattr(web_routes.service, "import_source", lambda source_id_arg: "Source imported.")
    monkeypatch.setattr(
        web_routes.service,
        "ask_question",
        lambda question, provider_id="": {
            "question": question,
            "answer": "Bounded answer from local evidence.",
            "answer_mode": "local_only",
            "provider_name": None,
            "evidence": [],
        },
    )
    monkeypatch.setattr(web_routes.service, "list_review_uncertainties", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_risks", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_opportunities", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_documents", lambda: ([review_item], None))

    client = TestClient(create_app())

    summary_response = client.post(f"/web/review/{review_item.summary.id}", data={"summary_en": "Manual summary"}, follow_redirects=False)
    toggle_response = client.post(f"/web/sources/{source_id}/toggle", follow_redirects=False)
    import_response = client.post(f"/web/sources/{source_id}/import", follow_redirects=False)
    ask_response = client.post("/web/ask", data={"question": "What changed?", "provider_id": ""})

    assert summary_response.status_code == 303
    assert summary_response.headers["location"].startswith("/web/review?")
    assert toggle_response.status_code == 303
    assert toggle_response.headers["location"].startswith("/web/sources?")
    assert import_response.status_code == 303
    assert import_response.headers["location"].startswith("/web/sources?")
    assert ask_response.status_code == 200
    assert "Bounded answer from local evidence." in ask_response.text
    assert "Answer" in ask_response.text
