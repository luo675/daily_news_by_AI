"""Verify the minimal URL-list batch import path into the application pipeline."""

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

from src.ingestion.url_importer import load_url_list

DEFAULT_URL_LIST = ROOT / "scripts" / "sample_application_url_list.txt"
DEFAULT_SEED_DIR = ROOT / "scripts" / "sample_seed_sources"


def assert_pass(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[PASS] {message}")


def verify_url_list_file(path: Path) -> list[str]:
    urls = load_url_list(path)
    assert_pass(len(urls) == 3, "sample URL list contains three URLs")
    assert_pass(urls[0].startswith("https://"), "sample URL list uses absolute URLs")
    return urls


def verify_seed_directory(path: Path) -> list[str]:
    urls = load_url_list(path)
    assert_pass(len(urls) == 3, "seed directory merges into three unique URLs")
    assert_pass(
        urls.count("https://simonwillison.net/2024/May/29/training-not-chatting/") == 1,
        "seed directory de-duplicates repeated URLs by first occurrence",
    )
    assert_pass(urls[0].startswith("https://"), "seed directory preserves absolute URLs")
    return urls


def verify_batch_script(path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_application_batch.py"), "--url-list", str(path), "--no-persist"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"run_application_batch.py --url-list must output valid JSON. stdout={completed.stdout!r}, stderr={completed.stderr!r}"
        ) from exc

    assert_pass(completed.returncode == 0, "URL-list batch script exits successfully")
    assert_pass(payload["total"] == 3, "URL-list import preserves three total items")
    assert_pass(len(payload["items"]) == 3, "URL-list import returns one item per URL")
    assert_pass(
        payload["succeeded"] + payload["failed"] == payload["total"],
        "URL-list import reports a complete succeeded/failed breakdown",
    )
    assert_pass(
        all(isinstance(item["success"], bool) for item in payload["items"]),
        "URL-list import returns explicit success flags for every item",
    )
    failed_items = [item for item in payload["items"] if not item["success"]]
    if failed_items:
        assert_pass(all(bool(item["error"]) for item in failed_items), "failed URL-list items include error messages")


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_URL_LIST
    print("=" * 60)
    print("Application URL-list import verification")
    print("=" * 60)
    print(f"[INFO] URL list file: {path}")
    verify_url_list_file(path)
    print(f"[INFO] Seed directory: {DEFAULT_SEED_DIR}")
    verify_seed_directory(DEFAULT_SEED_DIR)
    verify_batch_script(path)
    verify_batch_script(DEFAULT_SEED_DIR)
    print("=" * 60)
    print("Application URL-list import verification passed")
    print("=" * 60)


if __name__ == "__main__":
    main()
