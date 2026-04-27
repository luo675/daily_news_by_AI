"""Verify the minimal batch entrypoint for application-layer document processing."""

from __future__ import annotations

import io
import json
import shutil
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from src.config import DatabaseConfig, create_sync_engine


SCRIPT_PATH = ROOT / "scripts" / "run_application_batch.py"
SAMPLE_INPUT_PATH = ROOT / "scripts" / "sample_application_batch_input.json"


def assert_pass(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"  [PASS] {message}")


def build_document(title: str, url: str, content_text: str) -> dict[str, str]:
    return {
        "title": title,
        "source_type": "blog",
        "url": url,
        "author": "Example Author",
        "language": "en",
        "content_text": content_text,
    }


def run_batch(input_path: Path, *args: str) -> tuple[int, dict[str, object]]:
    return run_batch_with_env(input_path, None, *args)


def run_batch_with_env(
    input_path: Path,
    env_overrides: dict[str, str] | None,
    *args: str,
) -> tuple[int, dict[str, object]]:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(input_path), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"Batch script must output valid JSON. stdout={completed.stdout!r}, stderr={completed.stderr!r}"
        ) from exc
    return completed.returncode, payload


def database_is_available() -> bool:
    try:
        engine = create_sync_engine(DatabaseConfig())
        with engine.connect():
            pass
        engine.dispose()
        return True
    except Exception as exc:
        print(f"  [SKIP] persist=true verification skipped: {type(exc).__name__}: {exc}")
        return False


def test_single_document_process_only(tmpdir: Path) -> None:
    input_path = tmpdir / "single.json"
    input_path.write_text(
        json.dumps(
            build_document(
                title="Single batch entry test",
                url=f"https://example.com/single-batch-entry?run_id={uuid4().hex}",
                content_text=(
                    "OpenAI and Anthropic appear in a single document about developer tooling "
                    "and agent workflows."
                ),
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    returncode, payload = run_batch(input_path, "--no-persist")
    assert_pass(returncode == 0, "single-document persist=false exits successfully")
    assert_pass(payload["total"] == 1, "single-document input is accepted")
    assert_pass(payload["succeeded"] == 1 and payload["failed"] == 0, "single-document result succeeds")
    item = payload["items"][0]
    assert_pass(item["success"] is True, "single-document item reports success")
    assert_pass(item["persisted"] is None, "single-document persist=false keeps persisted as null")
    assert_pass(isinstance(item["summary_info"]["daily_brief_generated"], bool), "summary_info uses bool fields")


def test_multi_document_process_only() -> None:
    returncode, payload = run_batch(SAMPLE_INPUT_PATH, "--no-persist")
    assert_pass(returncode == 0, "multi-document persist=false exits successfully")
    assert_pass(payload["total"] == 2, "sample multi-document input is accepted")
    assert_pass(payload["succeeded"] == 2 and payload["failed"] == 0, "multi-document process-only run succeeds")
    assert_pass(all(item["persisted"] is None for item in payload["items"]), "persist=false returns null persisted")


def test_invalid_item_does_not_break_batch(tmpdir: Path) -> None:
    input_path = tmpdir / "partial_failure.json"
    payload = [
        build_document(
            title="Valid batch item one",
            url=f"https://example.com/valid-batch-item-one?run_id={uuid4().hex}",
            content_text="This valid document should succeed before the invalid item.",
        ),
        {
            "title": "Invalid batch item missing content",
            "source_type": "blog",
            "url": f"https://example.com/invalid-batch-item?run_id={uuid4().hex}",
            "author": "Example Author",
            "language": "en",
        },
        build_document(
            title="Valid batch item two",
            url=f"https://example.com/valid-batch-item-two?run_id={uuid4().hex}",
            content_text="This valid document should still succeed after the invalid item.",
        ),
    ]
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    returncode, result = run_batch(input_path, "--no-persist")
    assert_pass(returncode == 0, "batch with one invalid item still exits successfully")
    assert_pass(result["total"] == 3, "batch with one invalid item still reports total count")
    assert_pass(result["succeeded"] == 2 and result["failed"] == 1, "invalid item is isolated from other items")
    assert_pass(result["items"][1]["success"] is False, "invalid item is reported as failed")
    assert_pass(bool(result["items"][1]["error"]), "invalid item includes an error message")
    assert_pass(result["items"][2]["success"] is True, "later valid item still succeeds")


def test_database_failure_returns_structured_json_and_nonzero(tmpdir: Path) -> None:
    input_path = tmpdir / "db_failure.json"
    payload = [
        build_document(
            title="Persist failure item one",
            url=f"https://example.com/persist-failure-item-one?run_id={uuid4().hex}",
            content_text="This document forces a database write attempt that should fail on flush or commit.",
        ),
        build_document(
            title="Persist failure item two",
            url=f"https://example.com/persist-failure-item-two?run_id={uuid4().hex}",
            content_text="This second document should also report a structured failure under the same broken DB config.",
        ),
    ]
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    returncode, result = run_batch_with_env(
        input_path,
        {"DB_HOST": "invalid-db-host-for-batch-verification"},
        "--fail-on-item-error",
    )
    assert_pass(returncode != 0, "DB write failure returns a non-zero exit code with fail-on-item-error")
    assert_pass(result["persist"] is True, "DB failure path uses default persist=true")
    assert_pass(result["total"] == 2, "DB failure path preserves total count")
    assert_pass(result["succeeded"] == 0 and result["failed"] == 2, "DB failure path marks all items as failed")
    assert_pass(len(result["items"]) == 2, "DB failure path still returns structured item results")
    assert_pass(all(item["success"] is False for item in result["items"]), "DB failure path reports failed items")
    assert_pass(all(bool(item["error"]) for item in result["items"]), "DB failure path includes item error messages")


def test_default_persist_with_daily_brief(tmpdir: Path) -> None:
    if not database_is_available():
        return

    input_path = tmpdir / "persist_default_daily_brief.json"
    payload = [
        build_document(
            title="Persist batch entry one",
            url=f"https://example.com/persist-batch-entry-one?run_id={uuid4().hex}",
            content_text="OpenAI appears in this persist-mode document about startup tooling.",
        ),
        build_document(
            title="Persist batch entry two",
            url=f"https://example.com/persist-batch-entry-two?run_id={uuid4().hex}",
            content_text="Developers want better observability and deployment controls for agent workflows.",
        ),
    ]
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    returncode, result = run_batch(input_path)
    assert_pass(returncode == 0, "default persist=true exits successfully when DB is available")
    assert_pass(result["persist"] is True, "default run keeps persist=true")
    assert_pass(result["include_daily_brief"] is True, "default run keeps daily brief enabled")
    assert_pass(result["total"] == 2, "default persist=true accepts two documents")
    assert_pass(result["succeeded"] == 2 and result["failed"] == 0, "default persist=true succeeds")
    assert_pass(all(item["persisted"] is not None for item in result["items"]), "default persist=true returns persisted summaries")
    assert_pass(
        all(item["summary_info"]["daily_brief_generated"] is True for item in result["items"]),
        "default persist=true run reports generated daily briefs",
    )


def main() -> None:
    print("=" * 60)
    print("Application batch entry verification")
    print("=" * 60)
    tmpdir = ROOT / "scripts" / ".tmp_verify_application_batch"
    if tmpdir.exists():
        shutil.rmtree(tmpdir)
    tmpdir.mkdir(parents=True, exist_ok=True)
    try:
        test_single_document_process_only(tmpdir)
        test_multi_document_process_only()
        test_invalid_item_does_not_break_batch(tmpdir)
        test_database_failure_returns_structured_json_and_nonzero(tmpdir)
        test_default_persist_with_daily_brief(tmpdir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    print("=" * 60)
    print("Application batch entry verification passed")
    print("=" * 60)


if __name__ == "__main__":
    main()
