"""来源注册表

管理来源配置：类型、可信度、采集策略、启停状态。
对应 TC-02（来源分类规则）和 TC-03（来源可信度规则）。

设计原则：
  - 第一阶段使用内存注册表 + YAML 配置文件
  - 后续可切换到数据库驱动（sources 表）
  - 可信度等级判断依据文档化在代码注释中
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from src.ingestion.schemas import CredibilityLevel, SourceType


# ──────────────────────────── 可信度判断依据 ────────────────────────────
#
# S 级：一手来源，原始创作者或核心参与者直接产出
#        例：Andrej Karpathy 个人博客、OpenAI 官方博客
# A 级：高质量二次整理，专业机构或资深从业者产出
#        例：a16z Podcast、Dwarkesh Podcast、Ethan Mollick 博客
# B 级：一般性报道或转载，有编辑加工但非一手
#        例：TechCrunch 新闻报道、行业媒体综述
# C 级：未经验证或低可信度来源
#        例：匿名论坛帖子、未标注出处的转载
# ────────────────────────────────────────────────────────────────────────


class FetchStrategy(StrEnum):
    """采集策略"""

    RSS = "rss"
    API = "api"
    SCRAPE = "scrape"
    MANUAL = "manual"


class SourceConfig(BaseModel):
    """单个来源的配置

    对应 sources 表的字段，但作为配置层独立于数据库模型。
    """

    name: str = Field(..., min_length=1, description="来源名称")
    source_type: SourceType = Field(..., description="来源类型")
    url: str | None = Field(None, description="来源 URL")
    credibility_level: CredibilityLevel = Field(
        default=CredibilityLevel.C, description="可信度等级"
    )
    is_active: bool = Field(default=True, description="是否启用")
    fetch_strategy: FetchStrategy = Field(
        default=FetchStrategy.MANUAL, description="采集策略"
    )
    config: dict[str, Any] | None = Field(
        None, description="来源专属配置（RSS 地址、抓取规则等）"
    )

    model_config = {"extra": "allow"}


class SourceRegistry:
    """来源注册表

    管理所有已注册的来源配置。支持：
      - 从 YAML 文件批量加载
      - 按名称/类型/可信度查询
      - 启停控制
    """

    def __init__(self) -> None:
        self._sources: dict[str, SourceConfig] = {}

    def register(self, source: SourceConfig) -> None:
        """注册一个来源"""
        self._sources[source.name] = source

    def unregister(self, name: str) -> None:
        """移除一个来源"""
        self._sources.pop(name, None)

    def get(self, name: str) -> SourceConfig | None:
        """按名称获取来源配置"""
        return self._sources.get(name)

    def get_active_sources(self) -> list[SourceConfig]:
        """获取所有启用的来源"""
        return [s for s in self._sources.values() if s.is_active]

    def list_by_type(self, source_type: SourceType) -> list[SourceConfig]:
        """按类型筛选来源"""
        return [s for s in self._sources.values() if s.source_type == source_type]

    def list_by_credibility(self, level: CredibilityLevel) -> list[SourceConfig]:
        """按可信度等级筛选来源"""
        return [s for s in self._sources.values() if s.credibility_level == level]

    def set_active(self, name: str, active: bool) -> None:
        """设置来源启停状态"""
        source = self._sources.get(name)
        if source:
            source.is_active = active

    def all_sources(self) -> list[SourceConfig]:
        """获取所有来源"""
        return list(self._sources.values())

    def load_from_yaml(self, path: str | Path) -> None:
        """从 YAML 文件批量加载来源配置

        YAML 格式示例：
        ```yaml
        sources:
          - name: "Andrej Karpathy Blog"
            source_type: blog
            url: "https://karpathy.bearblog.dev"
            credibility_level: S
            fetch_strategy: rss
            config:
              rss_url: "https://karpathy.bearblog.dev/feed.xml"
        ```
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"来源配置文件不存在: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "sources" not in data:
            raise ValueError(f"YAML 文件缺少 'sources' 键: {path}")

        for item in data["sources"]:
            source = SourceConfig(**item)
            self.register(source)

    def __len__(self) -> int:
        return len(self._sources)

    def __repr__(self) -> str:
        return f"<SourceRegistry count={len(self._sources)}>"


def create_default_registry() -> SourceRegistry:
    """创建包含 P0 来源样板的默认注册表

    基于 project_overview.md 中推荐的 P0 来源。
    """
    registry = SourceRegistry()

    # ── S 级：一手来源 ──
    registry.register(SourceConfig(
        name="Andrej Karpathy Blog",
        source_type=SourceType.BLOG,
        url="https://karpathy.bearblog.dev",
        credibility_level=CredibilityLevel.S,
        fetch_strategy=FetchStrategy.RSS,
        config={"rss_url": "https://karpathy.bearblog.dev/feed.xml"},
    ))
    registry.register(SourceConfig(
        name="Jim Fan Public Posts",
        source_type=SourceType.BLOG,
        url="https://x.com/DrJimFan",
        credibility_level=CredibilityLevel.S,
        fetch_strategy=FetchStrategy.MANUAL,
    ))

    # ── A 级：高质量二次整理 ──
    registry.register(SourceConfig(
        name="Dwarkesh Podcast",
        source_type=SourceType.PODCAST_TRANSCRIPT,
        url="https://www.dwarkeshpatel.com",
        credibility_level=CredibilityLevel.A,
        fetch_strategy=FetchStrategy.MANUAL,
        config={"podcast_name": "Dwarkesh Podcast"},
    ))
    registry.register(SourceConfig(
        name="a16z Podcast",
        source_type=SourceType.PODCAST_TRANSCRIPT,
        url="https://a16z.com/podcasts",
        credibility_level=CredibilityLevel.A,
        fetch_strategy=FetchStrategy.MANUAL,
        config={"podcast_name": "a16z Podcast"},
    ))
    registry.register(SourceConfig(
        name="Ethan Mollick Blog",
        source_type=SourceType.BLOG,
        url="https://www.oneusefulthing.org",
        credibility_level=CredibilityLevel.A,
        fetch_strategy=FetchStrategy.RSS,
        config={"rss_url": "https://www.oneusefulthing.org/feed"},
    ))
    registry.register(SourceConfig(
        name="20VC",
        source_type=SourceType.INTERVIEW,
        url="https://www.20vc.com",
        credibility_level=CredibilityLevel.A,
        fetch_strategy=FetchStrategy.MANUAL,
    ))
    registry.register(SourceConfig(
        name="The Robot Brains Podcast",
        source_type=SourceType.PODCAST_TRANSCRIPT,
        url="https://www.therobotbrains.ai",
        credibility_level=CredibilityLevel.A,
        fetch_strategy=FetchStrategy.MANUAL,
        config={"podcast_name": "The Robot Brains Podcast"},
    ))

    # ── B 级：一般性报道 ──
    registry.register(SourceConfig(
        name="All-In Podcast",
        source_type=SourceType.PODCAST_TRANSCRIPT,
        url="https://www.allinpodcast.co",
        credibility_level=CredibilityLevel.B,
        fetch_strategy=FetchStrategy.MANUAL,
        config={"podcast_name": "All-In Podcast"},
    ))
    registry.register(SourceConfig(
        name="TechCrunch Equity Podcast",
        source_type=SourceType.PODCAST_TRANSCRIPT,
        url="https://techcrunch.com/category/podcasts/equity",
        credibility_level=CredibilityLevel.B,
        fetch_strategy=FetchStrategy.MANUAL,
        config={"podcast_name": "TechCrunch Equity Podcast"},
    ))
    registry.register(SourceConfig(
        name="Interplay VC Podcast",
        source_type=SourceType.PODCAST_TRANSCRIPT,
        url="https://www.interplay.vc/podcast",
        credibility_level=CredibilityLevel.B,
        fetch_strategy=FetchStrategy.MANUAL,
        config={"podcast_name": "Interplay VC Podcast"},
    ))
    registry.register(SourceConfig(
        name="TBPN",
        source_type=SourceType.PODCAST_TRANSCRIPT,
        url="https://tbpn.xyz",
        credibility_level=CredibilityLevel.B,
        fetch_strategy=FetchStrategy.MANUAL,
        config={"podcast_name": "TBPN"},
    ))

    return registry
