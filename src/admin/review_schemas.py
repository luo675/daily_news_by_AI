"""人工修订 Schema

定义可修订字段、修订请求/响应结构。
与 domain.models.ReviewEdit 和 api_spec.md 对齐。

设计原则：
  - target_type + field_name 组合必须合法
  - old_value / new_value 使用 JSON 序列化存储任意类型
  - 人工修订标记 source="manual"，自动结果标记 source="auto"
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator
from src.domain.enums import ReviewTargetType


# ──────────────────────────── 枚举 ────────────────────────────


class ReviewFieldName(StrEnum):
    """修订字段名

    每种 target_type 允许修订的字段。
    """

    # summary 目标
    SUMMARY_ZH = "summary_zh"
    SUMMARY_EN = "summary_en"
    KEY_POINTS = "key_points"

    # tags 目标
    TAGS = "tags"

    # opportunity_score 目标
    NEED_REALNESS = "need_realness"
    MARKET_GAP = "market_gap"
    FEASIBILITY = "feasibility"
    PRIORITY_SCORE = "priority_score"
    EVIDENCE_SCORE = "evidence_score"
    TOTAL_SCORE = "total_score"
    UNCERTAINTY_FLAG = "uncertainty"
    UNCERTAINTY_REASON = "uncertainty_reason"
    STATUS = "status"

    # conclusion 目标
    CONCLUSION_ZH = "conclusion_zh"
    CONCLUSION_EN = "conclusion_en"

    # priority 目标
    PRIORITY_LEVEL = "priority_level"

    # topic 目标
    TOPIC_NAME_ZH = "name_zh"
    TOPIC_NAME_EN = "name_en"
    TOPIC_DESCRIPTION = "description"

    # uncertainty 目标
    UNCERTAINTY_STATUS = "uncertainty_status"
    UNCERTAINTY_NOTE = "uncertainty_note"

    # risk 目标
    RISK_SEVERITY = "severity"
    RISK_DESCRIPTION = "description"


# ──────────────────────────── 允许的字段映射 ────────────────────────────

# 每个 target_type 允许修订的 field_name 列表
ALLOWED_FIELD_NAMES: dict[ReviewTargetType, list[ReviewFieldName]] = {
    ReviewTargetType.SUMMARY: [
        ReviewFieldName.SUMMARY_ZH,
        ReviewFieldName.SUMMARY_EN,
        ReviewFieldName.KEY_POINTS,
    ],
    ReviewTargetType.TAGS: [
        ReviewFieldName.TAGS,
    ],
    ReviewTargetType.OPPORTUNITY_SCORE: [
        ReviewFieldName.NEED_REALNESS,
        ReviewFieldName.MARKET_GAP,
        ReviewFieldName.FEASIBILITY,
        ReviewFieldName.PRIORITY_SCORE,
        ReviewFieldName.EVIDENCE_SCORE,
        ReviewFieldName.TOTAL_SCORE,
        ReviewFieldName.UNCERTAINTY_FLAG,
        ReviewFieldName.UNCERTAINTY_REASON,
        ReviewFieldName.STATUS,
    ],
    ReviewTargetType.CONCLUSION: [
        ReviewFieldName.CONCLUSION_ZH,
        ReviewFieldName.CONCLUSION_EN,
    ],
    ReviewTargetType.PRIORITY: [
        ReviewFieldName.PRIORITY_LEVEL,
    ],
    ReviewTargetType.TOPIC: [
        ReviewFieldName.TOPIC_NAME_ZH,
        ReviewFieldName.TOPIC_NAME_EN,
        ReviewFieldName.TOPIC_DESCRIPTION,
    ],
    ReviewTargetType.UNCERTAINTY: [
        ReviewFieldName.UNCERTAINTY_STATUS,
        ReviewFieldName.UNCERTAINTY_NOTE,
    ],
    ReviewTargetType.RISK: [
        ReviewFieldName.RISK_SEVERITY,
        ReviewFieldName.RISK_DESCRIPTION,
    ],
}


# ──────────────────────────── 请求 Schema ────────────────────────────


class ReviewEditCreate(BaseModel):
    """创建修订记录

    必填：field_name, new_value
    可选：old_value, reason, reviewer
    target_type 和 target_id 从 API 路径参数获取。
    """

    field_name: str = Field(..., description="修订字段名")
    new_value: Any = Field(..., description="新值")
    old_value: Any | None = Field(None, description="旧值（可选，服务层可自动获取）")
    reason: str | None = Field(None, description="修订原因")
    reviewer: str = Field(default="owner", description="修订人")

    @field_validator("field_name")
    @classmethod
    def field_name_must_be_valid(cls, v: str) -> str:
        """检查 field_name 是否是已知的字段名"""
        valid_names = {fn.value for fn in ReviewFieldName}
        if v not in valid_names:
            raise ValueError(
                f"未知的字段名: {v!r}，合法值: {sorted(valid_names)}"
            )
        return v


class ReviewEditBatch(BaseModel):
    """批量修订请求

    一次修订同一目标的多个字段。
    """

    edits: list[ReviewEditCreate] = Field(..., min_length=1, description="修订列表")
    reason: str | None = Field(None, description="整体修订原因（覆盖单条 reason）")

    @model_validator(mode="after")
    def edits_not_empty(self) -> "ReviewEditBatch":
        if not self.edits:
            raise ValueError("edits 不能为空")
        return self


# ──────────────────────────── 响应 Schema ────────────────────────────


class ReviewEditResponse(BaseModel):
    """修订记录响应"""

    id: UUID
    target_type: str
    target_id: UUID
    field_name: str
    old_value: Any | None
    new_value: Any | None
    reason: str | None
    reviewer: str
    source: str = Field(default="manual", description="来源标记: manual/auto")
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewHistoryResponse(BaseModel):
    """修订历史响应"""

    target_type: str
    target_id: UUID
    edits: list[ReviewEditResponse] = Field(default_factory=list)
    total_count: int = Field(default=0)
    latest_values: dict[str, Any] = Field(
        default_factory=dict,
        description="各字段最新人工修订值（人工覆盖自动的依据）",
    )


class OverrideStatus(BaseModel):
    """字段覆盖状态

    标记某个字段当前是人工值还是自动值。
    """

    field_name: str
    source: str = Field(description="manual 或 auto")
    last_manual_value: Any | None = Field(None, description="最近一次人工修订值")
    last_manual_at: datetime | None = Field(None, description="最近一次人工修订时间")
    current_auto_value: Any | None = Field(None, description="当前自动值（如有）")
