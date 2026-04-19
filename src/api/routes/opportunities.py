"""GET /api/v1/opportunities — 产品机会接口

对应 TC-14（产品机会评分卡）和 TC-15（机会输出模板卡）。
当前为占位实现。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from src.api.auth import require_api_key, check_quota
from src.api.schemas import OpportunityListResponse, MetaInfo

router = APIRouter()


@router.get("/opportunities", response_model=OpportunityListResponse, summary="获取产品机会")
async def get_opportunities(
    min_score: float | None = Query(None, description="最低总分过滤"),
    topic: str | None = Query(None, description="主题过滤"),
    limit: int = Query(10, ge=1, le=100, description="返回条数限制"),
    uncertainty: bool | None = Query(None, description="是否仅含不确定性项"),
    api_key: str = Depends(require_api_key),
    _quota: None = Depends(check_quota),
) -> OpportunityListResponse:
    """获取产品机会判断结果

    当前为占位实现。
    后续接入 opportunity_scoring 模块后填充实际逻辑。
    """
    return OpportunityListResponse(
        items=[],
        meta=MetaInfo(result_count=0),
    )
