"""日报接口

  - GET /api/v1/briefs/latest — 获取最新日报
  - POST /api/v1/briefs/generate — 生成日报

对应 TC-16（日报模板卡）。
当前为占位实现。
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends

from src.api.auth import require_api_key, check_quota
from src.api.schemas import (
    BriefGenerateRequest,
    BriefResponse,
    BilingualText,
    MetaInfo,
)

router = APIRouter()


@router.get("/briefs/latest", response_model=BriefResponse, summary="获取最新日报")
async def get_latest_brief(
    api_key: str = Depends(require_api_key),
    _quota: None = Depends(check_quota),
) -> BriefResponse:
    """获取最新日报

    当前为占位实现。
    后续接入 daily_briefing 模块后填充实际逻辑。
    """
    return BriefResponse(
        date=date.today().isoformat(),
        summary=BilingualText(
            zh="日报功能暂未实现",
            en="Daily brief feature is not yet implemented",
        ),
        opportunities=[],
        risks=[],
        uncertainties=[],
        watchlist_updates=[],
        meta=MetaInfo(brief_type="scheduled"),
    )


@router.post("/briefs/generate", response_model=BriefResponse, summary="生成日报")
async def generate_brief(
    request: BriefGenerateRequest,
    api_key: str = Depends(require_api_key),
    _quota: None = Depends(check_quota),
) -> BriefResponse:
    """按指定时间点生成一份固定或按需简报

    当前为占位实现。
    后续接入 daily_briefing 模块后填充实际逻辑。
    """
    brief_type = "on_demand" if request.as_of else "scheduled"
    return BriefResponse(
        date=date.today().isoformat(),
        summary=BilingualText(
            zh="日报生成功能暂未实现",
            en="Daily brief generation is not yet implemented",
        ),
        opportunities=[],
        risks=[],
        uncertainties=[],
        watchlist_updates=[],
        meta=MetaInfo(brief_type=brief_type),
    )
