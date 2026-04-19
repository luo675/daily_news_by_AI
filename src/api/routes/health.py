"""GET /api/v1/health — 健康检查接口

不需要鉴权（或可选鉴权），返回服务状态和配额信息。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.auth import optional_api_key, get_quota_tracker
from src.api.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, summary="健康检查")
async def health_check(
    api_key: str | None = Depends(optional_api_key),
) -> HealthResponse:
    """健康检查和配额状态查询

    无需鉴权即可访问。如果提供了有效 API 密钥，额外返回配额信息。
    """
    quota_status = None
    if api_key is not None:
        tracker = get_quota_tracker()
        quota_status = tracker.status

    return HealthResponse(
        status="ok",
        version="0.1.0",
        database="not_connected",
        quota=quota_status,
    )
