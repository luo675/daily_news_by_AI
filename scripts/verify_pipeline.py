"""验证处理流水线骨架。

检查：
1. 清洗与去重骨架可运行
2. 双语摘要结构可生成
3. 实体抽取、主题抽取、冲突检测结构可输出
4. 产品机会评分骨架可运行
5. 日报生成骨架可消费处理结果
"""

import io
import sys
from datetime import timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from src.briefing.service import DailyBriefGenerator
from src.briefing.schemas import DailyBriefDraft
from src.ingestion.schemas import RawDocumentInput, SourceType
from src.processing.cleaning import CleaningPipeline
from src.processing.pipeline import ProcessingPipeline
from src.scoring.service import OpportunityScorer


def main() -> None:
    cleaner = CleaningPipeline()
    cleaned = cleaner.clean(
        RawDocumentInput(
            title="Messy document",
            source_type=SourceType.BLOG,
            content_text="First paragraph.\n\n\nSecond paragraph.\n\nThird paragraph.",
            language="en",
        )
    )
    assert cleaned.normalized_text == "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    assert "\n\n" in cleaned.normalized_text
    assert cleaned.removed_lines == 1

    document_with_conflict = RawDocumentInput(
        title="AI Agent tooling for startup teams",
        source_type=SourceType.BLOG,
        content_text=(
            "AI agent workflow tools help startup teams ship faster. "
            "Developers need reliable coding automation and better observability. "
            "Some operators say costs will increase, others say costs will decrease."
        ),
        language="en",
    )
    document_without_conflict = RawDocumentInput(
        title="AI Agent tooling for startup teams",
        source_type=SourceType.BLOG,
        content_text=(
            "AI agent workflow tools help startup teams ship faster. "
            "Developers need reliable coding automation and better observability. "
            "Teams want better workflow automation and product tooling."
        ),
        language="en",
    )

    pipeline = ProcessingPipeline()
    result = pipeline.process(document_with_conflict)
    result_without_conflict = pipeline.process(document_without_conflict)

    assert result.cleaned_document.normalized_title == "AI Agent tooling for startup teams"
    assert result.summary.zh
    assert result.summary.en
    assert result.topics

    scorer = OpportunityScorer()
    opportunities = scorer.score(result)
    opportunities_without_conflict = scorer.score(result_without_conflict)
    assert opportunities
    assert opportunities_without_conflict
    assert opportunities[0].score.total >= 1
    assert opportunities[0].score.priority <= opportunities_without_conflict[0].score.priority
    assert opportunities[0].uncertainty is True
    assert opportunities[0].uncertainty_reason

    generator = DailyBriefGenerator()
    brief = generator.generate([result], opportunities=opportunities, watchlist_updates=["OpenAI: 保持高优先级关注"])
    standalone_brief = DailyBriefDraft(
        summary=result.summary,
        highlights=brief.highlights,
        risks=brief.risks,
        watchlist_updates=brief.watchlist_updates,
        open_questions=brief.open_questions,
    )

    assert brief.summary.zh
    assert brief.highlights.items
    assert brief.opportunities
    assert brief.watchlist_updates.items
    assert brief.generated_at.tzinfo is not None
    assert brief.generated_at.utcoffset() == timezone.utc.utcoffset(brief.generated_at)
    assert standalone_brief.generated_at.tzinfo is not None
    assert standalone_brief.generated_at.utcoffset() == timezone.utc.utcoffset(standalone_brief.generated_at)

    print("=" * 60)
    print("处理流水线骨架验证")
    print("=" * 60)
    print("  [PASS] 清洗与去重骨架")
    print("  [PASS] 双语摘要结构")
    print("  [PASS] 实体/主题/冲突结构")
    print("  [PASS] 产品机会评分骨架")
    print("  [PASS] 日报生成骨架")
    print("=" * 60)
    print("所有处理流水线骨架验证通过!")
    print("=" * 60)


if __name__ == "__main__":
    main()
