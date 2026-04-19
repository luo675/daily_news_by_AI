"""API 统一响应 Schema

与 docs/api_spec.md 对齐，定义所有接口共用的响应结构。

设计原则：
  - 统一响应包含 summary/evidence/opportunities/risks/uncertainties/related_topics/watchlist_updates/meta
  - 错误响应包含 error_code/message/details
  - 双语字段使用 {zh, en} 对象
  - 所有字段可选，不同接口按需填充
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ──────────────────────────── 基础结构 ────────────────────────────


class BilingualText(BaseModel):
    """双语文本"""

    zh: str | None = Field(None, description="中文")
    en: str | None = Field(None, description="英文")


class MetaInfo(BaseModel):
    """响应元信息"""

    result_count: int | None = Field(None, description="结果数量")
    brief_type: str | None = Field(None, description="简报类型（scheduled/on_demand）")
    page: int | None = Field(None, description="当前页码")
    page_size: int | None = Field(None, description="每页大小")
    extra: dict[str, Any] | None = Field(None, description="额外元信息")

    model_config = {"extra": "allow"}


class OpportunityScore(BaseModel):
    """机会评分结构"""

    need_realness: int | None = Field(None, ge=1, le=10, description="需求真实性 (1-10)")
    market_gap: int | None = Field(None, ge=1, le=10, description="市场空白度 (1-10)")
    feasibility: int | None = Field(None, ge=1, le=10, description="产品化可行性 (1-10)")
    priority: int | None = Field(None, ge=1, le=10, description="跟进优先级 (1-10)")
    evidence: int | None = Field(None, ge=1, le=10, description="证据充分度 (1-10)")
    total: float | None = Field(None, description="加权总分")


class EvidenceItem(BaseModel):
    """证据条目"""

    content: str | None = Field(None, description="证据内容")
    source_url: str | None = Field(None, description="来源链接")
    evidence_type: str | None = Field(None, description="证据类型: quote/data/trend/expert_opinion")
    document_id: str | None = Field(None, description="来源文档 ID")


class WatchlistUpdate(BaseModel):
    """关注列表更新"""

    item_type: str | None = Field(None, description="对象类型")
    item_value: str | None = Field(None, description="对象值")
    action: str | None = Field(None, description="操作: added/updated/removed")


class UncertaintyItem(BaseModel):
    """不确定性条目"""

    description: str | None = Field(None, description="不确定性描述")
    reason: str | None = Field(None, description="原因")
    related_conflict_ids: list[str] | None = Field(None, description="关联冲突 ID")


class RiskItem(BaseModel):
    """风险条目"""

    title: str | None = Field(None, description="风险标题")
    description: str | None = Field(None, description="风险描述")
    severity: str | None = Field(None, description="严重程度: high/medium/low")


class OpportunityItem(BaseModel):
    """产品机会条目"""

    title_zh: str | None = Field(None, description="中文标题")
    title_en: str | None = Field(None, description="英文标题")
    scores: OpportunityScore | None = Field(None, description="评分")
    evidence: list[EvidenceItem] | None = Field(None, description="证据列表")
    uncertainty: bool | None = Field(None, description="是否存在不确定性")
    uncertainty_reason: str | None = Field(None, description="不确定性原因")


# ──────────────────────────── 统一响应 ────────────────────────────


class UnifiedResponse(BaseModel):
    """统一响应结构

    所有 API 接口返回此结构，不同接口按需填充字段。
    与 api_spec.md 第 3 节对齐。
    """

    summary: BilingualText | None = Field(None, description="摘要")
    evidence: list[EvidenceItem] | None = Field(None, description="证据列表")
    opportunities: list[OpportunityItem] | None = Field(None, description="产品机会列表")
    risks: list[RiskItem] | None = Field(None, description="风险列表")
    uncertainties: list[UncertaintyItem] | None = Field(None, description="不确定性列表")
    related_topics: list[str] | None = Field(None, description="相关主题")
    watchlist_updates: list[WatchlistUpdate] | None = Field(None, description="关注更新")
    meta: MetaInfo | None = Field(None, description="元信息")

    model_config = {"extra": "allow"}


# ──────────────────────────── 错误响应 ────────────────────────────


class ErrorResponse(BaseModel):
    """统一错误响应

    与 api_spec.md 第 6 节对齐。
    """

    error_code: str = Field(..., description="错误代码")
    message: str = Field(..., description="错误消息")
    details: dict[str, Any] | None = Field(None, description="错误详情")


# ──────────────────────────── 请求 Schema ────────────────────────────


class SearchRequest(BaseModel):
    """搜索请求"""

    query: str = Field(..., min_length=1, description="搜索查询")
    topics: list[str] | None = Field(None, description="主题过滤")
    watchlist_only: bool = Field(default=False, description="仅搜索关注项相关内容")
    date_from: datetime | None = Field(None, description="起始日期")
    date_to: datetime | None = Field(None, description="截止日期")
    limit: int = Field(default=10, ge=1, le=100, description="返回条数限制")


class BriefGenerateRequest(BaseModel):
    """简报生成请求"""

    as_of: datetime | None = Field(None, description="简报截止时间")
    watchlist_scope: bool = Field(default=True, description="是否限定关注范围")
    force_refresh: bool = Field(default=False, description="是否强制刷新")


class WatchlistCreateRequest(BaseModel):
    """关注项创建请求"""

    item_type: str = Field(..., description="对象类型")
    item_value: str = Field(..., min_length=1, description="对象值/名称")
    priority_level: str = Field(default="medium", description="优先级: high/medium/low")
    group_name: str | None = Field(None, description="分组名")
    notes: str | None = Field(None, description="备注")


class ReviewPatchRequest(BaseModel):
    """人工修订请求"""

    field_name: str = Field(..., description="修订字段名")
    new_value: Any = Field(..., description="新值")
    reason: str | None = Field(None, description="修订原因")


# ──────────────────────────── 专用响应 ────────────────────────────


class BriefResponse(BaseModel):
    """日报响应"""

    date: str | None = Field(None, description="日报日期")
    summary: BilingualText | None = Field(None, description="摘要")
    opportunities: list[OpportunityItem] | None = Field(None, description="产品机会")
    risks: list[RiskItem] | None = Field(None, description="风险")
    uncertainties: list[UncertaintyItem] | None = Field(None, description="不确定性")
    watchlist_updates: list[WatchlistUpdate] | None = Field(None, description="关注更新")
    meta: MetaInfo | None = Field(None, description="元信息")


class OpportunityListResponse(BaseModel):
    """机会列表响应"""

    items: list[OpportunityItem] = Field(default_factory=list, description="机会列表")
    meta: MetaInfo | None = Field(None, description="元信息")


class TopicDetailResponse(BaseModel):
    """主题详情响应"""

    id: str | None = Field(None, description="主题 ID")
    name_zh: str | None = Field(None, description="中文名称")
    name_en: str | None = Field(None, description="英文名称")
    description: str | None = Field(None, description="描述")
    related_documents: list[EvidenceItem] | None = Field(None, description="相关文档")
    related_entities: list[str] | None = Field(None, description="关联实体")
    trend_summary: BilingualText | None = Field(None, description="趋势摘要")


class WatchlistResponse(BaseModel):
    """关注列表响应"""

    items: list[dict[str, Any]] = Field(default_factory=list, description="关注项列表")
    grouped_by_type: dict[str, list[dict[str, Any]]] | None = Field(None, description="按类型分组")
    grouped_by_priority: dict[str, list[dict[str, Any]]] | None = Field(None, description="按优先级分组")
    meta: MetaInfo | None = Field(None, description="元信息")


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str = Field(default="ok", description="服务状态")
    version: str | None = Field(None, description="版本号")
    database: str | None = Field(None, description="数据库状态")
    quota: dict[str, Any] | None = Field(None, description="配额状态")
