"""关注列表模块

管理用户关注的对象（人物、公司、产品、模型、主题、赛道、关键词）。
支持按对象类型和优先级分组，为检索和日报提供加权上下文。
对应 TC-04（关注对象模型）和 TC-05（Watchlist 规则）。
"""

from src.watchlist.schemas import (
    WatchlistItemCreate,
    WatchlistItemUpdate,
    WatchlistItemResponse,
    WatchlistGroup,
    ItemType,
    PriorityLevel,
    WatchlistStatus,
)
from src.watchlist.service import WatchlistService
from src.watchlist.weight import WatchlistWeightCalculator

__all__ = [
    "WatchlistItemCreate",
    "WatchlistItemUpdate",
    "WatchlistItemResponse",
    "WatchlistGroup",
    "ItemType",
    "PriorityLevel",
    "WatchlistStatus",
    "WatchlistService",
    "WatchlistWeightCalculator",
]
