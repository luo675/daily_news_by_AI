"""Verify the minimal single-URL import path into the application pipeline."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from src.ingestion.schemas import RawDocumentInput
from src.ingestion.url_importer import import_url_as_raw_document

DEFAULT_URL = "https://www.example.com/"


def assert_pass(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def verify_raw_document_mapping(url: str) -> None:
    document = import_url_as_raw_document(url)
    assert_pass(isinstance(document, RawDocumentInput), "URL importer returns RawDocumentInput")
    assert_pass(bool(document.title.strip()), "imported document includes a title")
    assert_pass(bool(document.content_text.strip()), "imported document includes content_text")
    assert_pass(document.url is not None and document.url.startswith("https://"), "imported document keeps a resolved URL")
    assert_pass(document.source_type.value == "blog", "single URL importer maps content as blog")


def verify_batch_script(url: str) -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_application_batch.py"), "--url", url, "--no-persist"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"run_application_batch.py --url must output valid JSON. stdout={completed.stdout!r}, stderr={completed.stderr!r}"
        ) from exc

    assert_pass(completed.returncode == 0, "batch script exits successfully for URL import")
    assert_pass(payload["total"] == 1, "URL import produces one batch item")
    assert_pass(payload["succeeded"] == 1 and payload["failed"] == 0, "URL-imported document enters the application pipeline successfully")
    assert_pass(payload["items"][0]["success"] is True, "URL-imported item reports success")
    assert_pass(payload["items"][0]["persisted"] is None, "URL import verification keeps persist=false")


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    print("=" * 60)
    print("Application URL import verification")
    print("=" * 60)
    print(f"[INFO] Test URL: {url}")
    verify_raw_document_mapping(url)
    verify_batch_script(url)
    print("=" * 60)
    print("Application URL import verification passed")
    print("=" * 60)


if __name__ == "__main__":
    main()
