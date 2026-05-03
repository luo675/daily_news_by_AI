from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.routes import web as web_routes
from src.domain.enums import PriorityLevel, WatchlistStatus
from src.domain.models import Document, DocumentSummary, Entity, WatchlistItem
from src.web.service import ProviderConfig, SummaryReviewView


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


def _provider_config() -> ProviderConfig:
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
        notes="Keep local evidence bounded.",
        last_test_status="valid",
        last_test_message="Connected successfully.",
        updated_at="2026-04-28T09:30:00+00:00",
    )


def _watchlist_page_item() -> dict[str, object]:
    return {
        "id": str(uuid.uuid4()),
        "item_value": "OpenAI",
        "item_type": "company",
        "priority_level": PriorityLevel.HIGH.value,
        "status": WatchlistStatus.ACTIVE.value,
        "group_name": "AI Labs",
        "notes": "Track model releases.",
        "linked_entity": "OpenAI (company)",
        "updated_at": "2026-04-29 08:00:00+00:00",
        "created_at": "2026-04-28 08:00:00+00:00",
        "related_documents": [
            {
                "id": str(uuid.uuid4()),
                "title": "GPT-5 launch notes",
                "source_name": "Example Source",
                "published_at": "2026-04-29 07:00:00+00:00",
                "created_at": "2026-04-29 08:00:00+00:00",
            }
        ],
    }


def test_web_mvp_service_returns_watchlist_page_view_contract(monkeypatch) -> None:
    service = web_routes.WebMvpService()
    item = WatchlistItem(
        id=uuid.uuid4(),
        item_type="company",
        item_value="OpenAI",
        priority_level=PriorityLevel.HIGH.value,
        status=WatchlistStatus.ACTIVE.value,
        group_name="AI Labs",
        notes="Track model releases.",
        entity=Entity(id=uuid.uuid4(), entity_type="company", name=""),
        created_at=datetime(2026, 4, 28, 8, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 29, 8, 0, tzinfo=timezone.utc),
    )
    documents = [
        Document(id=uuid.uuid4(), title=f"Related document {index}", content_text="OpenAI")
        for index in range(4)
    ]

    monkeypatch.setattr(service, "list_watchlist_items", lambda: ([item], None))
    monkeypatch.setattr(service, "list_watchlist_hits", lambda item_value: documents)

    views, error = service.list_watchlist_page_views()

    assert error is None
    assert views == [
        {
            "id": str(item.id),
            "item_value": "OpenAI",
            "item_type": "company",
            "priority_level": "high",
            "status": "active",
            "group_name": "AI Labs",
            "notes": "Track model releases.",
            "linked_entity": "Unnamed entity",
            "updated_at": "2026-04-29 08:00:00+00:00",
            "created_at": "2026-04-28 08:00:00+00:00",
            "related_documents": [
                {
                    "id": str(documents[0].id),
                    "title": "Related document 0",
                    "source_name": "-",
                    "published_at": "-",
                    "created_at": "-",
                },
                {
                    "id": str(documents[1].id),
                    "title": "Related document 1",
                    "source_name": "-",
                    "published_at": "-",
                    "created_at": "-",
                },
                {
                    "id": str(documents[2].id),
                    "title": "Related document 2",
                    "source_name": "-",
                    "published_at": "-",
                    "created_at": "-",
                },
            ],
        }
    ]


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
    assert "系统状态" in dashboard_response.text
    assert "Weekly AI coding tools update" in dashboard_response.text
    assert "/web/import" in dashboard_response.text

    assert documents_response.status_code == 200
    assert "文档列表" in documents_response.text
    assert "当前筛选条件" in documents_response.text
    assert "Manual effective summary for AI coding tools." in documents_response.text

    assert document_detail_response.status_code == 200
    assert "英文摘要：" in document_detail_response.text
    assert "OpenAI (company)" in document_detail_response.text

    assert sources_response.status_code == 200
    assert "来源目录" in sources_response.text
    assert "ordinary" in sources_response.text

    assert source_detail_response.status_code == 200
    assert "编辑来源" in source_detail_response.text
    assert "维护状态：" in source_detail_response.text

    assert review_response.status_code == 200
    assert "摘要审阅" in review_response.text
    assert "Reviewed summary document" in review_response.text

    assert ask_response.status_code == 200
    assert "基于本地知识提问" in ask_response.text

    assert system_response.status_code == 200
    assert "系统检查" in system_response.text
    assert "存储文件" in system_response.text


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
    assert "回答" in ask_response.text


def test_web_mvp_lang_query_forces_english_and_persists_cookie(monkeypatch) -> None:
    monkeypatch.setattr(web_routes.service, "get_dashboard_data", _dashboard_payload)

    client = TestClient(create_app())
    response = client.get("/web/dashboard?lang=en")

    assert response.status_code == 200
    assert "System Status" in response.text
    assert "系统状态" not in response.text
    assert "daily_news_lang=en" in response.headers.get("set-cookie", "")


def test_web_mvp_lang_cookie_is_used_when_query_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(web_routes.service, "get_dashboard_data", _dashboard_payload)

    client = TestClient(create_app())
    client.cookies.set("daily_news_lang", "en")
    response = client.get("/web/dashboard")

    assert response.status_code == 200
    assert "System Status" in response.text
    assert "系统状态" not in response.text


def test_web_entry_redirect_preserves_explicit_lang_query() -> None:
    client = TestClient(create_app())

    response = client.get("/web?lang=en", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/web/dashboard?lang=en"
    assert "daily_news_lang=en" in response.headers.get("set-cookie", "")


def test_web_entry_redirect_uses_lang_cookie_fallback_when_query_missing() -> None:
    client = TestClient(create_app())
    client.cookies.set("daily_news_lang", "en")

    response = client.get("/web", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/web/dashboard?lang=en"


def test_web_mvp_lang_query_renders_english_shell_for_sources_and_review(monkeypatch) -> None:
    source_id = str(uuid.uuid4())
    review_item = _review_summary_item()

    monkeypatch.setattr(web_routes.service, "list_source_page_views", lambda: ([_source_page_item(source_id)], None))
    monkeypatch.setattr(web_routes.service, "list_review_uncertainties", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_risks", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_opportunities", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_documents", lambda: ([review_item], None))

    client = TestClient(create_app())
    sources_response = client.get("/web/sources?lang=en")
    review_response = client.get("/web/review?lang=en")

    assert sources_response.status_code == 200
    assert "Source Registry" in sources_response.text
    assert "Add Source" in sources_response.text
    assert "来源目录" not in sources_response.text

    assert review_response.status_code == 200
    assert "Summary Review" in review_response.text
    assert "Automatic Result" in review_response.text
    assert "摘要审阅" not in review_response.text


def test_web_mvp_lang_query_renders_english_shell_for_watchlist_ai_settings_and_system(monkeypatch) -> None:
    monkeypatch.setattr(web_routes.service, "list_watchlist_page_views", lambda: ([_watchlist_page_item()], None))
    monkeypatch.setattr(web_routes.service, "list_watchlist_type_values", lambda: ["company", "product"])
    monkeypatch.setattr(web_routes.service, "list_priority_values", lambda: ["high", "medium", "low"])
    provider = _provider_config()
    monkeypatch.setattr(web_routes.service, "list_ai_providers", lambda: [provider])
    monkeypatch.setattr(web_routes.service, "list_ai_task_values", lambda: ["summarization", "analysis", "qa"])
    monkeypatch.setattr(web_routes.service, "get_system_page_data", _system_payload)

    client = TestClient(create_app())
    watchlist_response = client.get("/web/watchlist?lang=en")
    ai_settings_response = client.get("/web/ai-settings?lang=en")
    system_response = client.get("/web/system?lang=en")

    assert watchlist_response.status_code == 200
    assert "Add Watchlist Item" in watchlist_response.text
    assert "Related Documents" in watchlist_response.text
    assert "Type" in watchlist_response.text
    assert "Priority" in watchlist_response.text
    assert "Status" in watchlist_response.text
    assert "Group" in watchlist_response.text
    assert "Notes" in watchlist_response.text
    assert "Linked entity" in watchlist_response.text
    assert "Updated" in watchlist_response.text
    assert "Created" in watchlist_response.text
    assert "AI Labs" in watchlist_response.text
    assert "Track model releases." in watchlist_response.text
    assert "GPT-5 launch notes" in watchlist_response.text

    assert ai_settings_response.status_code == 200
    assert "Save Provider" in ai_settings_response.text
    assert "Configured Providers" in ai_settings_response.text
    assert "Supported tasks" in ai_settings_response.text
    assert provider.masked_key in ai_settings_response.text
    assert "secret-key" not in ai_settings_response.text
    assert "/web/ai-settings/provider-1?lang=en" in ai_settings_response.text
    assert "/web/ai-settings/provider-1/test?lang=en" in ai_settings_response.text
    assert 'action="/web/ai-settings?lang=en"' in ai_settings_response.text

    assert system_response.status_code == 200
    assert "System Checks" in system_response.text
    assert "Path" in system_response.text
    assert "Exists" in system_response.text
    assert "Size (bytes)" in system_response.text


def test_web_ai_settings_redirects_preserve_lang_context(monkeypatch) -> None:
    monkeypatch.setattr(web_routes.service, "save_ai_provider", lambda form: "AI provider saved.")
    monkeypatch.setattr(web_routes.service, "test_ai_provider", lambda provider_id: "Provider test status: valid.")

    client = TestClient(create_app())

    save_response = client.post(
        "/web/ai-settings?lang=en",
        data={"name": "Local QA Provider"},
        follow_redirects=False,
    )
    test_response = client.post(
        "/web/ai-settings/provider-1/test?lang=en",
        follow_redirects=False,
    )

    assert save_response.status_code == 303
    assert save_response.headers["location"].startswith("/web/ai-settings?lang=en")
    assert "message=" in save_response.headers["location"]

    assert test_response.status_code == 303
    assert test_response.headers["location"].startswith("/web/ai-settings/provider-1?lang=en")
    assert "message=" in test_response.headers["location"]


def test_web_mvp_default_language_renders_chinese_shell_for_watchlist_ai_settings_and_system(monkeypatch) -> None:
    monkeypatch.setattr(web_routes.service, "list_watchlist_page_views", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_watchlist_type_values", lambda: ["company", "product"])
    monkeypatch.setattr(web_routes.service, "list_priority_values", lambda: ["high", "medium", "low"])
    monkeypatch.setattr(web_routes.service, "list_ai_providers", lambda: [])
    monkeypatch.setattr(web_routes.service, "list_ai_task_values", lambda: ["summarization", "analysis", "qa"])
    monkeypatch.setattr(web_routes.service, "get_system_page_data", _system_payload)

    client = TestClient(create_app())
    watchlist_response = client.get("/web/watchlist")
    ai_settings_response = client.get("/web/ai-settings")
    system_response = client.get("/web/system")

    assert watchlist_response.status_code == 200
    assert "新增观察项" in watchlist_response.text
    assert "暂无观察项。" in watchlist_response.text
    assert "Add Watchlist Item" not in watchlist_response.text

    assert ai_settings_response.status_code == 200
    assert "保存服务商" in ai_settings_response.text
    assert "已配置服务商" in ai_settings_response.text
    assert "Save Provider" not in ai_settings_response.text

    assert system_response.status_code == 200
    assert "系统检查" in system_response.text
    assert "路径" in system_response.text
    assert "Path" not in system_response.text


def test_web_watchlist_renders_shared_database_note_when_db_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(web_routes.service, "list_watchlist_page_views", lambda: ([], "Database session unavailable."))
    monkeypatch.setattr(web_routes.service, "list_watchlist_type_values", lambda: ["company", "product"])
    monkeypatch.setattr(web_routes.service, "list_priority_values", lambda: ["high", "medium", "low"])

    client = TestClient(create_app())
    response = client.get("/web/watchlist?lang=en")

    assert response.status_code == 200
    assert "Database note" in response.text
    assert "Some page data is unavailable." in response.text
    assert "No watchlist items yet." in response.text


def test_web_mvp_review_history_is_collapsed_by_default(monkeypatch) -> None:
    review_item = _review_summary_item()
    review_item.history = [
        type(
            "ReviewEditRow",
            (),
            {
                "field_name": "summary_en",
                "new_value": "Manual summary",
                "created_at": datetime(2026, 4, 29, 8, 0, tzinfo=timezone.utc),
            },
        )()
    ]

    monkeypatch.setattr(web_routes.service, "list_review_uncertainties", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_risks", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_opportunities", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_documents", lambda: ([review_item], None))

    client = TestClient(create_app())
    response = client.get("/web/review")

    assert response.status_code == 200
    assert "review-history" in response.text
    assert "summary_en -> Manual summary" in response.text
    assert "<details" in response.text
