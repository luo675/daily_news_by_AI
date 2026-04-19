"""日报生成骨架实现。"""

from __future__ import annotations

from src.briefing.schemas import BriefSection, DailyBriefDraft
from src.processing.schemas import BilingualSummary, ProcessingResult
from src.scoring.schemas import OpportunityDraft


class DailyBriefGenerator:
    """最小日报生成器。"""

    def generate(
        self,
        results: list[ProcessingResult],
        opportunities: list[OpportunityDraft] | None = None,
        watchlist_updates: list[str] | None = None,
    ) -> DailyBriefDraft:
        """生成日报骨架。"""
        opportunities = opportunities or []
        watchlist_updates = watchlist_updates or []

        lead = results[0].summary if results else BilingualSummary(zh="今日暂无新增内容。", en="No new content today.")
        highlights = [
            result.cleaned_document.normalized_title
            for result in results[:5]
        ] or ["今日无明显新增重点"]
        risks = [
            conflict.summary
            for result in results
            for conflict in result.conflicts
        ] or ["当前未检测到明确冲突风险"]
        open_questions = [
            "需要人工复核机会评分是否合理"
            if opportunities
            else "需要补充更多内容后再生成机会判断"
        ]

        return DailyBriefDraft(
            summary=lead,
            highlights=BriefSection(title="今日重点", items=highlights),
            opportunities=opportunities,
            risks=BriefSection(title="风险与争议", items=risks),
            watchlist_updates=BriefSection(
                title="关注对象更新",
                items=watchlist_updates or ["暂无 watchlist 更新"],
            ),
            open_questions=BriefSection(title="待验证问题", items=open_questions),
        )
