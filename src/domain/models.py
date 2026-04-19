"""第一阶段核心数据模型

覆盖 TC-06 要求的 16 张核心表：
  sources / documents / document_summaries / chunks / chunk_embeddings
  entities / document_entities / topics / document_topics
  conflicts / opportunity_assessments / opportunity_evidence
  daily_briefs / watchlist_items / api_keys / review_edits

设计原则：
  - 只做第一阶段需要的字段，不过度设计
  - 命名统一（snake_case），可扩展
  - 保留后续升级空间，但不提前实现复杂图谱
  - 双语字段统一使用 _zh / _en 后缀
  - 所有业务表使用 UUID 主键 + 时间戳
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from src.domain.base import Base, TimestampMixin, UUIDPrimaryKey
from src.domain.enums import (
    CredibilityLevel,
    EntityType,
    PriorityLevel,
    ReviewTargetType,
    SourceType,
    WatchlistStatus,
)


# ──────────────────────────── 枚举定义 ────────────────────────────


class FetchStrategy(StrEnum):
    """采集策略"""

    RSS = "rss"
    API = "api"
    SCRAPE = "scrape"
    MANUAL = "manual"


class DocumentStatus(StrEnum):
    """文档生命周期状态（对应 TC-07）"""

    RAW = "raw"
    CLEANING = "cleaning"
    CLEANED = "cleaned"
    PROCESSING = "processing"
    PROCESSED = "processed"
    INDEXED = "indexed"
    FAILED = "failed"


class ConflictType(StrEnum):
    """冲突类型"""

    FACTUAL = "factual"
    OPINION = "opinion"
    TEMPORAL = "temporal"


class ResolutionStatus(StrEnum):
    """冲突解决状态"""

    UNRESOLVED = "unresolved"
    RESOLVED_AUTO = "resolved_auto"
    RESOLVED_MANUAL = "resolved_manual"
    UNCERTAIN = "uncertain"


class OpportunityStatus(StrEnum):
    """机会评估状态"""

    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    WATCHING = "watching"


class EvidenceType(StrEnum):
    """证据类型"""

    QUOTE = "quote"
    DATA = "data"
    TREND = "trend"
    EXPERT_OPINION = "expert_opinion"


class BriefType(StrEnum):
    """日报类型"""

    SCHEDULED = "scheduled"
    ON_DEMAND = "on_demand"


class QuotaMode(StrEnum):
    """配额模式"""

    TOKEN = "token"
    COUNT = "count"


# ──────────────────────────── 模型定义 ────────────────────────────


class Source(UUIDPrimaryKey, TimestampMixin, Base):
    """来源注册表

    管理所有数据来源的类型、可信度、采集策略和启停状态。
    对应模块：source_registry
    """

    __tablename__ = "sources"

    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="来源名称")
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="来源类型: blog/speech/interview/podcast_transcript/manual_import"
    )
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True, comment="来源 URL")
    credibility_level: Mapped[str] = mapped_column(
        String(1), nullable=False, default=CredibilityLevel.C, comment="可信度等级: S/A/B/C"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    fetch_strategy: Mapped[str] = mapped_column(
        String(50), nullable=False, default=FetchStrategy.MANUAL, comment="采集策略: rss/api/scrape/manual"
    )
    config: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="来源专属配置（RSS 地址、抓取规则等）"
    )

    # ── 关系 ──
    documents: Mapped[list["Document"]] = relationship(
        back_populates="source", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Source {self.name!r} ({self.source_type})>"


class Document(UUIDPrimaryKey, TimestampMixin, Base):
    """文档主表

    存储采集到的原始文档元数据与状态。
    第一阶段不强求保存全文，优先保存摘要和结构化结果。
    对应模块：document_ingestion / document_processing
    """

    __tablename__ = "documents"

    source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, comment="来源 ID"
    )
    title: Mapped[str] = mapped_column(String(1024), nullable=False, comment="标题")
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True, comment="原文链接")
    author: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="作者")
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="发布时间"
    )
    fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="抓取时间"
    )
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True, comment="原文文本（第一阶段可选）")
    language: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="语言代码，如 en/zh")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DocumentStatus.RAW, comment="文档状态"
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True, comment="内容哈希（SHA-256，用于去重）"
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        comment="额外元数据（来源特有字段、原始格式等）",
    )

    # ── 关系 ──
    source: Mapped["Source | None"] = relationship(back_populates="documents", lazy="selectin")
    summary: Mapped["DocumentSummary | None"] = relationship(
        back_populates="document", uselist=False, lazy="selectin"
    )
    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", lazy="selectin", cascade="all, delete-orphan"
    )
    document_entities: Mapped[list["DocumentEntity"]] = relationship(
        back_populates="document", lazy="selectin", cascade="all, delete-orphan"
    )
    document_topics: Mapped[list["DocumentTopic"]] = relationship(
        back_populates="document", lazy="selectin", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # URL 去重索引（同一 URL 不重复采集）
        UniqueConstraint("url", name="uq_documents_url"),
    )

    def __repr__(self) -> str:
        return f"<Document {self.title!r} ({self.status})>"


class DocumentSummary(UUIDPrimaryKey, TimestampMixin, Base):
    """文档摘要表

    存储文档的中英双语摘要、关键点和标签。
    对应模块：document_processing（摘要生成）
    """

    __tablename__ = "document_summaries"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="文档 ID（一对一）",
    )
    summary_zh: Mapped[str | None] = mapped_column(Text, nullable=True, comment="中文摘要")
    summary_en: Mapped[str | None] = mapped_column(Text, nullable=True, comment="英文摘要")
    key_points: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="关键点列表")
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="标签列表")
    generated_by: Mapped[str] = mapped_column(
        String(20), nullable=False, default="auto", comment="生成方式: auto/manual"
    )

    # ── 关系 ──
    document: Mapped["Document"] = relationship(back_populates="summary", lazy="selectin")

    def __repr__(self) -> str:
        return f"<DocumentSummary doc={self.document_id}>"


class Chunk(UUIDPrimaryKey, TimestampMixin, Base):
    """文档分段切块

    将文档按语义或固定长度切分为可检索的块。
    对应模块：document_processing（分段切块）
    """

    __tablename__ = "chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, comment="文档 ID"
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, comment="块序号（从 0 开始）")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="块文本内容")
    char_count: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="字符数")
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Token 数（预留）")
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True, comment="块级元数据"
    )

    # ── 关系 ──
    document: Mapped["Document"] = relationship(back_populates="chunks", lazy="selectin")
    embedding: Mapped["ChunkEmbedding | None"] = relationship(
        back_populates="chunk", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        # 同一文档内块序号唯一
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_doc_index"),
    )

    def __repr__(self) -> str:
        return f"<Chunk doc={self.document_id} idx={self.chunk_index}>"


class ChunkEmbedding(UUIDPrimaryKey, TimestampMixin, Base):
    """块向量索引

    存储 chunk 的向量嵌入，用于语义检索。
    使用 pgvector 扩展。
    对应模块：knowledge_indexing
    """

    __tablename__ = "chunk_embeddings"

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="Chunk ID（一对一）",
    )
    embedding: Mapped[Any] = mapped_column(
        Vector(1536),  # 默认维度 1536（text-embedding-ada-002），后续可调整
        nullable=False,
        comment="向量嵌入",
    )
    model_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Embedding 模型名称"
    )
    dimension: Mapped[int] = mapped_column(Integer, nullable=False, default=1536, comment="向量维度")

    # ── 关系 ──
    chunk: Mapped["Chunk"] = relationship(back_populates="embedding", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ChunkEmbedding chunk={self.chunk_id} model={self.model_name}>"


class Entity(UUIDPrimaryKey, TimestampMixin, Base):
    """实体表

    存储从文档中抽取的实体（人物、公司、产品、模型、主题、赛道、关键词）。
    支持别名归一化，与 watchlist 共用类型定义。
    对应模块：document_processing（实体抽取）
    """

    __tablename__ = "entities"

    entity_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="实体类型: person/company/product/model/topic/track/keyword",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="实体名称")
    aliases: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="别名列表（用于归一化）")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="实体描述")

    # ── 关系 ──
    document_entities: Mapped[list["DocumentEntity"]] = relationship(
        back_populates="entity", lazy="selectin", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # 同类型同名实体唯一
        UniqueConstraint("entity_type", "name", name="uq_entities_type_name"),
    )

    def __repr__(self) -> str:
        return f"<Entity {self.name!r} ({self.entity_type})>"


class DocumentEntity(UUIDPrimaryKey, Base):
    """文档-实体关联表

    记录文档中出现的实体及其相关性。
    对应模块：document_processing（实体关联）
    """

    __tablename__ = "document_entities"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, comment="文档 ID"
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), nullable=False, comment="实体 ID"
    )
    relevance_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="相关性分数 (0.0-1.0)"
    )
    context: Mapped[str | None] = mapped_column(Text, nullable=True, comment="出现上下文")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
        nullable=False,
    )

    # ── 关系 ──
    document: Mapped["Document"] = relationship(back_populates="document_entities", lazy="selectin")
    entity: Mapped["Entity"] = relationship(back_populates="document_entities", lazy="selectin")

    __table_args__ = (
        # 同一文档不重复关联同一实体
        UniqueConstraint("document_id", "entity_id", name="uq_doc_entities_doc_entity"),
    )

    def __repr__(self) -> str:
        return f"<DocumentEntity doc={self.document_id} entity={self.entity_id}>"


class Topic(UUIDPrimaryKey, TimestampMixin, Base):
    """主题表

    存储从文档中提取或人工创建的主题。
    支持层级结构（parent_id 自引用），预留后续图谱扩展。
    对应模块：document_processing（主题归类）
    """

    __tablename__ = "topics"

    name_zh: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="中文名称")
    name_en: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="英文名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="主题描述")
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"),
        nullable=True,
        comment="父主题 ID（支持层级）",
    )

    # ── 关系 ──
    parent: Mapped["Topic | None"] = relationship(
        remote_side="Topic.id", lazy="selectin"
    )
    document_topics: Mapped[list["DocumentTopic"]] = relationship(
        back_populates="topic", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Topic {self.name_en or self.name_zh!r}>"


class DocumentTopic(UUIDPrimaryKey, Base):
    """文档-主题关联表

    记录文档与主题的关联及相关性分数。
    对应模块：document_processing（主题归类）
    """

    __tablename__ = "document_topics"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, comment="文档 ID"
    )
    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=False, comment="主题 ID"
    )
    relevance_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="相关性分数 (0.0-1.0)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
        nullable=False,
    )

    # ── 关系 ──
    document: Mapped["Document"] = relationship(back_populates="document_topics", lazy="selectin")
    topic: Mapped["Topic"] = relationship(back_populates="document_topics", lazy="selectin")

    __table_args__ = (
        # 同一文档不重复关联同一主题
        UniqueConstraint("document_id", "topic_id", name="uq_doc_topics_doc_topic"),
    )

    def __repr__(self) -> str:
        return f"<DocumentTopic doc={self.document_id} topic={self.topic_id}>"


class Conflict(UUIDPrimaryKey, TimestampMixin, Base):
    """冲突记录表

    记录检测到的事实冲突、观点冲突和时间冲突。
    结合来源可信度做倾向判断，无法判断时保留不确定性。
    对应模块：conflict_resolution
    """

    __tablename__ = "conflicts"

    conflict_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="冲突类型: factual/opinion/temporal",
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, comment="冲突描述")
    resolution_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ResolutionStatus.UNRESOLVED,
        comment="解决状态: unresolved/resolved_auto/resolved_manual/uncertain",
    )
    resolution_note: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="解决说明"
    )
    involved_document_ids: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="涉及的文档 ID 列表"
    )
    involved_entity_ids: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="涉及的实体 ID 列表"
    )

    def __repr__(self) -> str:
        return f"<Conflict {self.conflict_type} ({self.resolution_status})>"


class OpportunityAssessment(UUIDPrimaryKey, TimestampMixin, Base):
    """产品机会评估表

    存储产品机会判断的结构化结果，包含五维评分和总分。
    评分维度（对应 project_overview.md）：
      - need_realness: 需求真实性 30%
      - market_gap: 市场空白度 30%
      - feasibility: 产品化可行性 20%
      - priority: 跟进优先级 10%
      - evidence_score: 证据充分度 10%
    对应模块：opportunity_scoring
    """

    __tablename__ = "opportunity_assessments"

    title_zh: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="中文标题")
    title_en: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="英文标题")
    description_zh: Mapped[str | None] = mapped_column(Text, nullable=True, comment="中文描述")
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True, comment="英文描述")
    need_realness: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="需求真实性 (1-10)"
    )
    market_gap: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="市场空白度 (1-10)"
    )
    feasibility: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="产品化可行性 (1-10)"
    )
    priority: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="跟进优先级 (1-10)"
    )
    evidence_score: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="证据充分度 (1-10)"
    )
    total_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="加权总分"
    )
    uncertainty: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否存在不确定性"
    )
    uncertainty_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="不确定性原因"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=OpportunityStatus.CANDIDATE,
        comment="状态: candidate/confirmed/dismissed/watching",
    )

    # ── 关系 ──
    evidence_items: Mapped[list["OpportunityEvidence"]] = relationship(
        back_populates="opportunity", lazy="selectin", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<OpportunityAssessment {self.title_en or self.title_zh!r} total={self.total_score}>"


class OpportunityEvidence(UUIDPrimaryKey, Base):
    """机会证据表

    存储支撑产品机会判断的证据条目，可回溯到原始文档。
    对应模块：opportunity_scoring
    """

    __tablename__ = "opportunity_evidence"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_assessments.id", ondelete="CASCADE"),
        nullable=False, comment="机会评估 ID",
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True, comment="来源文档 ID（可选）",
    )
    evidence_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="证据类型: quote/data/trend/expert_opinion",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="证据内容")
    source_url: Mapped[str | None] = mapped_column(
        String(2048), nullable=True, comment="来源链接"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
        nullable=False,
    )

    # ── 关系 ──
    opportunity: Mapped["OpportunityAssessment"] = relationship(
        back_populates="evidence_items", lazy="selectin"
    )
    document: Mapped["Document | None"] = relationship(lazy="selectin")

    def __repr__(self) -> str:
        return f"<OpportunityEvidence opp={self.opportunity_id} type={self.evidence_type}>"


class DailyBrief(UUIDPrimaryKey, TimestampMixin, Base):
    """每日简报表

    存储每日自动生成或按需生成的简报内容。
    第一阶段输出 Markdown 格式。
    对应模块：daily_briefing
    """

    __tablename__ = "daily_briefs"

    brief_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True, comment="简报日期"
    )
    brief_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BriefType.SCHEDULED,
        comment="简报类型: scheduled/on_demand",
    )
    content_zh: Mapped[str | None] = mapped_column(Text, nullable=True, comment="中文简报内容（Markdown）")
    content_en: Mapped[str | None] = mapped_column(Text, nullable=True, comment="英文简报内容（Markdown）")
    summary_zh: Mapped[str | None] = mapped_column(Text, nullable=True, comment="中文摘要")
    summary_en: Mapped[str | None] = mapped_column(Text, nullable=True, comment="英文摘要")
    highlights: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="今日重点")
    opportunities: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="产品机会列表")
    risks: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="风险列表")
    uncertainties: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="不确定性列表")
    watchlist_updates: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="关注更新")
    pending_questions: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="待验证问题")
    as_of_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="简报截止时间"
    )

    __table_args__ = (
        # 每天只生成一份固定简报，按需简报不限
        UniqueConstraint("brief_date", "brief_type", name="uq_daily_briefs_date_type"),
    )

    def __repr__(self) -> str:
        return f"<DailyBrief {self.brief_date.date()} ({self.brief_type})>"


class WatchlistItem(UUIDPrimaryKey, TimestampMixin, Base):
    """关注列表项

    管理用户关注的对象，支持按对象类型和优先级分组。
    可关联到已识别实体，为检索和日报提供加权上下文。
    对应模块：watchlist
    """

    __tablename__ = "watchlist_items"

    item_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="对象类型: person/company/product/model/topic/track/keyword",
    )
    item_value: Mapped[str] = mapped_column(String(255), nullable=False, comment="对象值/名称")
    priority_level: Mapped[str] = mapped_column(
        String(10), nullable=False, default=PriorityLevel.MEDIUM,
        comment="优先级: high/medium/low",
    )
    group_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="分组名"
    )
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default=WatchlistStatus.ACTIVE,
        comment="状态: active/paused/removed",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注")
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True, comment="关联实体 ID（可选）",
    )

    # ── 关系 ──
    entity: Mapped["Entity | None"] = relationship(lazy="selectin")

    __table_args__ = (
        # 同类型同值不重复
        UniqueConstraint("item_type", "item_value", name="uq_watchlist_type_value"),
    )

    def __repr__(self) -> str:
        return f"<WatchlistItem {self.item_value!r} ({self.item_type})>"


class ApiKey(UUIDPrimaryKey, TimestampMixin, Base):
    """API 密钥表

    管理单用户密钥的鉴权和配额。
    第一阶段全部开放，但需要密钥和配额控制。
    对应模块：agent_api
    """

    __tablename__ = "api_keys"

    key_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, comment="密钥哈希（不存明文）"
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="密钥名称/描述")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    quota_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default=QuotaMode.TOKEN,
        comment="配额模式: token/count",
    )
    quota_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100000, comment="配额上限"
    )
    quota_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="已用配额"
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最后使用时间"
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="过期时间（NULL 表示永不过期）"
    )

    def __repr__(self) -> str:
        return f"<ApiKey {self.name!r} active={self.is_active}>"


class ReviewEdit(UUIDPrimaryKey, Base):
    """人工修订记录表

    记录所有人工修订操作，人工结果优先级高于自动结果。
    支持修订摘要、标签、机会分数、结论、优先级等。
    对应模块：admin_review
    """

    __tablename__ = "review_edits"

    target_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True,
        comment="修订目标类型: summary/tags/opportunity_score/conclusion/priority/topic",
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False, comment="修订目标 ID（对应目标表的主键）"
    )
    field_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="修订字段名"
    )
    old_value: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="旧值（JSON 序列化）"
    )
    new_value: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="新值（JSON 序列化）"
    )
    reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="修订原因"
    )
    reviewer: Mapped[str] = mapped_column(
        String(100), nullable=False, default="owner", comment="修订人"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default="now()",
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ReviewEdit {self.target_type}:{self.field_name}>"
