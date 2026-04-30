from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.routes import web as web_routes
from src.domain.models import Document, DocumentEntity, DocumentSummary, DocumentTopic, Entity, Source, Topic
from src.web.service import ProviderConfig, WebMvpService


@pytest.fixture
def workspace_tmp_path() -> Path:
    root = Path("tests") / ".tmp" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


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


def _build_document() -> Document:
    document = Document(
        id=uuid.uuid4(),
        title="Weekly AI coding tools update",
        status="processed",
        language="en",
        url="https://example.com/ai-coding-tools",
        content_text="AI coding tools changed this week with new code review and editing workflows.",
        created_at=datetime(2026, 4, 28, 9, 30, tzinfo=timezone.utc),
        published_at=datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc),
    )
    document.source = Source(id=uuid.uuid4(), name="Example Source")
    document.summary = DocumentSummary(
        id=uuid.uuid4(),
        document_id=document.id,
        summary_en="Automatic English summary.",
        summary_zh="自动中文摘要。",
        key_points=["Automatic key point one", "Automatic key point two"],
    )
    document.document_entities = [
        DocumentEntity(entity=Entity(name="OpenAI", entity_type="company")),
    ]
    document.document_topics = [
        DocumentTopic(topic=Topic(name_en="AI Coding", name_zh="AI 编码")),
    ]
    return document


def _build_source_model() -> Source:
    return Source(
        id=uuid.uuid4(),
        name="Example Source",
        source_type="manual_import",
        url="https://example.com/source",
        credibility_level="B",
        is_active=True,
        fetch_strategy="manual",
        config={
            "rss_url": "https://example.com/rss.xml",
            "_web": {
                "maintenance_status": "ordinary",
                "notes": "Stable manual source.",
                "last_import_at": "2026-04-28T09:30:00+00:00",
                "last_result": "success",
            },
        },
    )


class _QueuedReadSession:
    def __init__(self, *, scalar_values=None, scalars_values=None, execute_rows=None):
        self.scalar_values = list(scalar_values or [])
        self.scalars_values = list(scalars_values or [])
        self.execute_rows = list(execute_rows or [])
        self.closed = False

    def scalar(self, stmt):
        if not self.scalar_values:
            return None
        return self.scalar_values.pop(0)

    def get(self, model, object_id):
        if not self.scalar_values:
            return None
        return self.scalar_values.pop(0)

    def scalars(self, stmt):
        if not self.scalars_values:
            return []
        return self.scalars_values.pop(0)

    def execute(self, stmt):
        rows = self.execute_rows.pop(0) if self.execute_rows else []

        class _Result:
            def __init__(self, data):
                self._data = data

            def all(self):
                return self._data

        return _Result(rows)

    def close(self) -> None:
        self.closed = True


class _FakeDatabaseReviewService:
    def __init__(self, session):
        self.session = session

    def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
        overrides = {
            "summary_en": "Manual effective summary for AI coding tools.",
            "key_points": ["Manual key point about AI coding workflows."],
        }
        return overrides.get(field_name, auto_value)


def test_list_document_views_prefers_reviewed_summary_and_key_points(monkeypatch) -> None:
    service = WebMvpService()
    document = _build_document()
    session = _QueuedReadSession(scalars_values=[[document]])

    monkeypatch.setattr(service, "_try_create_db_session", lambda: session)
    monkeypatch.setattr("src.web.service.DatabaseReviewService", _FakeDatabaseReviewService)

    views, error = service.list_document_views()

    assert error is None
    assert views[0]["title"] == "Weekly AI coding tools update"
    assert views[0]["source_name"] == "Example Source"
    assert views[0]["summary_text"] == "Manual effective summary for AI coding tools."
    assert views[0]["key_points"] == ["Manual key point about AI coding workflows."]


def test_get_document_view_degrades_when_summary_source_and_labels_are_missing(monkeypatch) -> None:
    service = WebMvpService()
    document = _build_document()
    document.title = ""
    document.status = ""
    document.language = None
    document.url = None
    document.source = None
    document.summary = None
    document.content_text = None
    document.document_entities = [DocumentEntity(entity=Entity(name="", entity_type=""))]
    document.document_topics = [DocumentTopic(topic=Topic(name_en="", name_zh=""))]
    session = _QueuedReadSession(scalar_values=[document])

    monkeypatch.setattr(service, "_try_create_db_session", lambda: session)

    view, error = service.get_document_view(str(document.id))

    assert error is None
    assert view is not None
    assert view["title"] == "Untitled document"
    assert view["source_name"] == "-"
    assert view["status"] == "-"
    assert view["language"] == "-"
    assert view["summary_en"] == ""
    assert view["summary_zh"] == ""
    assert view["key_points"] == []
    assert view["entities"] == ["Unnamed entity"]
    assert view["topics"] == ["Unnamed topic"]
    assert view["content_preview"] == ""


def test_get_document_view_returns_empty_entity_and_topic_collections_without_placeholder(monkeypatch) -> None:
    service = WebMvpService()
    document = _build_document()
    document.document_entities = []
    document.document_topics = []
    session = _QueuedReadSession(scalar_values=[document])

    monkeypatch.setattr(service, "_try_create_db_session", lambda: session)

    view, error = service.get_document_view(str(document.id))

    assert error is None
    assert view is not None
    assert view["entities"] == []
    assert view["topics"] == []


def test_get_dashboard_data_returns_stable_recent_document_contract(monkeypatch) -> None:
    service = WebMvpService()
    document = _build_document()
    session = _QueuedReadSession(
        scalar_values=[3, 12, 2, 4],
        scalars_values=[[document]],
        execute_rows=[[("AI Coding", 5)]],
    )

    monkeypatch.setattr(service, "_try_create_db_session", lambda: session)
    monkeypatch.setattr("src.web.service.DatabaseReviewService", _FakeDatabaseReviewService)
    monkeypatch.setattr(service, "list_ai_providers", lambda: [_build_provider()])
    monkeypatch.setattr(service, "list_qa_history", lambda: [{"question": "What changed?", "answer_mode": "local_only"}])

    data = service.get_dashboard_data()

    assert data["counts"] == {"sources": 3, "documents": 12, "watchlist": 2, "reviews": 4}
    assert data["recent_documents"][0]["title"] == "Weekly AI coding tools update"
    assert data["recent_documents"][0]["summary_text"] == "Manual effective summary for AI coding tools."
    assert data["recent_documents"][0]["source_name"] == "Example Source"
    assert data["recent_documents"][0]["status"] == "processed"
    assert data["recent_documents"][0]["published_at"] == "2026-04-27 12:00:00+00:00"
    assert data["top_topics"] == [("AI Coding", 5)]
    assert data["providers"][0].name == "Local QA Provider"
    assert data["system_status"]["database_label"] == "available"
    assert data["system_status"]["database_detail"] == "Counts and recent knowledge changes are available."
    assert data["system_status"]["provider_label"] == "1 provider enabled"
    assert data["system_status"]["knowledge_label"] == "1 recent document available in the dashboard"


def test_get_dashboard_data_uses_neutral_knowledge_label_for_non_reviewable_status(monkeypatch) -> None:
    service = WebMvpService()
    document = _build_document()
    document.status = "failed"
    session = _QueuedReadSession(
        scalar_values=[1, 1, 0, 0],
        scalars_values=[[document]],
        execute_rows=[[]],
    )

    monkeypatch.setattr(service, "_try_create_db_session", lambda: session)
    monkeypatch.setattr("src.web.service.DatabaseReviewService", _FakeDatabaseReviewService)
    monkeypatch.setattr(service, "list_ai_providers", lambda: [])
    monkeypatch.setattr(service, "list_qa_history", lambda: [])

    data = service.get_dashboard_data()

    assert data["recent_documents"][0]["status"] == "failed"
    assert data["system_status"]["knowledge_label"] == "1 recent document available in the dashboard"


def test_get_dashboard_data_degrades_when_database_is_unavailable(monkeypatch) -> None:
    service = WebMvpService()

    monkeypatch.setattr(service, "_try_create_db_session", lambda: None)
    monkeypatch.setattr(service, "list_ai_providers", lambda: [])
    monkeypatch.setattr(service, "list_qa_history", lambda: [])

    data = service.get_dashboard_data()

    assert data["counts"] == {"sources": 0, "documents": 0, "watchlist": 0, "reviews": 0}
    assert data["recent_documents"] == []
    assert data["top_topics"] == []
    assert data["db_error"] == "Database session unavailable."
    assert data["system_status"]["database_label"] == "degraded"
    assert data["system_status"]["database_detail"] == "Database session unavailable."
    assert data["system_status"]["provider_label"] == "No provider configured"
    assert data["system_status"]["knowledge_label"] == "Recent knowledge changes are unavailable."


def test_dashboard_page_renders_recent_summary_and_system_status(monkeypatch, workspace_tmp_path: Path) -> None:
    monkeypatch.setattr(
        web_routes.service,
        "get_dashboard_data",
        lambda: {
            "counts": {"sources": 3, "documents": 12, "watchlist": 2, "reviews": 4},
            "recent_documents": [
                {
                    "id": str(uuid.uuid4()),
                    "title": "Weekly AI coding tools update",
                    "source_name": "Example Source",
                    "created_at": "2026-04-28 09:30:00+00:00",
                    "published_at": "2026-04-27 12:00:00+00:00",
                    "status": "processed",
                    "summary_text": "Manual effective summary for AI coding tools.",
                }
            ],
            "top_topics": [("AI Coding", 5)],
            "providers": [_build_provider()],
            "qa_history": [{"question": "What changed?", "answer_mode": "local_only"}],
            "db_error": None,
            "system_status": {
                "database_label": "available",
                "database_detail": "Counts and recent knowledge changes are available.",
                "provider_label": "1 provider enabled",
                "knowledge_label": "1 recent document available in the dashboard",
            },
        },
        raising=False,
    )

    client = TestClient(create_app())
    response = client.get("/web/dashboard")

    assert response.status_code == 200
    assert "系统状态" in response.text
    assert "数据库:</strong> available" in response.text
    assert "服务商:</strong> 1 provider enabled" in response.text
    assert "知识:</strong> 1 recent document available in the dashboard" in response.text
    assert "Manual effective summary for AI coding tools." in response.text
    assert "processed" in response.text
    assert "2026-04-27 12:00:00+00:00" in response.text


def test_dashboard_page_renders_english_shell_when_lang_query_requests_en(monkeypatch, workspace_tmp_path: Path) -> None:
    monkeypatch.setattr(
        web_routes.service,
        "get_dashboard_data",
        lambda: {
            "counts": {"sources": 3, "documents": 12, "watchlist": 2, "reviews": 4},
            "recent_documents": [],
            "top_topics": [],
            "providers": [],
            "qa_history": [],
            "db_error": None,
            "system_status": {
                "database_label": "available",
                "database_detail": "Counts and recent knowledge changes are available.",
                "provider_label": "1 provider enabled",
                "knowledge_label": "1 recent document available in the dashboard",
            },
        },
        raising=False,
    )

    client = TestClient(create_app())
    response = client.get("/web/dashboard?lang=en")

    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "System Status" in response.text
    assert "Recent Documents" in response.text
    assert "Top Topics" in response.text
    assert "AI Providers" in response.text
    assert "控制台" not in response.text


def test_dashboard_page_renders_empty_and_db_degraded_states(monkeypatch, workspace_tmp_path: Path) -> None:
    monkeypatch.setattr(
        web_routes.service,
        "get_dashboard_data",
        lambda: {
            "counts": {"sources": 0, "documents": 0, "watchlist": 0, "reviews": 0},
            "recent_documents": [],
            "top_topics": [],
            "providers": [],
            "qa_history": [],
            "db_error": "Database session unavailable.",
            "system_status": {
                "database_label": "degraded",
                "database_detail": "Database session unavailable.",
                "provider_label": "No provider configured",
                "knowledge_label": "Recent knowledge changes are unavailable.",
            },
        },
        raising=False,
    )

    client = TestClient(create_app())
    response = client.get("/web/dashboard")

    assert response.status_code == 200
    assert "数据库提示:" in response.text
    assert "部分页面数据暂不可用。" in response.text
    assert "Database session unavailable." in response.text
    assert "数据库:</strong> degraded" in response.text
    assert "暂无最近文档。" in response.text
    assert "暂无主题。" in response.text
    assert "暂无 provider。" in response.text
    assert "暂无最近问答。" in response.text


def test_documents_page_uses_document_view_contract(monkeypatch, workspace_tmp_path: Path) -> None:
    source_id = str(uuid.uuid4())
    monkeypatch.setattr(
        web_routes.service,
        "list_document_views",
        lambda query="", source_id="": (
            [
                {
                    "id": str(uuid.uuid4()),
                    "title": "Weekly AI coding tools update",
                    "source_name": "Example Source",
                    "language": "en",
                    "status": "processed",
                    "published_at": "2026-04-27 12:00:00+00:00",
                    "summary_text": "Manual effective summary for AI coding tools.",
                    "key_points": ["Manual key point about AI coding workflows."],
                }
            ],
            None,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        web_routes.service,
        "list_sources",
        lambda: ([Source(id=uuid.UUID(source_id), name="Example Source")], None),
    )
    monkeypatch.setattr(
        web_routes.service,
        "list_documents",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("old documents path should not be used")),
    )

    client = TestClient(create_app())
    response = client.get(f"/web/documents?q=ai+tools&source_id={source_id}")

    assert response.status_code == 200
    assert "Manual effective summary for AI coding tools." in response.text
    assert "Weekly AI coding tools update" in response.text
    assert "value=\"ai tools\"" in response.text
    assert f"value='{source_id}' selected" in response.text
    assert "当前筛选条件" in response.text
    assert "状态" in response.text
    assert "语言" in response.text
    assert "发布时间" in response.text
    assert "processed" in response.text
    assert "en" in response.text
    assert "2026-04-27 12:00:00+00:00" in response.text


def test_documents_page_renders_empty_state_with_current_filters(monkeypatch, workspace_tmp_path: Path) -> None:
    source_id = str(uuid.uuid4())
    monkeypatch.setattr(web_routes.service, "list_document_views", lambda query="", source_id="": ([], None), raising=False)
    monkeypatch.setattr(
        web_routes.service,
        "list_sources",
        lambda: ([Source(id=uuid.UUID(source_id), name="Example Source")], None),
    )

    client = TestClient(create_app())
    response = client.get(f"/web/documents?q=missing&source_id={source_id}")

    assert response.status_code == 200
    assert "当前筛选条件" in response.text
    assert "missing" in response.text
    assert "Example Source" in response.text
    assert "当前筛选条件下无匹配文档。" in response.text


def test_documents_page_renders_unknown_source_filter_when_source_id_is_unmatched(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    source_id = str(uuid.uuid4())
    monkeypatch.setattr(web_routes.service, "list_document_views", lambda query="", source_id="": ([], None), raising=False)
    monkeypatch.setattr(web_routes.service, "list_sources", lambda: ([], None))

    client = TestClient(create_app())
    response = client.get(f"/web/documents?q=missing&source_id={source_id}")

    assert response.status_code == 200
    assert "当前筛选条件" in response.text
    assert "missing" in response.text
    assert "未知来源筛选" in response.text
    assert "全部来源" not in response.text.split("当前筛选条件", 1)[1]
    assert "当前筛选条件下无匹配文档。" in response.text


def test_documents_page_renders_stable_missing_field_fallbacks(monkeypatch, workspace_tmp_path: Path) -> None:
    monkeypatch.setattr(
        web_routes.service,
        "list_document_views",
        lambda query="", source_id="": (
            [
                {
                    "id": str(uuid.uuid4()),
                    "title": "Untitled document",
                    "source_name": "-",
                    "language": "-",
                    "status": "-",
                    "published_at": "-",
                    "summary_text": "-",
                    "key_points": [],
                }
            ],
            None,
        ),
        raising=False,
    )
    monkeypatch.setattr(web_routes.service, "list_sources", lambda: ([], None))

    client = TestClient(create_app())
    response = client.get("/web/documents")

    assert response.status_code == 200
    assert "Untitled document" in response.text
    assert "<td>-</td>" in response.text


def test_documents_page_renders_empty_state_without_filters(monkeypatch, workspace_tmp_path: Path) -> None:
    monkeypatch.setattr(web_routes.service, "list_document_views", lambda query="", source_id="": ([], None), raising=False)
    monkeypatch.setattr(web_routes.service, "list_sources", lambda: ([], None))

    client = TestClient(create_app())
    response = client.get("/web/documents")

    assert response.status_code == 200
    assert "当前筛选条件" in response.text
    assert "查询:</strong> 无" in response.text
    assert "来源:</strong> 全部来源" in response.text
    assert "暂无文档。" in response.text


def test_document_detail_uses_document_view_contract(monkeypatch, workspace_tmp_path: Path) -> None:
    document_id = str(uuid.uuid4())
    monkeypatch.setattr(
        web_routes.service,
        "get_document_view",
        lambda document_id_arg: (
            {
                "id": document_id_arg,
                "title": "Weekly AI coding tools update",
                "source_name": "-",
                "url": "",
                "status": "-",
                "language": "-",
                "published_at": "-",
                "summary_en": "Manual effective summary for AI coding tools.",
                "summary_zh": "",
                "key_points": ["Manual key point about AI coding workflows."],
                "entities": ["Unnamed entity"],
                "topics": ["Unnamed topic"],
                "content_preview": "",
            },
            None,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        web_routes.service,
        "get_document",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("old detail path should not be used")),
    )

    client = TestClient(create_app())
    response = client.get(f"/web/documents/{document_id}")

    assert response.status_code == 200
    assert "Manual effective summary for AI coding tools." in response.text
    assert "Manual key point about AI coding workflows." in response.text
    assert "Unnamed entity" in response.text
    assert "Unnamed topic" in response.text


def test_document_detail_renders_empty_entity_and_topic_states(monkeypatch, workspace_tmp_path: Path) -> None:
    document_id = str(uuid.uuid4())
    monkeypatch.setattr(
        web_routes.service,
        "get_document_view",
        lambda document_id_arg: (
            {
                "id": document_id_arg,
                "title": "Weekly AI coding tools update",
                "source_name": "-",
                "url": "",
                "status": "-",
                "language": "-",
                "published_at": "-",
                "summary_en": "",
                "summary_zh": "",
                "key_points": [],
                "entities": [],
                "topics": [],
                "content_preview": "",
            },
            None,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        web_routes.service,
        "get_document",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("old detail path should not be used")),
    )

    client = TestClient(create_app())
    response = client.get(f"/web/documents/{document_id}")

    assert response.status_code == 200
    assert "暂无实体。" in response.text
    assert "暂无主题。" in response.text
    assert "Unnamed entity" not in response.text
    assert "Unnamed topic" not in response.text


def test_list_source_page_views_returns_stable_contract(monkeypatch) -> None:
    service = WebMvpService()
    source = _build_source_model()
    session = _QueuedReadSession(scalars_values=[[source]])

    monkeypatch.setattr(service, "_try_create_db_session", lambda: session)

    views, error = service.list_source_page_views()

    assert error is None
    assert views[0]["name"] == "Example Source"
    assert views[0]["source_type"] == "manual_import"
    assert views[0]["url"] == "https://example.com/source"
    assert views[0]["credibility_level"] == "B"
    assert views[0]["fetch_strategy"] == "manual"
    assert views[0]["is_active"] is True
    assert views[0]["activity_label"] == "active"
    assert views[0]["maintenance_status"] == "ordinary"
    assert views[0]["notes"] == "Stable manual source."
    assert views[0]["last_import_at"] == "2026-04-28T09:30:00+00:00"
    assert views[0]["last_result"] == "success"
    assert "rss_url" in views[0]["raw_config_json"]


def test_get_source_page_view_degrades_missing_fields(monkeypatch) -> None:
    service = WebMvpService()
    source = _build_source_model()
    source.name = ""
    source.url = None
    source.fetch_strategy = ""
    source.config = {"_web": {"maintenance_status": "", "notes": "", "last_import_at": None, "last_result": None}}
    session = _QueuedReadSession(scalar_values=[source])

    monkeypatch.setattr(service, "_try_create_db_session", lambda: session)

    view, error = service.get_source_page_view(str(source.id))

    assert error is None
    assert view is not None
    assert view["name"] == "Unnamed source"
    assert view["editable_name"] == ""
    assert view["url"] == "-"
    assert view["fetch_strategy"] == "-"
    assert view["maintenance_status"] == "ordinary"
    assert view["notes"] == ""
    assert view["last_import_at"] == "-"
    assert view["last_result"] == "-"


def test_sources_page_uses_source_page_view_contract(monkeypatch, workspace_tmp_path: Path) -> None:
    source_id = str(uuid.uuid4())
    monkeypatch.setattr(
        web_routes.service,
        "list_source_page_views",
        lambda: (
            [
                {
                    "id": source_id,
                    "name": "Example Source",
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
            ],
            None,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        web_routes.service,
        "list_source_views",
        lambda: (_ for _ in ()).throw(AssertionError("old source view path should not be used")),
    )

    client = TestClient(create_app())
    response = client.get("/web/sources")

    assert response.status_code == 200
    assert "来源目录" in response.text
    assert "Example Source" in response.text
    assert "manual_import" in response.text
    assert "ordinary" in response.text
    assert "success" in response.text
    assert "/web/sources/" in response.text


def test_sources_page_renders_english_shell_when_lang_query_requests_en(monkeypatch, workspace_tmp_path: Path) -> None:
    source_id = str(uuid.uuid4())
    monkeypatch.setattr(
        web_routes.service,
        "list_source_page_views",
        lambda: (
            [
                {
                    "id": source_id,
                    "name": "Example Source",
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
                    "raw_config_json": "{}",
                }
            ],
            None,
        ),
        raising=False,
    )

    client = TestClient(create_app())
    response = client.get("/web/sources?lang=en")

    assert response.status_code == 200
    assert "Sources" in response.text
    assert "Source Registry" in response.text
    assert "Add Source" in response.text
    assert "Create Source" in response.text
    assert "来源目录" not in response.text


def test_sources_page_renders_empty_and_db_degraded_states(monkeypatch, workspace_tmp_path: Path) -> None:
    monkeypatch.setattr(web_routes.service, "list_source_page_views", lambda: ([], "Database session unavailable."), raising=False)

    client = TestClient(create_app())
    response = client.get("/web/sources")

    assert response.status_code == 200
    assert "数据库提示:" in response.text
    assert "部分页面数据暂不可用。" in response.text
    assert "Database session unavailable." in response.text
    assert "暂无来源。" in response.text


def test_source_detail_uses_source_page_view_contract(monkeypatch, workspace_tmp_path: Path) -> None:
    source_id = str(uuid.uuid4())
    monkeypatch.setattr(
        web_routes.service,
        "get_source_page_view",
        lambda source_id_arg: (
            {
                "id": source_id_arg,
                "name": "Example Source",
                "source_type": "manual_import",
                "url": "https://example.com/source",
                "credibility_level": "B",
                "fetch_strategy": "manual",
                "is_active": True,
                "activity_label": "active",
                "maintenance_status": "formal_seed",
                "notes": "Stable manual source.",
                "last_import_at": "2026-04-28T09:30:00+00:00",
                "last_result": "success",
                "raw_config_json": "{\n  \"rss_url\": \"https://example.com/rss.xml\"\n}",
            },
            None,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        web_routes.service,
        "get_source_view",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("old source detail path should not be used")),
    )

    client = TestClient(create_app())
    response = client.get(f"/web/sources/{source_id}")

    assert response.status_code == 200
    assert "编辑来源" in response.text
    assert "维护状态" in response.text
    assert "formal_seed" in response.text
    assert "正式种子基线状态可在此查看，但不能通过普通 Web 表单编辑。" in response.text
    assert "Stable manual source." in response.text
    assert "success" in response.text


def test_source_detail_does_not_write_display_fallback_back_into_name_input(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    source_id = str(uuid.uuid4())
    monkeypatch.setattr(
        web_routes.service,
        "get_source_page_view",
        lambda source_id_arg: (
            {
                "id": source_id_arg,
                "name": "Unnamed source",
                "editable_name": "",
                "source_type": "manual_import",
                "url": "-",
                "credibility_level": "B",
                "fetch_strategy": "manual",
                "is_active": True,
                "activity_label": "active",
                "maintenance_status": "ordinary",
                "notes": "",
                "last_import_at": "-",
                "last_result": "-",
                "raw_config_json": "",
            },
            None,
        ),
        raising=False,
    )

    client = TestClient(create_app())
    response = client.get(f"/web/sources/{source_id}")

    assert response.status_code == 200
    assert "Unnamed source" in response.text
    assert 'name="name" value=""' in response.text
    assert 'name="name" value="Unnamed source"' not in response.text


def test_get_system_page_data_returns_stable_contract(monkeypatch) -> None:
    service = WebMvpService()
    session = _QueuedReadSession(scalar_values=[3, 12, 11, 7, 5, 2, 4])
    probe_ok = type("ProbeResult", (), {"ok": True, "detail": "ok"})()

    monkeypatch.setattr("src.web.service.probe_database_environment", lambda: probe_ok)
    monkeypatch.setattr("src.web.service.probe_database_connection", lambda: probe_ok)
    monkeypatch.setattr("src.web.service.probe_pgvector_extension", lambda: probe_ok)
    monkeypatch.setattr(service, "_try_create_db_session", lambda: session)

    data = service.get_system_page_data()

    assert data["checks"][0]["label"] == "Database environment"
    assert data["checks"][0]["status"] == "available"
    assert data["checks"][0]["detail"] == "ok"
    assert data["database_counts"][0] == {"name": "sources", "count": 3}
    assert data["database_counts"][-1] == {"name": "review_edits", "count": 4}
    assert data["counts_error"] is None
    assert len(data["storage_files"]) == 2


def test_get_system_page_data_degrades_when_counts_are_unavailable(monkeypatch) -> None:
    service = WebMvpService()
    probe_fail = type("ProbeResult", (), {"ok": False, "detail": "Database session unavailable."})()

    monkeypatch.setattr("src.web.service.probe_database_environment", lambda: probe_fail)
    monkeypatch.setattr("src.web.service.probe_database_connection", lambda: probe_fail)
    monkeypatch.setattr("src.web.service.probe_pgvector_extension", lambda: probe_fail)
    monkeypatch.setattr(service, "_try_create_db_session", lambda: None)

    data = service.get_system_page_data()

    assert data["checks"][0]["status"] == "degraded"
    assert data["database_counts"] == []
    assert data["counts_error"] == "Database session unavailable."


def test_get_system_page_data_prefers_real_counts_query_error(monkeypatch) -> None:
    service = WebMvpService()
    probe_ok = type("ProbeResult", (), {"ok": True, "detail": "ok"})()

    class _FailingCountSession:
        def scalar(self, stmt):
            raise RuntimeError("count query timeout")

        def close(self) -> None:
            return None

    monkeypatch.setattr("src.web.service.probe_database_environment", lambda: probe_ok)
    monkeypatch.setattr("src.web.service.probe_database_connection", lambda: probe_ok)
    monkeypatch.setattr("src.web.service.probe_pgvector_extension", lambda: probe_ok)
    monkeypatch.setattr(service, "_try_create_db_session", lambda: _FailingCountSession())

    data = service.get_system_page_data()

    assert data["checks"][0]["status"] == "available"
    assert data["database_counts"] == []
    assert data["counts_error"] == "RuntimeError: count query timeout"


def test_system_page_uses_system_page_data_contract(monkeypatch, workspace_tmp_path: Path) -> None:
    monkeypatch.setattr(
        web_routes.service,
        "get_system_page_data",
        lambda: {
            "checks": [
                {"label": "Database environment", "status": "available", "detail": "ok"},
                {"label": "Database connection", "status": "available", "detail": "ok"},
                {"label": "pgvector", "status": "available", "detail": "ok"},
            ],
            "database_counts": [{"name": "sources", "count": 3}],
            "counts_error": None,
            "storage_files": [
                {"path": "configs/web/ai_settings.json", "exists_label": "yes", "size_bytes": 128},
                {"path": "configs/web/qa_history.json", "exists_label": "no", "size_bytes": 0},
            ],
        },
        raising=False,
    )
    monkeypatch.setattr(
        web_routes.service,
        "get_system_status",
        lambda: (_ for _ in ()).throw(AssertionError("old system status path should not be used")),
    )

    client = TestClient(create_app())
    response = client.get("/web/system")

    assert response.status_code == 200
    assert "系统检查" in response.text
    assert "存储文件" in response.text
    assert "数据库计数" in response.text
    assert "Database environment" in response.text
    assert "available" in response.text
    assert "configs/web/ai_settings.json" in response.text
    assert "yes" in response.text


def test_system_page_renders_empty_and_degraded_states(monkeypatch, workspace_tmp_path: Path) -> None:
    monkeypatch.setattr(
        web_routes.service,
        "get_system_page_data",
        lambda: {
            "checks": [
                {"label": "Database environment", "status": "degraded", "detail": "Database session unavailable."},
                {"label": "Database connection", "status": "degraded", "detail": "Database session unavailable."},
            ],
            "database_counts": [],
            "counts_error": "Database session unavailable.",
            "storage_files": [],
        },
        raising=False,
    )

    client = TestClient(create_app())
    response = client.get("/web/system")

    assert response.status_code == 200
    assert "数据库提示:" in response.text
    assert "部分页面数据暂不可用。" in response.text
    assert "Database session unavailable." in response.text
    assert "暂无数据库计数。" in response.text
    assert "暂无存储文件。" in response.text


def test_system_page_renders_real_counts_query_error(monkeypatch, workspace_tmp_path: Path) -> None:
    monkeypatch.setattr(
        web_routes.service,
        "get_system_page_data",
        lambda: {
            "checks": [
                {"label": "Database environment", "status": "available", "detail": "ok"},
                {"label": "Database connection", "status": "available", "detail": "ok"},
                {"label": "pgvector", "status": "available", "detail": "ok"},
            ],
            "database_counts": [],
            "counts_error": "RuntimeError: count query timeout",
            "storage_files": [],
        },
        raising=False,
    )

    client = TestClient(create_app())
    response = client.get("/web/system")

    assert response.status_code == 200
    assert "数据库提示:" in response.text
    assert "部分页面数据暂不可用。" in response.text
    assert "RuntimeError: count query timeout" in response.text
