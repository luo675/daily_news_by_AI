"""PATCH /api/v1/reviews/{target_type}/{target_id} — 人工修订接口

对应 TC-20（人工修订规则卡）。
已接入 admin_review 模块，使用数据库存储。
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from src.admin.review_schemas import (
    ReviewEditCreate,
    ReviewEditBatch,
    ReviewEditResponse,
    ReviewHistoryResponse,
    OverrideStatus,
)
from src.admin.review_service import ReviewService
from src.admin.review_service_db import DatabaseReviewService, InvalidReviewError
from src.api.auth import require_api_key, check_quota
from src.api.deps import try_create_db_session

router = APIRouter()
_fallback_review_service = ReviewService()


def get_review_service() -> Generator[ReviewService | DatabaseReviewService, None, None]:
    """优先使用数据库服务，不可用时降级到内存服务。"""
    db = try_create_db_session()
    if db is None:
        yield _fallback_review_service
        return

    try:
        db.execute(text("SELECT 1"))
        yield DatabaseReviewService(db)
    except Exception:
        yield _fallback_review_service
    finally:
        db.close()


@router.patch(
    "/reviews/{target_type}/{target_id}",
    response_model=ReviewEditResponse,
    summary="人工修订（单字段）",
)
async def patch_review(
    target_type: str,
    target_id: str,
    request: ReviewEditCreate,
    api_key: str = Depends(require_api_key),
    _quota: None = Depends(check_quota),
    service: ReviewService | DatabaseReviewService = Depends(get_review_service),
) -> ReviewEditResponse:
    """修订摘要、标签、评分、结论等

    target_type: summary/tags/opportunity_score/conclusion/priority/topic/uncertainty/risk
    target_id: 修订目标 ID

    人工修订优先级高于自动结果，所有改动保留审计记录。
    """
    try:
        target_uuid = uuid.UUID(target_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的 target_id: {target_id}")

    try:
        edit = service.create_edit(
            target_type=target_type,
            target_id=target_uuid,
            create=request,
        )
    except InvalidReviewError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return edit


@router.post(
    "/reviews/{target_type}/{target_id}/batch",
    response_model=List[ReviewEditResponse],
    summary="批量修订",
)
async def batch_review(
    target_type: str,
    target_id: str,
    request: ReviewEditBatch,
    api_key: str = Depends(require_api_key),
    _quota: None = Depends(check_quota),
    service: ReviewService | DatabaseReviewService = Depends(get_review_service),
) -> List[ReviewEditResponse]:
    """批量修订同一目标的多个字段"""
    try:
        target_uuid = uuid.UUID(target_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的 target_id: {target_id}")

    try:
        edits = service.create_batch(
            target_type=target_type,
            target_id=target_uuid,
            batch=request.edits,
            reason=request.reason,
        )
    except InvalidReviewError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return edits


@router.get(
    "/reviews/{target_type}/{target_id}",
    response_model=ReviewHistoryResponse,
    summary="获取修订历史",
)
async def get_review_history(
    target_type: str,
    target_id: str,
    field_name: str | None = None,
    api_key: str = Depends(require_api_key),
    _quota: None = Depends(check_quota),
    service: ReviewService | DatabaseReviewService = Depends(get_review_service),
) -> ReviewHistoryResponse:
    """获取指定目标的修订历史

    可选按 field_name 过滤。
    """
    try:
        target_uuid = uuid.UUID(target_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的 target_id: {target_id}")

    return service.get_history(target_type, target_uuid, field_name)


@router.get(
    "/reviews/{target_type}/{target_id}/override/{field_name}",
    response_model=OverrideStatus,
    summary="获取字段覆盖状态",
)
async def get_override_status(
    target_type: str,
    target_id: str,
    field_name: str,
    api_key: str = Depends(require_api_key),
    _quota: None = Depends(check_quota),
    service: ReviewService | DatabaseReviewService = Depends(get_review_service),
) -> OverrideStatus:
    """获取字段的覆盖状态（manual vs auto）"""
    try:
        target_uuid = uuid.UUID(target_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的 target_id: {target_id}")

    return service.get_override_status(target_type, target_uuid, field_name)


@router.post(
    "/reviews/{edit_id}/revert",
    response_model=ReviewEditResponse,
    summary="撤销修订",
)
async def revert_review(
    edit_id: str,
    reviewer: str = "owner",
    api_key: str = Depends(require_api_key),
    _quota: None = Depends(check_quota),
    service: ReviewService | DatabaseReviewService = Depends(get_review_service),
) -> ReviewEditResponse:
    """撤销一条修订记录，恢复为旧值"""
    try:
        edit_uuid = uuid.UUID(edit_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的 edit_id: {edit_id}")

    revert_edit = service.revert_edit(edit_uuid, reviewer)
    if revert_edit is None:
        raise HTTPException(status_code=404, detail=f"修订记录不存在: {edit_id}")

    return revert_edit
