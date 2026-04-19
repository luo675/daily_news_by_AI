"""关注列表接口

  - GET /api/v1/watchlist — 获取关注列表
  - POST /api/v1/watchlist — 新增关注项

对应 TC-05（Watchlist 规则卡）。
当前为占位实现，后续接入 watchlist 模块。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.auth import require_api_key, check_quota
from src.api.schemas import WatchlistCreateRequest, WatchlistResponse, MetaInfo
from src.watchlist.schemas import WatchlistItemCreate
from src.watchlist.service import DuplicateItemError, WatchlistService

router = APIRouter()
_watchlist_service = WatchlistService()


def _serialize_watchlist() -> WatchlistResponse:
    items = [item.model_dump(mode="json") for item in _watchlist_service.list_all()]
    grouped_by_type = {
        group.group_key: [item.model_dump(mode="json") for item in group.items]
        for group in _watchlist_service.group_by_type()
    }
    grouped_by_priority = {
        group.group_key: [item.model_dump(mode="json") for item in group.items]
        for group in _watchlist_service.group_by_priority()
    }
    return WatchlistResponse(
        items=items,
        grouped_by_type=grouped_by_type,
        grouped_by_priority=grouped_by_priority,
        meta=MetaInfo(result_count=len(items)),
    )


@router.get("/watchlist", response_model=WatchlistResponse, summary="获取关注列表")
async def get_watchlist(
    api_key: str = Depends(require_api_key),
    _quota: None = Depends(check_quota),
) -> WatchlistResponse:
    """获取当前关注列表。"""
    return _serialize_watchlist()


@router.post("/watchlist", response_model=WatchlistResponse, summary="新增关注项")
async def create_watchlist_item(
    request: WatchlistCreateRequest,
    api_key: str = Depends(require_api_key),
    _quota: None = Depends(check_quota),
) -> WatchlistResponse:
    """新增关注项。"""
    try:
        _watchlist_service.add(
            WatchlistItemCreate(
                item_type=request.item_type,
                item_value=request.item_value,
                priority_level=request.priority_level,
                group_name=request.group_name,
                notes=request.notes,
            )
        )
    except DuplicateItemError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return _serialize_watchlist()
