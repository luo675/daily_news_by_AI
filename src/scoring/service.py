"""产品机会评分骨架实现。"""

from __future__ import annotations

from src.processing.schemas import ProcessingResult
from src.scoring.schemas import OpportunityDraft, OpportunityScoreCard, ScoringWeights


class OpportunityScorer:
    """最小机会评分器。"""

    def __init__(self, weights: ScoringWeights | None = None) -> None:
        self.weights = weights or ScoringWeights()

    def score(self, result: ProcessingResult) -> list[OpportunityDraft]:
        """根据处理结果生成机会候选项。"""
        if not result.topics:
            return []

        topic = max(result.topics, key=lambda item: item.relevance_score)
        need_realness = self._clamp(5 + int(topic.relevance_score * 4))
        market_gap = self._clamp(6 if "startup" in topic.topic_key or "tool" in topic.topic_key else 5)
        feasibility = self._clamp(6 if result.entities else 5)
        base_priority = 6
        priority = self._clamp(base_priority - 1 if result.conflicts else base_priority)
        evidence = self._clamp(min(4 + len(result.summary.bullets), 10))

        total = round(
            need_realness * self.weights.need_realness
            + market_gap * self.weights.market_gap
            + feasibility * self.weights.feasibility
            + priority * self.weights.priority
            + evidence * self.weights.evidence,
            2,
        )

        score = OpportunityScoreCard(
            need_realness=need_realness,
            market_gap=market_gap,
            feasibility=feasibility,
            priority=priority,
            evidence=evidence,
            total=total,
        )

        return [
            OpportunityDraft(
                title_zh=f"{topic.topic_name} 方向机会",
                title_en=f"Opportunity in {topic.topic_name}",
                summary_zh=f"基于当前文档，{topic.topic_name} 相关需求值得继续跟踪。",
                summary_en=f"The current document suggests a follow-up opportunity in {topic.topic_name}.",
                score=score,
                supporting_topics=result.topics,
                supporting_entities=result.entities,
                uncertainty=bool(result.conflicts),
                uncertainty_reason="检测到潜在冲突信号" if result.conflicts else None,
            )
        ]

    def _clamp(self, value: int) -> int:
        return max(1, min(10, value))
