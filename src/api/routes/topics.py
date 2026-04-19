"""GET /api/v1/topics/{id} — 主题详情接口

对应 TC-12（主题抽取规范卡）。
当前为占位实现。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.auth import require_api_key, check_quota
from src.api.schemas import TopicDetailResponse, BilingualText

router = APIRouter()


@router.get("/topics/{topic_id}", response_model=TopicDetailResponse, summary="获取主题详情")
async def get_topic(
    topic_id: str,
    api_key: str = Depends(require_api_key),
    _quota: None = Depends(check_quota),
) -> TopicDetailResponse:
    """获取主题详情、相关文档、关联实体和趋势摘要

    当前为占位实现。
    后续接入主题查询模块后填充实际逻辑。
    """
    return TopicDetailResponse(
        id=topic_id,
        name_zh=None,
        name_en=None,
        description="Topic detail not yet implemented",
        related_documents=[],
        related_entities=[],
        trend_summary=BilingualText(
            zh="主题趋势暂未实现",
            en="Topic trend not yet implemented",
        ),
    )
