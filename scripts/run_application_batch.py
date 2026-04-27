"""Minimal batch entrypoint for application-layer document processing."""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from pydantic import ValidationError

from src.api.deps import create_db_session
from src.application.orchestrator import DocumentPipelineOrchestrator
from src.application.schemas import (
    ApplicationBatchItemResult,
    ApplicationBatchRunResult,
    ApplicationBatchSummaryInfo,
)
from src.ingestion.schemas import RawDocumentInput
from src.ingestion.url_importer import import_url_as_raw_document, load_url_list


def rollback_session(session: Any) -> None:
    rollback = getattr(session, "rollback", None)
    if callable(rollback):
        rollback()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run DocumentPipelineOrchestrator for one or more raw documents from JSON input."
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to a JSON file containing one object or an array of objects.",
    )
    parser.add_argument(
        "--url",
        help="Fetch one article URL and convert it into RawDocumentInput before running the pipeline.",
    )
    parser.add_argument(
        "--url-list",
        help="Path to a plain-text/JSON URL-list file, or a directory of seed files, to import one by one.",
    )
    parser.add_argument(
        "--persist",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Persist results using the existing application persistence path (default: true).",
    )
    parser.add_argument(
        "--no-daily-brief",
        action="store_true",
        help="Disable daily brief generation.",
    )
    parser.add_argument(
        "--fail-on-item-error",
        action="store_true",
        help="Return a non-zero exit code if any item fails.",
    )
    args = parser.parse_args()
    provided_sources = sum(bool(value) for value in (args.input, args.url, args.url_list))
    if provided_sources == 0:
        parser.error("Provide an input JSON file path, --url, or --url-list.")
    if provided_sources > 1:
        parser.error("Use only one of: input JSON file path, --url, or --url-list.")
    return args


def load_input_documents(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ValueError(f"Input file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON input: {exc}") from exc

    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        return payload
    raise ValueError("Input JSON must be a single object or an array of objects.")


def load_url_document(url: str) -> list[dict[str, Any]]:
    try:
        document = import_url_as_raw_document(url)
    except Exception as exc:
        raise ValueError(f"Failed to import URL as RawDocumentInput: {type(exc).__name__}: {exc}") from exc
    return [document.model_dump(mode="json")]


def build_import_error_item(url: str, error: str) -> ApplicationBatchItemResult:
    return ApplicationBatchItemResult(
        success=False,
        error=f"URL import failed for {url}: {error}",
    )


def build_item_result(
    orchestrator: DocumentPipelineOrchestrator,
    payload: dict[str, Any],
    *,
    persist: bool,
    include_daily_brief: bool,
    session: Any = None,
) -> ApplicationBatchItemResult:
    try:
        document = RawDocumentInput.model_validate(payload)
        result = orchestrator.run_document_pipeline(
            document=document,
            persist=persist,
            include_daily_brief=include_daily_brief,
            session=session,
        )
    except ValidationError as exc:
        if persist and session is not None:
            rollback_session(session)
        return ApplicationBatchItemResult(success=False, error=str(exc))
    except Exception as exc:
        if persist and session is not None:
            rollback_session(session)
        return ApplicationBatchItemResult(success=False, error=f"{type(exc).__name__}: {exc}")

    return ApplicationBatchItemResult(
        success=True,
        document_id=result.document_id,
        persisted=result.persisted,
        summary_info=ApplicationBatchSummaryInfo(
            title=result.cleaned.normalized_title,
            language=result.cleaned.raw_document.language,
            entity_count=len(result.entities),
            topic_count=len(result.topics),
            opportunity_count=len(result.opportunities),
            daily_brief_generated=result.daily_brief is not None,
        ),
    )


def main() -> int:
    args = parse_args()
    persist = args.persist
    include_daily_brief = not args.no_daily_brief
    raw_documents: list[dict[str, Any]] = []
    prebuilt_items: list[ApplicationBatchItemResult] = []
    try:
        if args.url:
            raw_documents = load_url_document(args.url)
        elif args.url_list:
            for url in load_url_list(Path(args.url_list)):
                try:
                    raw_documents.extend(load_url_document(url))
                except ValueError as exc:
                    prebuilt_items.append(build_import_error_item(url, str(exc)))
        else:
            raw_documents = load_input_documents(Path(args.input))
    except ValueError as exc:
        print(
            json.dumps(
                ApplicationBatchRunResult(
                    persist=persist,
                    include_daily_brief=include_daily_brief,
                    total=0,
                    succeeded=0,
                    failed=0,
                    error=str(exc),
                ).model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    orchestrator = DocumentPipelineOrchestrator()
    try:
        session = create_db_session() if persist else None
    except Exception as exc:
        print(
            json.dumps(
                ApplicationBatchRunResult(
                    persist=persist,
                    include_daily_brief=include_daily_brief,
                    total=0,
                    succeeded=0,
                    failed=0,
                    error=f"{type(exc).__name__}: {exc}",
                ).model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    try:
        items = list(prebuilt_items)
        for payload in raw_documents:
            items.append(
                build_item_result(
                    orchestrator,
                    payload,
                    persist=persist,
                    include_daily_brief=include_daily_brief,
                    session=session,
                )
            )
    finally:
        if session is not None:
            session.close()

    batch_result = ApplicationBatchRunResult(
        persist=persist,
        include_daily_brief=include_daily_brief,
        total=len(items),
        succeeded=sum(1 for item in items if item.success),
        failed=sum(1 for item in items if not item.success),
        items=items,
    )
    print(json.dumps(batch_result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    if args.fail_on_item_error and batch_result.failed > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
