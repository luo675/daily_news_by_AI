"""来源适配器

将不同来源类型的原始数据映射到统一 RawDocumentInput。
对应 TC-08（采集输入规范）。

设计原则：
  - 每种来源类型一个适配器
  - 适配器只做字段映射和基础标准化，不做复杂清洗
  - 后续实现真实抓取时，只需在适配器内替换数据获取逻辑
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from src.ingestion.schemas import (
    CredibilityLevel,
    DocumentMetadata,
    RawDocumentInput,
    SourceType,
)
from src.ingestion.source_registry import SourceConfig


class BaseSourceAdapter(ABC):
    """来源适配器基类

    定义从来源特定数据到统一 RawDocumentInput 的映射接口。
    子类需实现 map_to_document 方法。
    """

    source_type: SourceType

    def __init__(self, source_config: SourceConfig | None = None) -> None:
        self.source_config = source_config

    @abstractmethod
    def map_to_document(
        self,
        *,
        title: str,
        content_text: str,
        url: str | None = None,
        author: str | None = None,
        published_at: datetime | None = None,
        language: str | None = None,
        fetched_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RawDocumentInput:
        """将来源特定数据映射到统一文档输入对象

        Args:
            title: 文档标题（必填）
            content_text: 正文文本（必填）
            url: 原文链接
            author: 作者
            published_at: 发布时间
            language: 语言代码
            fetched_at: 采集时间
            metadata: 来源特有元数据

        Returns:
            RawDocumentInput 统一文档输入对象
        """
        ...

    def _build_base_document(
        self,
        *,
        title: str,
        content_text: str,
        url: str | None = None,
        author: str | None = None,
        published_at: datetime | None = None,
        language: str | None = None,
        fetched_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RawDocumentInput:
        """构建基础文档对象，子类可在此基础上添加特有字段"""
        doc_metadata = DocumentMetadata(**(metadata or {}))

        # 从 source_config 获取可信度和来源名称
        credibility = CredibilityLevel.C
        source_name = None
        if self.source_config:
            credibility = self.source_config.credibility_level
            source_name = self.source_config.name

        return RawDocumentInput(
            title=title,
            source_type=self.source_type,
            content_text=content_text,
            url=url,
            author=author,
            published_at=published_at,
            language=language,
            fetched_at=fetched_at or datetime.now(timezone.utc),
            credibility_level=credibility,
            source_name=source_name,
            metadata=doc_metadata,
        )


class BlogAdapter(BaseSourceAdapter):
    """博客适配器

    映射博客文章到统一文档输入。
    特有字段：blog_platform
    """

    source_type = SourceType.BLOG

    def map_to_document(
        self,
        *,
        title: str,
        content_text: str,
        url: str | None = None,
        author: str | None = None,
        published_at: datetime | None = None,
        language: str | None = None,
        fetched_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RawDocumentInput:
        meta = metadata or {}
        # 博客特有：标记平台
        if "blog_platform" not in meta and self.source_config and self.source_config.url:
            # 尝试从 URL 推断平台
            meta["blog_platform"] = self._infer_platform(self.source_config.url)

        return self._build_base_document(
            title=title,
            content_text=content_text,
            url=url,
            author=author,
            published_at=published_at,
            language=language,
            fetched_at=fetched_at,
            metadata=meta,
        )

    @staticmethod
    def _infer_platform(url: str) -> str:
        """从 URL 推断博客平台"""
        url_lower = url.lower()
        if "medium.com" in url_lower:
            return "Medium"
        if "substack.com" in url_lower:
            return "Substack"
        if "bearblog" in url_lower:
            return "Bear Blog"
        if "ghost.org" in url_lower or "ghost.io" in url_lower:
            return "Ghost"
        if "wordpress" in url_lower:
            return "WordPress"
        return "personal_site"


class SpeechAdapter(BaseSourceAdapter):
    """演讲适配器

    映射演讲文字稿到统一文档输入。
    特有字段：event_name, event_location
    """

    source_type = SourceType.SPEECH

    def map_to_document(
        self,
        *,
        title: str,
        content_text: str,
        url: str | None = None,
        author: str | None = None,
        published_at: datetime | None = None,
        language: str | None = None,
        fetched_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        event_name: str | None = None,
        event_location: str | None = None,
    ) -> RawDocumentInput:
        meta = metadata or {}
        if event_name:
            meta["event_name"] = event_name
        if event_location:
            meta["event_location"] = event_location

        return self._build_base_document(
            title=title,
            content_text=content_text,
            url=url,
            author=author,
            published_at=published_at,
            language=language,
            fetched_at=fetched_at,
            metadata=meta,
        )


class InterviewAdapter(BaseSourceAdapter):
    """访谈适配器

    映射访谈文字稿到统一文档输入。
    特有字段：interviewer, interviewee
    """

    source_type = SourceType.INTERVIEW

    def map_to_document(
        self,
        *,
        title: str,
        content_text: str,
        url: str | None = None,
        author: str | None = None,
        published_at: datetime | None = None,
        language: str | None = None,
        fetched_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        interviewer: str | None = None,
        interviewee: str | None = None,
    ) -> RawDocumentInput:
        meta = metadata or {}
        if interviewer:
            meta["interviewer"] = interviewer
        if interviewee:
            meta["interviewee"] = interviewee

        # 访谈的 author 默认为 interviewee
        effective_author = author or interviewee

        return self._build_base_document(
            title=title,
            content_text=content_text,
            url=url,
            author=effective_author,
            published_at=published_at,
            language=language,
            fetched_at=fetched_at,
            metadata=meta,
        )


class PodcastTranscriptAdapter(BaseSourceAdapter):
    """播客文字稿适配器

    映射播客文字稿到统一文档输入。
    特有字段：podcast_name, episode_number, duration_minutes
    """

    source_type = SourceType.PODCAST_TRANSCRIPT

    def map_to_document(
        self,
        *,
        title: str,
        content_text: str,
        url: str | None = None,
        author: str | None = None,
        published_at: datetime | None = None,
        language: str | None = None,
        fetched_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        podcast_name: str | None = None,
        episode_number: str | int | None = None,
        duration_minutes: int | None = None,
    ) -> RawDocumentInput:
        meta = metadata or {}
        # 优先使用参数，其次从 source_config 获取
        if podcast_name:
            meta["podcast_name"] = podcast_name
        elif self.source_config and self.source_config.config:
            meta["podcast_name"] = self.source_config.config.get("podcast_name")
        if episode_number:
            meta["episode_number"] = episode_number
        if duration_minutes:
            meta["duration_minutes"] = duration_minutes

        return self._build_base_document(
            title=title,
            content_text=content_text,
            url=url,
            author=author,
            published_at=published_at,
            language=language,
            fetched_at=fetched_at,
            metadata=meta,
        )


class ManualImportAdapter(BaseSourceAdapter):
    """手工导入适配器

    映射手工导入内容到统一文档输入。
    无特有字段，所有元数据通过 metadata 传入。
    """

    source_type = SourceType.MANUAL_IMPORT

    def map_to_document(
        self,
        *,
        title: str,
        content_text: str,
        url: str | None = None,
        author: str | None = None,
        published_at: datetime | None = None,
        language: str | None = None,
        fetched_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RawDocumentInput:
        return self._build_base_document(
            title=title,
            content_text=content_text,
            url=url,
            author=author,
            published_at=published_at,
            language=language,
            fetched_at=fetched_at,
            metadata=metadata,
        )


class AdapterRegistry:
    """适配器注册表

    根据来源类型查找对应的适配器实例。
    """

    _adapters: dict[SourceType, type[BaseSourceAdapter]] = {
        SourceType.BLOG: BlogAdapter,
        SourceType.SPEECH: SpeechAdapter,
        SourceType.INTERVIEW: InterviewAdapter,
        SourceType.PODCAST_TRANSCRIPT: PodcastTranscriptAdapter,
        SourceType.MANUAL_IMPORT: ManualImportAdapter,
    }

    @classmethod
    def get_adapter(
        cls, source_type: SourceType, source_config: SourceConfig | None = None
    ) -> BaseSourceAdapter:
        """获取指定类型的适配器实例"""
        adapter_cls = cls._adapters.get(source_type)
        if adapter_cls is None:
            raise ValueError(f"未注册的来源类型: {source_type}")
        return adapter_cls(source_config=source_config)

    @classmethod
    def register_adapter(cls, source_type: SourceType, adapter_cls: type[BaseSourceAdapter]) -> None:
        """注册自定义适配器"""
        cls._adapters[source_type] = adapter_cls

    @classmethod
    def supported_types(cls) -> list[SourceType]:
        """返回所有已注册的来源类型"""
        return list(cls._adapters.keys())
