"""Watchlist Pydantic Schema

定义关注列表的输入/输出/校验结构，与 domain.models.WatchlistItem 保持一致。

设计原则：
  - 枚举与 domain.models 中的定义对齐
  - Create schema 定义必填字段，Update schema 全部可选
  - Response schema 包含完整信息（id, created_at, updated_at）
  - 校验逻辑在 schema 层完成
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator
from src.domain.enums import EntityType as ItemType
from src.domain.enums import PriorityLevel, WatchlistStatus


# ──────────────────────────── 枚举 ────────────────────────────


# ──────────────────────────── 输入 Schema ────────────────────────────


class WatchlistItemCreate(BaseModel):
    """创建关注项

    必填：item_type, item_value
    可选：priority_level, group_name, notes, entity_id
    """

    item_type: ItemType = Field(..., description="对象类型（必填）")
    item_value: str = Field(
        ..., min_length=1, max_length=255, description="对象值/名称（必填）"
    )
    priority_level: PriorityLevel = Field(
        default=PriorityLevel.MEDIUM, description="优先级（默认 medium）"
    )
    group_name: str | None = Field(
        None, max_length=100, description="分组名（可选）"
    )
    notes: str | None = Field(None, description="备注（可选）")
    entity_id: UUID | None = Field(
        None, description="关联实体 ID（可选，用于与实体表对齐）"
    )

    @field_validator("item_value")
    @classmethod
    def item_value_must_not_be_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("item_value 不能为空白字符串")
        return stripped


class WatchlistItemUpdate(BaseModel):
    """更新关注项

    所有字段可选，只更新提供的字段。
    """

    priority_level: PriorityLevel | None = Field(None, description="优先级")
    group_name: str | None = Field(None, description="分组名")
    status: WatchlistStatus | None = Field(None, description="状态")
    notes: str | None = Field(None, description="备注")
    entity_id: UUID | None = Field(None, description="关联实体 ID")

    @model_validator(mode="after")
    def at_least_one_field(self) -> "WatchlistItemUpdate":
        """至少提供一个要更新的字段"""
        if all(
            v is None
            for v in [self.priority_level, self.group_name, self.status, self.notes, self.entity_id]
        ):
            raise ValueError("至少提供一个要更新的字段")
        return self


# ──────────────────────────── 输出 Schema ────────────────────────────


class WatchlistItemResponse(BaseModel):
    """关注项响应

    包含完整信息，用于 API 返回。
    """

    id: UUID
    item_type: ItemType
    item_value: str
    priority_level: PriorityLevel
    group_name: str | None
    status: WatchlistStatus
    notes: str | None
    entity_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WatchlistGroup(BaseModel):
    """关注项分组视图

    按类型或优先级分组后的结果。
    """

    group_key: str = Field(..., description="分组键（类型名或优先级名）")
    group_label: str = Field(..., description="分组显示名")
    items: list[WatchlistItemResponse] = Field(default_factory=list, description="分组内的关注项")
    count: int = Field(default=0, description="分组内项目数")

    model_config = {"from_attributes": True}
