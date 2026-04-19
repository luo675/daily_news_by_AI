"""日报输出结构。"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from src.processing.schemas import BilingualSummary
from src.scoring.schemas import OpportunityDraft


class BriefSection(BaseModel):
    """日报章节。"""

    title: str = Field(..., description="章节标题")
    items: list[str] = Field(default_factory=list, description="章节条目")


class DailyBriefDraft(BaseModel):
    """日报草稿结构。"""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    summary: BilingualSummary
    highlights: BriefSection
    opportunities: list[OpportunityDraft] = Field(default_factory=list)
    risks: BriefSection
    watchlist_updates: BriefSection
    open_questions: BriefSection
