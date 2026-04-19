"""Watchlist 权重计算

为检索重排序和日报优先级提升提供加权计算。
对应 architecture.md 中 watchlist 参与决策的场景：
  - 检索重排序
  - 日报优先级提升
  - 专题聚合
  - 机会判断增强

设计原则：
  - 第一阶段使用简单的优先级映射权重
  - 后续可扩展为基于关注时长、交互频率等的动态权重
"""

from __future__ import annotations

from src.watchlist.schemas import (
    ItemType,
    PriorityLevel,
    WatchlistItemResponse,
    WatchlistStatus,
)


# ──────────────────────────── 权重配置 ────────────────────────────

# 优先级 → 基础权重映射
PRIORITY_WEIGHTS: dict[PriorityLevel, float] = {
    PriorityLevel.HIGH: 2.0,
    PriorityLevel.MEDIUM: 1.5,
    PriorityLevel.LOW: 1.0,
}

# 对象类型 → 类型权重映射（可选，第一阶段默认 1.0）
TYPE_WEIGHTS: dict[ItemType, float] = {
    ItemType.PERSON: 1.0,
    ItemType.COMPANY: 1.0,
    ItemType.PRODUCT: 1.0,
    ItemType.MODEL: 1.0,
    ItemType.TOPIC: 1.0,
    ItemType.TRACK: 1.0,
    ItemType.KEYWORD: 1.0,
}


class WatchlistWeightCalculator:
    """Watchlist 权重计算器

    根据关注列表为文档/实体/主题计算加权分数。
    用于检索重排序和日报优先级提升。
    """

    def __init__(
        self,
        priority_weights: dict[PriorityLevel, float] | None = None,
        type_weights: dict[ItemType, float] | None = None,
    ) -> None:
        self.priority_weights = priority_weights or PRIORITY_WEIGHTS
        self.type_weights = type_weights or TYPE_WEIGHTS

    def item_weight(self, item: WatchlistItemResponse) -> float:
        """计算单个关注项的权重

        公式：priority_weight * type_weight
        仅活跃项有权重，暂停/移除项权重为 0。

        Args:
            item: 关注项

        Returns:
            权重值（>= 0）
        """
        if item.status != WatchlistStatus.ACTIVE:
            return 0.0

        pw = self.priority_weights.get(item.priority_level, 1.0)
        tw = self.type_weights.get(item.item_type, 1.0)
        return pw * tw

    def compute_boost(
        self,
        items: list[WatchlistItemResponse],
        matched_types: set[ItemType] | None = None,
        matched_values: set[str] | None = None,
    ) -> float:
        """计算一组关注项的加权提升分数

        用于检索重排序：当文档/实体匹配到关注项时，
        计算总提升分数用于排序。

        Args:
            items: 活跃关注项列表
            matched_types: 匹配的对象类型集合（可选）
            matched_values: 匹配的对象值集合（可选）

        Returns:
            总提升分数
        """
        total = 0.0
        for item in items:
            if item.status != WatchlistStatus.ACTIVE:
                continue
            # 如果提供了匹配条件，只计算匹配项的权重
            if matched_types and item.item_type not in matched_types:
                continue
            if matched_values and item.item_value not in matched_values:
                continue
            total += self.item_weight(item)
        return total

    def get_active_items_by_type(
        self, items: list[WatchlistItemResponse]
    ) -> dict[ItemType, list[WatchlistItemResponse]]:
        """按类型分组活跃关注项

        用于日报聚合：按类型组织关注项的更新。
        """
        result: dict[ItemType, list[WatchlistItemResponse]] = {}
        for item in items:
            if item.status != WatchlistStatus.ACTIVE:
                continue
            result.setdefault(item.item_type, []).append(item)
        return result

    def get_high_priority_values(
        self, items: list[WatchlistItemResponse]
    ) -> set[str]:
        """获取高优先级关注项的值集合

        用于日报优先级提升：高优先级关注项的相关内容优先展示。
        """
        return {
            item.item_value
            for item in items
            if item.status == WatchlistStatus.ACTIVE and item.priority_level == PriorityLevel.HIGH
        }
