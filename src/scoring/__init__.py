"""产品机会评分骨架。"""

from src.scoring.schemas import OpportunityDraft, OpportunityScoreCard, ScoringWeights
from src.scoring.service import OpportunityScorer

__all__ = [
    "OpportunityDraft",
    "OpportunityScoreCard",
    "ScoringWeights",
    "OpportunityScorer",
]
