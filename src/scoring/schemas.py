"""产品机会评分结构。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.processing.schemas import EntityMention, TopicAssignment


class ScoringWeights(BaseModel):
    """默认权重。"""

    need_realness: float = Field(default=0.30)
    market_gap: float = Field(default=0.30)
    feasibility: float = Field(default=0.20)
    priority: float = Field(default=0.10)
    evidence: float = Field(default=0.10)


class OpportunityScoreCard(BaseModel):
    """机会评分卡。"""

    need_realness: int = Field(..., ge=1, le=10)
    market_gap: int = Field(..., ge=1, le=10)
    feasibility: int = Field(..., ge=1, le=10)
    priority: int = Field(..., ge=1, le=10)
    evidence: int = Field(..., ge=1, le=10)
    total: float = Field(..., ge=1.0, le=10.0)


class OpportunityDraft(BaseModel):
    """机会输出骨架。"""

    title_zh: str = Field(..., description="中文标题")
    title_en: str = Field(..., description="英文标题")
    summary_zh: str = Field(..., description="中文说明")
    summary_en: str = Field(..., description="英文说明")
    score: OpportunityScoreCard
    supporting_topics: list[TopicAssignment] = Field(default_factory=list)
    supporting_entities: list[EntityMention] = Field(default_factory=list)
    uncertainty: bool = Field(default=False)
    uncertainty_reason: str | None = Field(None)
