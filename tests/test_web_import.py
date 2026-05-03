from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.routes import web as web_routes
from src.web.service import WebMvpService


def test_import_page_is_linked_in_main_nav(monkeypatch) -> None:
    client = TestClient(create_app())

    response = client.get("/web/import")

    assert response.status_code == 200
    assert "/web/import" in response.text
    assert "文档手动导入" in response.text


def test_manual_import_route_accepts_pasted_text(monkeypatch) -> None:
    captured: dict[str, str | None] = {}
    document_id = str(uuid4())

    def _import_manual_document(*, title: str, content_text: str, filename: str | None = None, content_type: str | None = None):
        captured["title"] = title
        captured["content_text"] = content_text
        captured["filename"] = filename
        captured["content_type"] = content_type
        return document_id, None

    monkeypatch.setattr(web_routes.service, "import_manual_document", _import_manual_document)

    client = TestClient(create_app())
    response = client.post(
        "/web/import",
        data={
            "title": "",
            "content_text": "# Weekly AI coding update\n\nBody text.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/web/documents/{document_id}"
    assert captured["title"] == "Weekly AI coding update"
    assert captured["content_text"] == "# Weekly AI coding update\n\nBody text."
    assert captured["filename"] is None


def test_manual_import_route_accepts_markdown_upload(monkeypatch) -> None:
    captured: dict[str, str | None] = {}
    document_id = str(uuid4())

    def _import_manual_document(*, title: str, content_text: str, filename: str | None = None, content_type: str | None = None):
        captured["title"] = title
        captured["content_text"] = content_text
        captured["filename"] = filename
        captured["content_type"] = content_type
        return document_id, None

    monkeypatch.setattr(web_routes.service, "import_manual_document", _import_manual_document)

    client = TestClient(create_app())
    response = client.post(
        "/web/import",
        data={"title": "", "content_text": ""},
        files={"content_file": ("sample-note.md", b"# Markdown title\n\nMarkdown body.", "text/markdown")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/web/documents/{document_id}"
    assert captured["title"] == "sample-note"
    assert captured["content_text"] == "# Markdown title\n\nMarkdown body."
    assert captured["filename"] == "sample-note.md"
    assert captured["content_type"] == "text/markdown"


def test_manual_import_route_rejects_blank_content_and_invalid_extension(monkeypatch) -> None:
    monkeypatch.setattr(web_routes.service, "import_manual_document", lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not be called")))
    client = TestClient(create_app())

    blank_response = client.post(
        "/web/import",
        data={"title": "", "content_text": ""},
        follow_redirects=False,
    )
    ext_response = client.post(
        "/web/import",
        data={"title": "", "content_text": ""},
        files={"content_file": ("sample.pdf", b"%PDF-1.4", "application/pdf")},
        follow_redirects=False,
    )

    assert blank_response.status_code == 200
    assert "请输入正文" in blank_response.text
    assert ext_response.status_code == 200
    assert "仅支持 .md、.markdown、.txt 文件" in ext_response.text


def test_manual_import_service_reuses_existing_pipeline(monkeypatch) -> None:
    service = WebMvpService()
    doc_id = uuid4()
    counters = {"commit": 0, "rollback": 0, "closed": 0}

    class _Session:
        def commit(self) -> None:
            counters["commit"] += 1

        def rollback(self) -> None:
            counters["rollback"] += 1

        def close(self) -> None:
            counters["closed"] += 1

    session = _Session()

    captured: dict[str, object] = {}

    def _run_document_pipeline(*, document, persist, include_daily_brief, session):
        captured["document"] = document
        captured["persist"] = persist
        captured["include_daily_brief"] = include_daily_brief
        captured["session"] = session
        return SimpleNamespace(document_id=doc_id)

    monkeypatch.setattr(service, "_require_session", lambda: session)
    monkeypatch.setattr(service._orchestrator, "run_document_pipeline", _run_document_pipeline)

    document_id, error = service.import_manual_document(
        title="Manual source note",
        content_text="Manual import body",
        filename="manual-note.md",
        content_type="text/markdown",
    )

    assert error is None
    assert document_id == str(doc_id)
    assert captured["persist"] is True
    assert captured["include_daily_brief"] is False
    assert captured["session"] is session
    document = captured["document"]
    assert document.title == "Manual source note"
    assert document.source_type.value == "manual_import"
    assert document.metadata.original_format == "markdown"
    assert document.metadata.extra == {"filename": "manual-note.md"}
    assert counters["commit"] >= 1
    assert counters["closed"] == 1
