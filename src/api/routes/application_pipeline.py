"""POST /api/v1/application/pipeline/run - minimal application pipeline entrypoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from src.api.auth import check_quota, require_api_key
from src.api.deps import create_db_session
from src.api.schemas import ApplicationPipelineRunRequest
from src.application.orchestrator import DocumentPipelineOrchestrator
from src.application.schemas import (
    ApplicationBatchItemResult,
    ApplicationBatchSummaryInfo,
    ApplicationPipelineResult,
)

router = APIRouter()


def rollback_session(session: Any) -> None:
    rollback = getattr(session, "rollback", None)
    if callable(rollback):
        rollback()


def build_success_response(result: ApplicationPipelineResult) -> ApplicationBatchItemResult:
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


@router.post(
    "/application/pipeline/run",
    response_model=ApplicationBatchItemResult,
    summary="Run the application pipeline for one raw document",
)
async def run_application_pipeline(
    request: ApplicationPipelineRunRequest,
    api_key: str = Depends(require_api_key),
    _quota: None = Depends(check_quota),
) -> ApplicationBatchItemResult | JSONResponse:
    del api_key
    orchestrator = DocumentPipelineOrchestrator()
    session = None

    try:
        if request.persist:
            session = create_db_session()

        result = orchestrator.run_document_pipeline(
            document=request.document,
            persist=request.persist,
            include_daily_brief=request.include_daily_brief,
            session=session,
        )
        return build_success_response(result)
    except Exception as exc:
        if request.persist and session is not None:
            rollback_session(session)
        error_response = ApplicationBatchItemResult(
            success=False,
            error=f"{type(exc).__name__}: {exc}",
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response.model_dump(mode="json"),
        )
    finally:
        if session is not None:
            session.close()
