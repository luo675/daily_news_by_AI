"""POST /api/v1/search — 检索接口

对应 TC-17（检索接口卡）。
当前为占位实现，返回空结果结构。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.auth import require_api_key, check_quota
from src.api.schemas import SearchRequest, UnifiedResponse, BilingualText, MetaInfo

router = APIRouter()


@router.post("/search", response_model=UnifiedResponse, summary="搜索知识库")
async def search(
    request: SearchRequest,
    api_key: str = Depends(require_api_key),
    _quota: None = Depends(check_quota),
) -> UnifiedResponse:
    """按 query、topic、时间范围搜索知识结果

    当前为占位实现，返回空结果结构。
    后续接入检索模块后填充实际逻辑。
    """
    return UnifiedResponse(
        summary=BilingualText(
            zh=f"搜索 '{request.query}' 的结果暂未实现",
            en=f"Search results for '{request.query}' are not yet implemented",
        ),
        evidence=[],
        opportunities=[],
        risks=[],
        uncertainties=[],
        related_topics=request.topics or [],
        watchlist_updates=[],
        meta=MetaInfo(result_count=0),
    )
