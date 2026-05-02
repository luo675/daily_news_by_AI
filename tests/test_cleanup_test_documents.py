from __future__ import annotations

import importlib.util
import io
import sys
import uuid
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from src.domain.models import Document


def _load_cleanup_script():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "cleanup_test_documents.py"
    spec = importlib.util.spec_from_file_location("cleanup_test_documents", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cleanup_script = _load_cleanup_script()


def _build_document(*, title: str, url: str) -> Document:
    return Document(
        id=uuid.uuid4(),
        title=title,
        url=url,
        created_at=datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc),
    )


def test_match_reasons_only_targets_obvious_test_documents() -> None:
    example_doc = _build_document(title="Verification run", url="https://example.com/run")
    localhost_doc = _build_document(title="Local example", url="http://127.0.0.1:8000/doc")
    localhost_only_doc = _build_document(title="Local host note", url="http://localhost:8000/doc")
    run_id_doc = _build_document(title="Batch tx smoke", url="https://news.example/run?run_id=abc123")
    persist_doc = _build_document(title="Persist test example", url="https://news.example/article")
    title_doc = _build_document(title="Schema tightening notes", url="https://news.example/article")
    real_doc = _build_document(title="Something Big Is Happening", url="https://news.example/article")

    assert cleanup_script._match_reasons(example_doc, include_localhost=True) == (
        "url contains example.com",
        "title contains verification",
    )
    assert cleanup_script._match_reasons(localhost_doc, include_localhost=True) == (
        "url contains 127.0.0.1",
    )
    assert cleanup_script._match_reasons(localhost_only_doc, include_localhost=True) == (
        "url contains localhost",
    )
    assert cleanup_script._match_reasons(localhost_only_doc, include_localhost=False) == ()
    assert cleanup_script._match_reasons(run_id_doc, include_localhost=True) == (
        "url contains run_id=",
        "title contains Batch tx",
    )
    assert cleanup_script._match_reasons(persist_doc, include_localhost=True) == ("title contains persist test",)
    assert cleanup_script._match_reasons(title_doc, include_localhost=True) == ("title contains Schema tightening",)
    assert cleanup_script._match_reasons(real_doc, include_localhost=True) == ()


def test_print_report_marks_localhost_and_summary() -> None:
    candidate = cleanup_script.CleanupCandidate(
        document=_build_document(title="Batch tx smoke", url="http://localhost/doc"),
        matched_reasons=("title contains Batch tx", "url contains localhost"),
        residual_opportunity_assessments=2,
        residual_opportunity_evidence=3,
    )
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        cleanup_script.print_report([candidate], apply_mode=False, include_localhost=True)
    output = buffer.getvalue()

    assert "Mode: dry-run" in output
    assert "localhost URLs are included in matching" in output
    assert "matched_reason=title contains Batch tx; url contains localhost" in output
    assert "possible_residual_opportunity_assessments=2" in output


class _FakeSession:
    def __init__(self) -> None:
        self.deleted = []
        self.commit_calls = 0
        self.rollback_calls = 0

    def delete(self, obj) -> None:
        self.deleted.append(obj)

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1

    def close(self) -> None:
        return None


def test_delete_candidates_deletes_documents_and_commits() -> None:
    session = _FakeSession()
    candidate_one = cleanup_script.CleanupCandidate(
        document=_build_document(title="Verification note", url="https://example.com/a"),
        matched_reasons=("url contains example.com",),
        residual_opportunity_assessments=0,
        residual_opportunity_evidence=0,
    )
    candidate_two = cleanup_script.CleanupCandidate(
        document=_build_document(title="Schema tightening", url="https://example.com/b"),
        matched_reasons=("url contains example.com",),
        residual_opportunity_assessments=0,
        residual_opportunity_evidence=0,
    )

    deleted = cleanup_script.delete_candidates(session, [candidate_one, candidate_two])

    assert deleted == 2
    assert session.deleted == [candidate_one.document, candidate_two.document]
    assert session.commit_calls == 1
    assert session.rollback_calls == 0


def test_main_dry_run_prints_summary_without_deleting(monkeypatch) -> None:
    candidate = cleanup_script.CleanupCandidate(
        document=_build_document(title="Verification run", url="https://example.com/run"),
        matched_reasons=("url contains example.com", "title contains verification"),
        residual_opportunity_assessments=0,
        residual_opportunity_evidence=0,
    )
    fake_session = _FakeSession()

    monkeypatch.setattr(cleanup_script, "collect_candidates", lambda *args, **kwargs: [candidate])
    monkeypatch.setattr(cleanup_script, "delete_candidates", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("delete should not run in dry-run")))
    monkeypatch.setattr(cleanup_script, "get_session_factory", lambda: lambda: fake_session)
    monkeypatch.setattr(sys, "argv", ["cleanup_test_documents.py"])

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = cleanup_script.main()

    output = buffer.getvalue()
    assert exit_code == 0
    assert "Mode: dry-run" in output
    assert "Summary: matched=1 deleted=0 skipped=1" in output
    assert fake_session.deleted == []


def test_main_apply_deletes_matching_documents(monkeypatch) -> None:
    candidate = cleanup_script.CleanupCandidate(
        document=_build_document(title="Persist test batch", url="https://example.com/run"),
        matched_reasons=("url contains example.com", "title contains persist test"),
        residual_opportunity_assessments=0,
        residual_opportunity_evidence=0,
    )
    fake_session = _FakeSession()
    deleted_calls = {"count": 0}

    monkeypatch.setattr(cleanup_script, "collect_candidates", lambda *args, **kwargs: [candidate])

    def _delete_candidates(session, candidates):
        deleted_calls["count"] += 1
        assert session is fake_session
        assert candidates == [candidate]
        return 1

    monkeypatch.setattr(cleanup_script, "delete_candidates", _delete_candidates)
    monkeypatch.setattr(cleanup_script, "get_session_factory", lambda: lambda: fake_session)
    monkeypatch.setattr(sys, "argv", ["cleanup_test_documents.py", "--apply"])

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = cleanup_script.main()

    output = buffer.getvalue()
    assert exit_code == 0
    assert "Mode: apply" in output
    assert "Summary: matched=1 deleted=1 skipped=0" in output
    assert deleted_calls["count"] == 1
