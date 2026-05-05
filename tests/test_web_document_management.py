from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.routes import web as web_routes
from src.domain.models import Document, Source
from src.web.service import WebMvpService


def _workspace_tmp_path() -> Path:
    root = Path("tests") / ".tmp" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cleanup_workspace(root: Path) -> None:
    shutil.rmtree(root, ignore_errors=True)


def _document_payload(document_id: str) -> dict[str, object]:
    return {
        "id": document_id,
        "title": "Weekly AI coding tools update",
        "source_name": "Example Source",
        "url": "https://example.com/doc",
        "status": "processed",
        "language": "en",
        "published_at": "2026-04-27 12:00:00+00:00",
        "summary_en": "",
        "summary_zh": "",
        "key_points": [],
        "entities": [],
        "topics": [],
        "content_preview": "Original preview text.",
    }


def _edit_payload(document_id: str) -> dict[str, object]:
    return {
        "id": document_id,
        "title": "Weekly AI coding tools update",
        "source_name": "Example Source",
        "url": "https://example.com/doc",
        "language": "en",
        "published_at": "2026-04-27T12:00:00+00:00",
        "content_text": "Original article text.",
        "needs_reprocess": False,
    }


def _detail_payload(
    document_id: str,
    *,
    archived: bool = False,
    archived_at: str | None = None,
) -> dict[str, object]:
    return {
        "id": document_id,
        "title": "Weekly AI coding tools update",
        "source_name": "Example Source",
        "url": "https://example.com/doc",
        "status": "processed",
        "language": "en",
        "published_at": "2026-04-27 12:00:00+00:00",
        "summary_en": "",
        "summary_zh": "",
        "key_points": [],
        "entities": [],
        "topics": [],
        "content_preview": "Original preview text.",
        "needs_reprocess": False,
        "archived": archived,
        "archived_at": archived_at,
    }


def test_document_detail_exposes_edit_entry(monkeypatch) -> None:
    document_id = str(uuid.uuid4())
    monkeypatch.setattr(web_routes.service, "get_document_view", lambda requested_id: (_detail_payload(requested_id), None))

    client = TestClient(create_app())
    response_zh = client.get(f"/web/documents/{document_id}")
    response_en = client.get(f"/web/documents/{document_id}?lang=en")

    assert response_zh.status_code == 200
    assert "编辑文章" in response_zh.text
    assert f"/web/documents/{document_id}/edit?lang=zh" in response_zh.text
    assert "Edit document" not in response_zh.text

    assert response_en.status_code == 200
    assert "Edit document" in response_en.text
    assert f"/web/documents/{document_id}/edit?lang=en" in response_en.text


def test_document_detail_exposes_archive_and_restore_entries(monkeypatch) -> None:
    document_id = str(uuid.uuid4())
    monkeypatch.setattr(web_routes.service, "get_document_view", lambda requested_id: (_detail_payload(requested_id), None))

    client = TestClient(create_app())
    response = client.get(f"/web/documents/{document_id}?lang=en")

    assert response.status_code == 200
    assert "Archive document" in response.text
    assert f"/web/documents/{document_id}/archive?lang=en" in response.text
    assert "Restore document" not in response.text


def test_archived_document_detail_shows_restore_entry(monkeypatch) -> None:
    document_id = str(uuid.uuid4())
    monkeypatch.setattr(
        web_routes.service,
        "get_document_view",
        lambda requested_id: (_detail_payload(requested_id, archived=True, archived_at="2026-04-30T10:00:00+00:00"), None),
    )

    client = TestClient(create_app())
    response = client.get(f"/web/documents/{document_id}?lang=en")

    assert response.status_code == 200
    assert "Archived" in response.text
    assert "Restore document" in response.text
    assert f"/web/documents/{document_id}/restore?lang=en" in response.text
    assert "Archive document" not in response.text


def test_document_edit_page_renders_existing_fields(monkeypatch) -> None:
    document_id = str(uuid.uuid4())
    monkeypatch.setattr(web_routes.service, "get_document_edit_view", lambda requested_id: (_edit_payload(requested_id), None))

    client = TestClient(create_app())
    response = client.get(f"/web/documents/{document_id}/edit")

    assert response.status_code == 200
    assert "Weekly AI coding tools update" in response.text
    assert "https://example.com/doc" in response.text
    assert "Original article text." in response.text
    assert "Published time" not in response.text
    assert "发布时间" in response.text


def test_document_edit_submit_updates_title_and_redirects(monkeypatch) -> None:
    document_id = str(uuid.uuid4())
    state = {
        "title": "Weekly AI coding tools update",
        "needs_reprocess": False,
    }

    def _get_document_view(requested_id: str):
        return (
            {
                "id": requested_id,
                "title": state["title"],
                "source_name": "Example Source",
                "url": "https://example.com/doc",
                "status": "processed",
                "language": "en",
                "published_at": "2026-04-27 12:00:00+00:00",
                "summary_en": "",
                "summary_zh": "",
                "key_points": [],
                "entities": [],
                "topics": [],
                "content_preview": "Original article text.",
                "needs_reprocess": state["needs_reprocess"],
            },
            None,
        )

    def _update_document_basic_fields(requested_id: str, payload: dict[str, str]):
        state["title"] = payload["title"]
        return None, False

    monkeypatch.setattr(web_routes.service, "get_document_view", _get_document_view)
    monkeypatch.setattr(web_routes.service, "get_document_edit_view", lambda requested_id: (_edit_payload(requested_id), None))
    monkeypatch.setattr(web_routes.service, "update_document_basic_fields", _update_document_basic_fields)

    client = TestClient(create_app())
    response = client.post(
        f"/web/documents/{document_id}/edit",
        data={
            "title": "Updated title",
            "url": "https://example.com/doc",
            "language": "en",
            "published_at": "2026-04-27T12:00:00+00:00",
            "content_text": "Original article text.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"/web/documents/{document_id}")

    detail_response = client.get(f"/web/documents/{document_id}")
    assert detail_response.status_code == 200
    assert "Updated title" in detail_response.text


def test_document_edit_rejects_invalid_published_at(monkeypatch) -> None:
    document_id = str(uuid.uuid4())
    called = {"count": 0}

    monkeypatch.setattr(web_routes.service, "get_document_edit_view", lambda requested_id: (_edit_payload(requested_id), None))

    def _should_not_be_called(*args, **kwargs):
        called["count"] += 1
        raise AssertionError("service update should not be called for invalid published_at")

    monkeypatch.setattr(web_routes.service, "update_document_basic_fields", _should_not_be_called)

    client = TestClient(create_app())
    response = client.post(
        f"/web/documents/{document_id}/edit",
        data={
            "title": "Weekly AI coding tools update",
            "url": "https://example.com/doc",
            "language": "en",
            "published_at": "not-a-time",
            "content_text": "Original article text.",
        },
    )

    assert response.status_code == 200
    assert "发布时间格式错误" in response.text
    assert called["count"] == 0


def test_document_edit_submit_rejects_invalid_document_id_without_500(monkeypatch) -> None:
    monkeypatch.setattr(
        web_routes.service,
        "update_document_basic_fields",
        lambda *args, **kwargs: ("invalid_document_id", False),
    )
    monkeypatch.setattr(
        web_routes.service,
        "get_document_edit_view",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("detail lookup should not run for invalid id")),
    )

    client = TestClient(create_app())
    response = client.post(
        "/web/documents/not-a-uuid/edit",
        data={
            "title": "Weekly AI coding tools update",
            "url": "https://example.com/doc",
            "language": "en",
            "published_at": "2026-04-27T12:00:00+00:00",
            "content_text": "Original article text.",
        },
    )

    assert response.status_code == 200
    assert "无效文档 ID" in response.text
    assert "鍙戝竷鏃堕棿鏍煎紡閿欒" not in response.text


def test_document_edit_submit_handles_database_unavailable_without_500(monkeypatch) -> None:
    monkeypatch.setattr(
        web_routes.service,
        "update_document_basic_fields",
        lambda *args, **kwargs: ("database_unavailable", False),
    )
    monkeypatch.setattr(
        web_routes.service,
        "get_document_edit_view",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("detail lookup should not run when db is unavailable")),
    )

    client = TestClient(create_app())
    response = client.post(
        f"/web/documents/{uuid.uuid4()}/edit",
        data={
            "title": "Weekly AI coding tools update",
            "url": "https://example.com/doc",
            "language": "en",
            "published_at": "2026-04-27T12:00:00+00:00",
            "content_text": "Original article text.",
        },
    )

    assert response.status_code == 200
    assert "数据库会话不可用" in response.text


def test_document_edit_handles_missing_document_without_500(monkeypatch) -> None:
    document_id = str(uuid.uuid4())
    monkeypatch.setattr(web_routes.service, "get_document_edit_view", lambda requested_id: (None, "Document not found."))
    monkeypatch.setattr(web_routes.service, "update_document_basic_fields", lambda *args, **kwargs: ("document_not_found", False))

    client = TestClient(create_app())
    response = client.get(f"/web/documents/{document_id}/edit")
    assert response.status_code == 200
    assert "文档不存在" in response.text

    post_response = client.post(
        f"/web/documents/{document_id}/edit",
        data={
            "title": "Weekly AI coding tools update",
            "url": "https://example.com/doc",
            "language": "en",
            "published_at": "2026-04-27T12:00:00+00:00",
            "content_text": "Original article text.",
        },
    )
    assert post_response.status_code == 200
    assert "文档不存在" in post_response.text


def test_update_document_basic_fields_rejects_invalid_document_id(monkeypatch) -> None:
    service = WebMvpService()
    called = {"parse": 0}

    def _parse_datetime(value):
        called["parse"] += 1
        raise AssertionError("published_at parser should not run for invalid document_id")

    monkeypatch.setattr(service, "_parse_datetime", _parse_datetime)
    monkeypatch.setattr(
        service,
        "_try_create_db_session",
        lambda: (_ for _ in ()).throw(AssertionError("session should not be requested for invalid document_id")),
    )

    error, changed = service.update_document_basic_fields(
        "not-a-uuid",
        {
            "title": "Updated title",
            "url": "https://example.com/updated",
            "language": "zh",
            "published_at": "2026-04-29T07:00:00+00:00",
            "content_text": "Updated article text.",
        },
    )

    assert error == "invalid_document_id"
    assert changed is False
    assert called["parse"] == 0


def test_update_document_basic_fields_marks_reprocess_when_content_changes(monkeypatch) -> None:
    service = WebMvpService()
    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        title="Weekly AI coding tools update",
        url="https://example.com/doc",
        language="en",
        published_at=datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc),
        content_text="Original article text.",
        status="processed",
        metadata_={"web_edit": {"needs_reprocess": False}},
    )
    document.source = Source(id=uuid.uuid4(), name="Example Source")

    class _Session:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0
            self.closed = 0

        def get(self, model, object_id):
            return document if object_id == document_id else None

        def add(self, obj):
            return None

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed += 1

    session = _Session()
    monkeypatch.setattr(service, "_try_create_db_session", lambda: session)

    error, changed = service.update_document_basic_fields(
        str(document_id),
        {
            "title": "Updated title",
            "url": "https://example.com/updated",
            "language": "zh",
            "published_at": "2026-04-29T07:00:00+00:00",
            "content_text": "Updated article text.",
        },
    )

    assert error is None
    assert changed is True
    assert document.title == "Updated title"
    assert document.url == "https://example.com/updated"
    assert document.language == "zh"
    assert document.published_at == datetime(2026, 4, 29, 7, 0, tzinfo=timezone.utc)
    assert document.content_text == "Updated article text."
    assert document.metadata_["web_edit"]["needs_reprocess"] is True
    assert session.commits == 1
    assert session.closed == 1


def test_get_document_edit_view_reports_reprocess_notice(monkeypatch) -> None:
    service = WebMvpService()
    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        title="Weekly AI coding tools update",
        url="https://example.com/doc",
        language="en",
        published_at=datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc),
        content_text="Updated article text.",
        status="processed",
        metadata_={"web_edit": {"needs_reprocess": True}},
    )
    document.source = Source(id=uuid.uuid4(), name="Example Source")

    class _Session:
        def __init__(self):
            self.closed = 0

        def scalar(self, stmt):
            return document

        def close(self):
            self.closed += 1

    session = _Session()
    monkeypatch.setattr(service, "_try_create_db_session", lambda: session)

    view, error = service.get_document_edit_view(str(document_id))

    assert error is None
    assert view is not None
    assert view["needs_reprocess"] is True
    assert session.closed == 1


def test_document_list_can_show_archived_documents(monkeypatch) -> None:
    document_id = str(uuid.uuid4())
    captured = {"show_archived": None}

    def _list_document_views(*, query="", source_id="", show_archived=False):
        captured["show_archived"] = show_archived
        if show_archived:
            return ([_detail_payload(document_id, archived=True)], None)
        return ([], None)

    monkeypatch.setattr(web_routes.service, "list_document_views", _list_document_views)
    monkeypatch.setattr(web_routes.service, "list_sources", lambda: ([], None))

    client = TestClient(create_app())
    default_response = client.get("/web/documents")
    archived_response = client.get("/web/documents?show_archived=1&lang=en")

    assert default_response.status_code == 200
    assert "Weekly AI coding tools update" not in default_response.text
    assert captured["show_archived"] is True
    assert archived_response.status_code == 200
    assert "Show archived documents" in archived_response.text
    assert "Archived documents included" in archived_response.text
    assert "Weekly AI coding tools update" in archived_response.text


def test_archive_and_restore_update_metadata_without_delete(monkeypatch) -> None:
    service = WebMvpService()
    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        title="Weekly AI coding tools update",
        url="https://example.com/doc",
        language="en",
        published_at=datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc),
        content_text="Original article text.",
        status="processed",
        metadata_={"web_edit": {"needs_reprocess": False}},
    )
    document.source = Source(id=uuid.uuid4(), name="Example Source")
    deleted = {"called": False}

    class _Session:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0
            self.closed = 0

        def get(self, model, object_id):
            return document if object_id == document_id else None

        def add(self, obj):
            return None

        def delete(self, obj):
            deleted["called"] = True
            raise AssertionError("archive/restore should not hard delete documents")

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed += 1

    session = _Session()
    monkeypatch.setattr(service, "_try_create_db_session", lambda: session)

    archive_error = service.archive_document(str(document_id))
    assert archive_error is None
    assert document.metadata_["web_management"]["archived"] is True
    assert document.metadata_["web_management"]["archived_at"]
    assert document.status == "processed"

    restore_error = service.restore_document(str(document_id))
    assert restore_error is None
    assert document.metadata_["web_management"]["archived"] is False
    assert document.metadata_["web_management"]["archived_at"] is None
    assert document.status == "processed"
    assert deleted["called"] is False
    assert session.commits == 2
    assert session.closed == 2


def test_archive_submit_rejects_invalid_document_id_without_500(monkeypatch) -> None:
    monkeypatch.setattr(web_routes.service, "archive_document", lambda *args, **kwargs: "invalid_document_id")
    monkeypatch.setattr(
        web_routes.service,
        "get_document_view",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("detail lookup should not run for invalid archive id")),
    )

    client = TestClient(create_app())
    response = client.post("/web/documents/not-a-uuid/archive")

    assert response.status_code == 200
    assert "invalid" in response.text.lower() or "鏃犳晥" in response.text


def test_archive_submit_handles_database_unavailable_without_500(monkeypatch) -> None:
    monkeypatch.setattr(web_routes.service, "archive_document", lambda *args, **kwargs: "database_unavailable")
    monkeypatch.setattr(
        web_routes.service,
        "get_document_view",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("detail lookup should not run when db is unavailable")),
    )

    client = TestClient(create_app())
    response = client.post(f"/web/documents/{uuid.uuid4()}/archive")

    assert response.status_code == 200
    assert "database" in response.text.lower() or "鏁版嵁搴" in response.text


def test_restore_submit_rejects_invalid_document_id_without_500(monkeypatch) -> None:
    monkeypatch.setattr(web_routes.service, "restore_document", lambda *args, **kwargs: "invalid_document_id")
    monkeypatch.setattr(
        web_routes.service,
        "get_document_view",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("detail lookup should not run for invalid restore id")),
    )

    client = TestClient(create_app())
    response = client.post("/web/documents/not-a-uuid/restore")

    assert response.status_code == 200
    assert "invalid" in response.text.lower() or "鏃犳晥" in response.text


def test_restore_submit_handles_database_unavailable_without_500(monkeypatch) -> None:
    monkeypatch.setattr(web_routes.service, "restore_document", lambda *args, **kwargs: "database_unavailable")
    monkeypatch.setattr(
        web_routes.service,
        "get_document_view",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("detail lookup should not run when db is unavailable")),
    )

    client = TestClient(create_app())
    response = client.post(f"/web/documents/{uuid.uuid4()}/restore")

    assert response.status_code == 200
    assert "database" in response.text.lower() or "鏁版嵁搴" in response.text


def test_archive_and_restore_submit_toggle_detail_state(monkeypatch) -> None:
    document_id = str(uuid.uuid4())
    state = {"archived": False}

    def _get_document_view(requested_id: str):
        return (
            {
                "id": requested_id,
                "title": "Weekly AI coding tools update",
                "source_name": "Example Source",
                "url": "https://example.com/doc",
                "status": "processed",
                "language": "en",
                "published_at": "2026-04-27 12:00:00+00:00",
                "summary_en": "",
                "summary_zh": "",
                "key_points": [],
                "entities": [],
                "topics": [],
                "content_preview": "Original preview text.",
                "needs_reprocess": False,
                "archived": state["archived"],
                "archived_at": "2026-04-30T10:00:00+00:00" if state["archived"] else None,
            },
            None,
        )

    def _archive_document(requested_id: str):
        state["archived"] = True
        return None

    def _restore_document(requested_id: str):
        state["archived"] = False
        return None

    monkeypatch.setattr(web_routes.service, "get_document_view", _get_document_view)
    monkeypatch.setattr(web_routes.service, "archive_document", _archive_document)
    monkeypatch.setattr(web_routes.service, "restore_document", _restore_document)

    client = TestClient(create_app())

    archive_response = client.post(f"/web/documents/{document_id}/archive", follow_redirects=False)
    assert archive_response.status_code == 303
    assert archive_response.headers["location"].startswith(f"/web/documents/{document_id}")

    archived_detail = client.get(f"/web/documents/{document_id}?lang=en")
    assert archived_detail.status_code == 200
    assert "Archived" in archived_detail.text
    assert "Restore document" in archived_detail.text

    restore_response = client.post(f"/web/documents/{document_id}/restore", follow_redirects=False)
    assert restore_response.status_code == 303
    assert restore_response.headers["location"].startswith(f"/web/documents/{document_id}")

    restored_detail = client.get(f"/web/documents/{document_id}?lang=en")
    assert restored_detail.status_code == 200
    assert "Archive document" in restored_detail.text
    assert "Restore document" not in restored_detail.text


def test_list_document_views_hides_archived_documents_by_default(monkeypatch) -> None:
    service = WebMvpService()
    active_document_id = uuid.uuid4()
    archived_document_id = uuid.uuid4()
    active_document = Document(
        id=active_document_id,
        title="Active article",
        url="https://example.com/active",
        language="en",
        published_at=datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc),
        content_text="Active content.",
        status="processed",
        metadata_={"web_management": {"archived": False, "archived_at": None}},
    )
    archived_document = Document(
        id=archived_document_id,
        title="Archived article",
        url="https://example.com/archive",
        language="en",
        published_at=datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc),
        content_text="Archived content.",
        status="processed",
        metadata_={"web_management": {"archived": True, "archived_at": "2026-04-30T10:00:00+00:00"}},
    )
    active_document.source = Source(id=uuid.uuid4(), name="Example Source")
    archived_document.source = Source(id=uuid.uuid4(), name="Example Source")

    class _Session:
        def __init__(self):
            self.closed = False
            self.calls = 0

        def scalars(self, stmt):
            if self.calls == 0:
                self.calls += 1
                return [active_document, archived_document]
            self.calls += 1
            return []

        def close(self):
            self.closed = True

    sessions = [_Session(), _Session()]
    monkeypatch.setattr(service, "_try_create_db_session", lambda: sessions.pop(0))

    class _FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            return auto_value

    monkeypatch.setattr("src.web.service.DatabaseReviewService", _FakeDatabaseReviewService)

    views_default, error_default = service.list_document_views()
    views_archived, error_archived = service.list_document_views(show_archived=True)

    assert error_default is None
    assert error_archived is None
    assert [view["title"] for view in views_default] == ["Active article"]
    assert [view["title"] for view in views_archived] == ["Active article", "Archived article"]
    assert views_archived[1]["archived"] is True
