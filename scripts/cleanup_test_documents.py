"""Safely clean obvious test documents from the local PostgreSQL database.

This script is conservative by design:
- dry-run by default
- only deletes when --apply is passed
- matches only obvious test/example documents
- deletes Document rows only and relies on ORM / DB cascade for related rows
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.config import DatabaseConfig, get_session_factory
from src.domain.models import Document, OpportunityAssessment, OpportunityEvidence

URL_MATCH_RULES: tuple[tuple[str, str], ...] = (
    ("example.com", "url contains example.com"),
    ("127.0.0.1", "url contains 127.0.0.1"),
    ("run_id=", "url contains run_id="),
)

TITLE_MATCH_RULES: tuple[tuple[str, str], ...] = (
    ("verification", "title contains verification"),
    ("persist test", "title contains persist test"),
    ("batch tx", "title contains Batch tx"),
    ("schema tightening", "title contains Schema tightening"),
)


@dataclass(frozen=True)
class CleanupCandidate:
    document: Document
    matched_reasons: tuple[str, ...]
    residual_opportunity_assessments: int
    residual_opportunity_evidence: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run or delete obvious test documents from PostgreSQL.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete matching documents instead of only printing a dry-run report.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit how many matching documents are processed.",
    )
    parser.add_argument(
        "--include-localhost",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include localhost URLs in the conservative test-data match rules.",
    )
    return parser


def _normalize(value: Any) -> str:
    return str(value or "").strip()


def _match_reasons(document: Document, *, include_localhost: bool) -> tuple[str, ...]:
    reasons: list[str] = []
    url = _normalize(document.url)
    title = _normalize(document.title)
    lowered_url = url.lower()
    lowered_title = title.lower()

    for needle, reason in URL_MATCH_RULES:
        if needle in lowered_url:
            reasons.append(reason)

    if include_localhost and "localhost" in lowered_url:
        reasons.append("url contains localhost")

    for needle, reason in TITLE_MATCH_RULES:
        if needle in lowered_title:
            reasons.append(reason)

    return tuple(dict.fromkeys(reasons))


def _format_datetime(value: Any) -> str:
    if value is None:
        return "-"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _build_candidate(session: Session, document: Document, *, include_localhost: bool) -> CleanupCandidate | None:
    reasons = _match_reasons(document, include_localhost=include_localhost)
    if not reasons:
        return None

    residual_opportunity_assessments = int(
        session.scalar(
            select(func.count(func.distinct(OpportunityAssessment.id)))
            .select_from(OpportunityAssessment)
            .join(OpportunityEvidence, OpportunityEvidence.opportunity_id == OpportunityAssessment.id)
            .where(OpportunityEvidence.document_id == document.id)
        )
        or 0
    )
    residual_opportunity_evidence = int(
        session.scalar(
            select(func.count())
            .select_from(OpportunityEvidence)
            .where(OpportunityEvidence.document_id == document.id)
        )
        or 0
    )
    return CleanupCandidate(
        document=document,
        matched_reasons=reasons,
        residual_opportunity_assessments=residual_opportunity_assessments,
        residual_opportunity_evidence=residual_opportunity_evidence,
    )


def collect_candidates(
    session: Session,
    *,
    include_localhost: bool,
    limit: int | None,
) -> list[CleanupCandidate]:
    conditions = [
        Document.url.ilike("%example.com%"),
        Document.url.ilike("%127.0.0.1%"),
        Document.url.ilike("%run_id=%"),
        Document.title.ilike("%verification%"),
        Document.title.ilike("%persist test%"),
        Document.title.ilike("%Batch tx%"),
        Document.title.ilike("%Schema tightening%"),
    ]
    if include_localhost:
        conditions.append(Document.url.ilike("%localhost%"))

    stmt = (
        select(Document)
        .where(or_(*conditions))
        .order_by(Document.created_at.asc().nullslast(), Document.id.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)

    documents = list(session.scalars(stmt).unique())
    candidates: list[CleanupCandidate] = []
    for document in documents:
        candidate = _build_candidate(session, document, include_localhost=include_localhost)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def render_candidate(candidate: CleanupCandidate) -> str:
    return (
        f"- document_id={candidate.document.id} | "
        f"title={_normalize(candidate.document.title)} | "
        f"url={_normalize(candidate.document.url) or '-'} | "
        f"created_at={_format_datetime(candidate.document.created_at)} | "
        f"matched_reason={'; '.join(candidate.matched_reasons)} | "
        f"possible_residual_opportunity_assessments={candidate.residual_opportunity_assessments} | "
        f"possible_residual_opportunity_evidence={candidate.residual_opportunity_evidence}"
    )


def print_report(candidates: Iterable[CleanupCandidate], *, apply_mode: bool, include_localhost: bool) -> None:
    mode = "apply" if apply_mode else "dry-run"
    localhost_note = "included" if include_localhost else "excluded"
    print(f"Mode: {mode}")
    print(f"localhost URLs are {localhost_note} in matching")
    printed = False
    for candidate in candidates:
        printed = True
        print(render_candidate(candidate))
    if not printed:
        print("No matching documents found.")


def delete_candidates(session: Session, candidates: list[CleanupCandidate]) -> int:
    deleted = 0
    try:
        for candidate in candidates:
            session.delete(candidate.document)
            deleted += 1
        session.commit()
        return deleted
    except Exception:
        session.rollback()
        raise


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be a positive integer")

    config = DatabaseConfig()
    session_factory = get_session_factory()
    session = session_factory()
    try:
        candidates = collect_candidates(
            session,
            include_localhost=bool(args.include_localhost),
            limit=args.limit,
        )
        matched_count = len(candidates)
        print_report(candidates, apply_mode=args.apply, include_localhost=bool(args.include_localhost))

        if args.apply:
            deleted_count = delete_candidates(session, candidates)
            skipped_count = matched_count - deleted_count
        else:
            deleted_count = 0
            skipped_count = matched_count

        print(
            "Summary: "
            f"matched={matched_count} deleted={deleted_count} skipped={skipped_count}"
        )
        print(f"Database: {config.masked_sync_url}")
        return 0
    finally:
        close = getattr(session, "close", None)
        if callable(close):
            close()


if __name__ == "__main__":
    raise SystemExit(main())
