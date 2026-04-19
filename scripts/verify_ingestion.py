"""验证采集层骨架完整性

检查：
1. 四类来源都能映射到统一 RawDocumentInput
2. 必填字段校验生效
3. 可信度等级正确传递
4. 来源注册表功能正常
5. 适配器注册表功能正常
"""

import sys
import io

# Windows 终端兼容
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from datetime import datetime, timezone

from src.ingestion.schemas import (
    RawDocumentInput,
    DocumentMetadata,
    SourceType,
    CredibilityLevel,
)
from src.ingestion.source_registry import (
    SourceRegistry,
    SourceConfig,
    FetchStrategy,
    create_default_registry,
)
from src.ingestion.adapters import (
    BlogAdapter,
    SpeechAdapter,
    InterviewAdapter,
    PodcastTranscriptAdapter,
    ManualImportAdapter,
    AdapterRegistry,
)
from src.ingestion.validators import validate_raw_document, ValidationError


def test_blog_adapter() -> None:
    """测试博客适配器"""
    config = SourceConfig(
        name="Test Blog",
        source_type=SourceType.BLOG,
        url="https://medium.com/@test",
        credibility_level=CredibilityLevel.A,
        fetch_strategy=FetchStrategy.RSS,
    )
    adapter = BlogAdapter(source_config=config)
    doc = adapter.map_to_document(
        title="The Future of AI Agents",
        content_text="AI agents are becoming more capable...",
        url="https://medium.com/@test/future-of-ai-agents",
        author="Test Author",
        language="en",
    )
    assert doc.source_type == SourceType.BLOG
    assert doc.credibility_level == CredibilityLevel.A
    assert doc.source_name == "Test Blog"
    assert doc.metadata.blog_platform == "Medium"
    print("  [PASS] BlogAdapter")


def test_speech_adapter() -> None:
    """测试演讲适配器"""
    config = SourceConfig(
        name="Test Conference",
        source_type=SourceType.SPEECH,
        credibility_level=CredibilityLevel.S,
        fetch_strategy=FetchStrategy.MANUAL,
    )
    adapter = SpeechAdapter(source_config=config)
    doc = adapter.map_to_document(
        title="Keynote: Scaling Laws",
        content_text="Today I want to talk about scaling laws...",
        author="Andrej Karpathy",
        event_name="NeurIPS 2026",
        event_location="Vancouver",
    )
    assert doc.source_type == SourceType.SPEECH
    assert doc.credibility_level == CredibilityLevel.S
    assert doc.metadata.event_name == "NeurIPS 2026"
    assert doc.metadata.event_location == "Vancouver"
    print("  [PASS] SpeechAdapter")


def test_interview_adapter() -> None:
    """测试访谈适配器"""
    config = SourceConfig(
        name="20VC",
        source_type=SourceType.INTERVIEW,
        credibility_level=CredibilityLevel.A,
        fetch_strategy=FetchStrategy.MANUAL,
    )
    adapter = InterviewAdapter(source_config=config)
    doc = adapter.map_to_document(
        title="Interview with Sam Altman",
        content_text="Q: What's next for OpenAI? A: We're focused on...",
        interviewer="Harry Stebbings",
        interviewee="Sam Altman",
    )
    assert doc.source_type == SourceType.INTERVIEW
    assert doc.author == "Sam Altman"  # interviewee 作为默认 author
    assert doc.metadata.interviewer == "Harry Stebbings"
    assert doc.metadata.interviewee == "Sam Altman"
    print("  [PASS] InterviewAdapter")


def test_podcast_adapter() -> None:
    """测试播客适配器"""
    config = SourceConfig(
        name="Dwarkesh Podcast",
        source_type=SourceType.PODCAST_TRANSCRIPT,
        credibility_level=CredibilityLevel.A,
        fetch_strategy=FetchStrategy.MANUAL,
        config={"podcast_name": "Dwarkesh Podcast"},
    )
    adapter = PodcastTranscriptAdapter(source_config=config)
    doc = adapter.map_to_document(
        title="Ep 42: The State of AI Research",
        content_text="Welcome to the podcast. Today we discuss...",
        podcast_name="Dwarkesh Podcast",
        episode_number=42,
        duration_minutes=90,
    )
    assert doc.source_type == SourceType.PODCAST_TRANSCRIPT
    assert doc.metadata.podcast_name == "Dwarkesh Podcast"
    assert doc.metadata.episode_number == 42
    assert doc.metadata.duration_minutes == 90
    print("  [PASS] PodcastTranscriptAdapter")


def test_manual_import_adapter() -> None:
    """测试手工导入适配器"""
    adapter = ManualImportAdapter()
    doc = adapter.map_to_document(
        title="My Notes on AI Safety",
        content_text="Some personal notes about AI safety...",
        language="zh",
    )
    assert doc.source_type == SourceType.MANUAL_IMPORT
    assert doc.credibility_level == CredibilityLevel.C  # 默认
    print("  [PASS] ManualImportAdapter")


def test_required_fields() -> None:
    """测试必填字段校验"""
    # 缺少 title
    try:
        RawDocumentInput(
            title="",
            source_type=SourceType.BLOG,
            content_text="some content",
        )
        assert False, "应该校验失败"
    except Exception:
        pass

    # 缺少 content_text
    try:
        RawDocumentInput(
            title="Test",
            source_type=SourceType.BLOG,
            content_text="",
        )
        assert False, "应该校验失败"
    except Exception:
        pass

    # 正常创建
    doc = RawDocumentInput(
        title="Valid Title",
        source_type=SourceType.BLOG,
        content_text="Valid content",
    )
    assert doc.title == "Valid Title"
    print("  [PASS] 必填字段校验")


def test_validator() -> None:
    """测试业务校验器"""
    doc = RawDocumentInput(
        title="Test Document",
        source_type=SourceType.BLOG,
        content_text="Some content here",
    )
    validated = validate_raw_document(doc)
    assert validated.content_hash is not None
    assert len(validated.content_hash) == 64  # SHA-256
    print("  [PASS] 业务校验器（content_hash 自动计算）")


def test_source_registry() -> None:
    """测试来源注册表"""
    registry = create_default_registry()
    assert len(registry) > 0

    # 按类型查询
    blogs = registry.list_by_type(SourceType.BLOG)
    assert len(blogs) > 0

    # 按可信度查询
    s_level = registry.list_by_credibility(CredibilityLevel.S)
    assert len(s_level) > 0

    # 启停控制
    registry.set_active("Jim Fan Public Posts", False)
    source = registry.get("Jim Fan Public Posts")
    assert source is not None
    assert source.is_active is False
    registry.set_active("Jim Fan Public Posts", True)

    # 活跃来源
    active = registry.get_active_sources()
    assert len(active) > 0

    print(f"  [PASS] SourceRegistry (共 {len(registry)} 个来源, {len(active)} 个活跃)")


def test_adapter_registry() -> None:
    """测试适配器注册表"""
    supported = AdapterRegistry.supported_types()
    assert len(supported) == 5  # blog, speech, interview, podcast_transcript, manual_import

    for st in supported:
        adapter = AdapterRegistry.get_adapter(st)
        assert adapter is not None

    print(f"  [PASS] AdapterRegistry (支持 {len(supported)} 种类型)")


def main() -> None:
    print("=" * 60)
    print("采集层骨架验证")
    print("=" * 60)

    print("\n1. 适配器测试:")
    test_blog_adapter()
    test_speech_adapter()
    test_interview_adapter()
    test_podcast_adapter()
    test_manual_import_adapter()

    print("\n2. 必填字段校验:")
    test_required_fields()

    print("\n3. 业务校验器:")
    test_validator()

    print("\n4. 来源注册表:")
    test_source_registry()

    print("\n5. 适配器注册表:")
    test_adapter_registry()

    print("\n" + "=" * 60)
    print("所有采集层测试通过!")
    print("=" * 60)


if __name__ == "__main__":
    main()
