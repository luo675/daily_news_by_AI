"""统一采集输入 Schema

定义所有来源类型映射到的统一文档输入对象。
使用 Pydantic v2 进行数据校验和序列化。

设计原则：
  - 必填字段：保证后续处理（清洗、摘要、实体抽取、入库）最低需要
  - 可选字段：来源特有信息，不强制要求
  - 双语字段暂不在输入层要求，由处理层生成
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from src.domain.enums import CredibilityLevel, SourceType


# ──────────────────────────── 枚举 ────────────────────────────


# ──────────────────────────── Schema ────────────────────────────


class DocumentMetadata(BaseModel):
    """文档额外元数据

    存储来源特有的、不属于标准字段的附加信息。
    不同来源类型可填充不同内容。
    """

    # 博客特有
    blog_platform: str | None = Field(None, description="博客平台（如 Medium、Substack、个人站）")

    # 演讲特有
    event_name: str | None = Field(None, description="演讲活动名称")
    event_location: str | None = Field(None, description="演讲地点")

    # 访谈特有
    interviewer: str | None = Field(None, description="访谈者")
    interviewee: str | None = Field(None, description="受访者")

    # 播客特有
    podcast_name: str | None = Field(None, description="播客节目名称")
    episode_number: str | int | None = Field(None, description="集数")
    duration_minutes: int | None = Field(None, description="时长（分钟）")

    # 通用扩展
    original_format: str | None = Field(None, description="原始格式（html/markdown/pdf/text）")
    extra: dict[str, Any] | None = Field(None, description="其他扩展字段")

    model_config = {"extra": "allow"}


class RawDocumentInput(BaseModel):
    """统一文档输入对象

    所有来源类型采集到的内容，最终都映射到此结构。
    这是采集层输出、处理层输入的边界对象。

    必填字段：
      - title: 文档标题
      - source_type: 来源类型
      - content_text: 正文文本
      - fetched_at: 采集时间

    可选字段：
      - url, author, published_at, language, credibility_level,
        source_name, metadata 等
    """

    # ── 必填字段 ──
    title: str = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="文档标题（必填）",
    )
    source_type: SourceType = Field(
        ...,
        description="来源类型（必填）: blog/speech/interview/podcast_transcript/manual_import",
    )
    content_text: str = Field(
        ...,
        min_length=1,
        description="正文文本（必填，至少 1 个字符）",
    )
    fetched_at: datetime = Field(
        default_factory=lambda: datetime.now(),
        description="采集时间（必填，默认当前时间）",
    )

    # ── 可选字段 ──
    url: str | None = Field(
        None,
        max_length=2048,
        description="原文链接（可选，用于去重和回溯）",
    )
    author: str | None = Field(
        None,
        max_length=255,
        description="作者（可选）",
    )
    published_at: datetime | None = Field(
        None,
        description="发布时间（可选，原始发布时间）",
    )
    language: str | None = Field(
        None,
        max_length=10,
        description="语言代码（可选，如 en/zh）",
    )
    credibility_level: CredibilityLevel = Field(
        default=CredibilityLevel.C,
        description="来源可信度等级（默认 C，由 source_registry 覆盖）",
    )
    source_name: str | None = Field(
        None,
        max_length=255,
        description="来源名称（可选，对应 sources 表的 name）",
    )
    content_hash: str | None = Field(
        None,
        max_length=64,
        description="内容哈希 SHA-256（可选，由校验层生成）",
    )
    metadata: DocumentMetadata = Field(
        default_factory=DocumentMetadata,
        description="额外元数据（可选，来源特有字段）",
    )

    model_config = {"from_attributes": True}

    # ── 校验器 ──

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("title 不能为空白字符串")
        return stripped

    @field_validator("content_text")
    @classmethod
    def content_must_not_be_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("content_text 不能为空白字符串")
        return stripped

    @field_validator("url")
    @classmethod
    def url_must_be_valid_if_provided(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                return None
            if not v.startswith(("http://", "https://")):
                raise ValueError(f"url 必须以 http:// 或 https:// 开头，得到: {v!r}")
        return v

    @field_validator("language")
    @classmethod
    def language_format(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip().lower()
            if len(v) > 10:
                raise ValueError(f"language 代码过长: {v!r}")
        return v

    @model_validator(mode="after")
    def podcast_requires_podcast_name(self) -> "RawDocumentInput":
        """播客文字稿建议提供 podcast_name"""
        # 仅做警告级别提示，不强制阻断
        return self

    def compute_content_hash(self) -> str:
        """计算 content_text 的 SHA-256 哈希"""
        import hashlib

        self.content_hash = hashlib.sha256(self.content_text.encode("utf-8")).hexdigest()
        return self.content_hash
