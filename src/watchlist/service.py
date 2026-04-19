"""Watchlist 服务层

提供关注列表的 CRUD、查询和分组功能。
第一阶段使用内存存储，后续可切换到数据库。

设计原则：
  - 接口稳定，底层存储可替换
  - 校验逻辑在 schema 层完成，服务层专注业务逻辑
  - 为检索加权和日报聚合提供查询接口
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence

from src.watchlist.schemas import (
    ItemType,
    PriorityLevel,
    WatchlistGroup,
    WatchlistItemCreate,
    WatchlistItemResponse,
    WatchlistItemUpdate,
    WatchlistStatus,
)


class DuplicateItemError(Exception):
    """重复关注项错误"""

    pass


class ItemNotFoundError(Exception):
    """关注项不存在错误"""

    pass


class WatchlistService:
    """关注列表服务

    第一阶段使用内存字典存储，接口设计兼容后续数据库切换。
    """

    def __init__(self) -> None:
        self._items: dict[uuid.UUID, WatchlistItemResponse] = {}
        # (item_type, item_value) -> id 的唯一索引
        self._type_value_index: dict[tuple[str, str], uuid.UUID] = {}

    def add(self, create: WatchlistItemCreate) -> WatchlistItemResponse:
        """添加关注项

        Args:
            create: 创建参数

        Returns:
            创建后的关注项

        Raises:
            DuplicateItemError: 同类型同值已存在
        """
        key = (create.item_type, create.item_value.strip())
        if key in self._type_value_index:
            raise DuplicateItemError(
                f"关注项已存在: type={create.item_type}, value={create.item_value}"
            )

        item_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        item = WatchlistItemResponse(
            id=item_id,
            item_type=create.item_type,
            item_value=create.item_value.strip(),
            priority_level=create.priority_level,
            group_name=create.group_name,
            status=WatchlistStatus.ACTIVE,
            notes=create.notes,
            entity_id=create.entity_id,
            created_at=now,
            updated_at=now,
        )
        self._items[item_id] = item
        self._type_value_index[key] = item_id
        return item

    def get(self, item_id: uuid.UUID) -> WatchlistItemResponse:
        """获取单个关注项

        Raises:
            ItemNotFoundError: 关注项不存在
        """
        item = self._items.get(item_id)
        if item is None:
            raise ItemNotFoundError(f"关注项不存在: id={item_id}")
        return item

    def update(self, item_id: uuid.UUID, update: WatchlistItemUpdate) -> WatchlistItemResponse:
        """更新关注项

        只更新提供的字段，未提供的字段保持不变。

        Raises:
            ItemNotFoundError: 关注项不存在
        """
        old = self.get(item_id)

        # 构建更新后的对象
        updated = WatchlistItemResponse(
            id=old.id,
            item_type=old.item_type,
            item_value=old.item_value,
            priority_level=update.priority_level or old.priority_level,
            group_name=update.group_name if update.group_name is not None else old.group_name,
            status=update.status or old.status,
            notes=update.notes if update.notes is not None else old.notes,
            entity_id=update.entity_id if update.entity_id is not None else old.entity_id,
            created_at=old.created_at,
            updated_at=datetime.now(timezone.utc),
        )

        # 如果状态变为 removed，从唯一索引中移除
        if updated.status == WatchlistStatus.REMOVED and old.status != WatchlistStatus.REMOVED:
            key = (old.item_type, old.item_value)
            self._type_value_index.pop(key, None)
        # 如果从 removed 恢复为 active/paused，重新加入唯一索引
        elif old.status == WatchlistStatus.REMOVED and updated.status != WatchlistStatus.REMOVED:
            key = (updated.item_type, updated.item_value)
            if key in self._type_value_index:
                raise DuplicateItemError(
                    f"关注项已存在: type={updated.item_type}, value={updated.item_value}"
                )
            self._type_value_index[key] = item_id

        self._items[item_id] = updated
        return updated

    def remove(self, item_id: uuid.UUID) -> WatchlistItemResponse:
        """移除关注项（软删除，状态变为 removed）

        Raises:
            ItemNotFoundError: 关注项不存在
        """
        return self.update(item_id, WatchlistItemUpdate(status=WatchlistStatus.REMOVED))

    def pause(self, item_id: uuid.UUID) -> WatchlistItemResponse:
        """暂停关注项

        Raises:
            ItemNotFoundError: 关注项不存在
        """
        return self.update(item_id, WatchlistItemUpdate(status=WatchlistStatus.PAUSED))

    def resume(self, item_id: uuid.UUID) -> WatchlistItemResponse:
        """恢复关注项

        Raises:
            ItemNotFoundError: 关注项不存在
        """
        return self.update(item_id, WatchlistItemUpdate(status=WatchlistStatus.ACTIVE))

    # ── 查询 ──

    def list_active(self) -> list[WatchlistItemResponse]:
        """获取所有活跃关注项"""
        return [item for item in self._items.values() if item.status == WatchlistStatus.ACTIVE]

    def list_all(self, include_removed: bool = False) -> list[WatchlistItemResponse]:
        """获取所有关注项

        Args:
            include_removed: 是否包含已移除的项
        """
        if include_removed:
            return list(self._items.values())
        return [item for item in self._items.values() if item.status != WatchlistStatus.REMOVED]

    def list_by_type(self, item_type: ItemType) -> list[WatchlistItemResponse]:
        """按对象类型筛选（仅活跃项）"""
        return [
            item for item in self._items.values()
            if item.item_type == item_type and item.status == WatchlistStatus.ACTIVE
        ]

    def list_by_priority(self, priority: PriorityLevel) -> list[WatchlistItemResponse]:
        """按优先级筛选（仅活跃项）"""
        return [
            item for item in self._items.values()
            if item.priority_level == priority and item.status == WatchlistStatus.ACTIVE
        ]

    def list_by_group(self, group_name: str) -> list[WatchlistItemResponse]:
        """按分组名筛选（仅活跃项）"""
        return [
            item for item in self._items.values()
            if item.group_name == group_name and item.status == WatchlistStatus.ACTIVE
        ]

    def find_by_type_value(self, item_type: ItemType, item_value: str) -> WatchlistItemResponse | None:
        """按类型+值查找关注项"""
        key = (item_type, item_value.strip())
        item_id = self._type_value_index.get(key)
        if item_id is None:
            return None
        return self._items.get(item_id)

    # ── 分组视图 ──

    def group_by_type(self) -> list[WatchlistGroup]:
        """按对象类型分组"""
        type_labels = {
            ItemType.PERSON: "人物",
            ItemType.COMPANY: "公司",
            ItemType.PRODUCT: "产品",
            ItemType.MODEL: "模型",
            ItemType.TOPIC: "主题",
            ItemType.TRACK: "赛道",
            ItemType.KEYWORD: "关键词",
        }
        groups: dict[str, list[WatchlistItemResponse]] = {}
        for item in self.list_active():
            groups.setdefault(item.item_type, []).append(item)

        result = []
        for itype in ItemType:
            items = groups.get(itype, [])
            result.append(WatchlistGroup(
                group_key=itype,
                group_label=type_labels.get(itype, itype),
                items=items,
                count=len(items),
            ))
        return result

    def group_by_priority(self) -> list[WatchlistGroup]:
        """按优先级分组"""
        priority_labels = {
            PriorityLevel.HIGH: "高优先级",
            PriorityLevel.MEDIUM: "中优先级",
            PriorityLevel.LOW: "低优先级",
        }
        groups: dict[str, list[WatchlistItemResponse]] = {}
        for item in self.list_active():
            groups.setdefault(item.priority_level, []).append(item)

        result = []
        for pl in [PriorityLevel.HIGH, PriorityLevel.MEDIUM, PriorityLevel.LOW]:
            items = groups.get(pl, [])
            result.append(WatchlistGroup(
                group_key=pl,
                group_label=priority_labels.get(pl, pl),
                items=items,
                count=len(items),
            ))
        return result

    # ── 统计 ──

    def count(self, status: WatchlistStatus | None = None) -> int:
        """统计关注项数量"""
        if status is None:
            return len(self._items)
        return sum(1 for item in self._items.values() if item.status == status)

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"<WatchlistService total={len(self._items)} active={self.count(WatchlistStatus.ACTIVE)}>"
