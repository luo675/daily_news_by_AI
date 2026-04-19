"""共享领域枚举。

集中定义跨模块复用的枚举，避免 Schema 层和 ORM 层发生漂移。
"""

from __future__ import annotations

from enum import StrEnum


class SourceType(StrEnum):
    BLOG = "blog"
    SPEECH = "speech"
    INTERVIEW = "interview"
    PODCAST_TRANSCRIPT = "podcast_transcript"
    MANUAL_IMPORT = "manual_import"


class CredibilityLevel(StrEnum):
    S = "S"
    A = "A"
    B = "B"
    C = "C"


class EntityType(StrEnum):
    PERSON = "person"
    COMPANY = "company"
    PRODUCT = "product"
    MODEL = "model"
    TOPIC = "topic"
    TRACK = "track"
    KEYWORD = "keyword"


class WatchlistStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    REMOVED = "removed"


class PriorityLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReviewTargetType(StrEnum):
    SUMMARY = "summary"
    TAGS = "tags"
    OPPORTUNITY_SCORE = "opportunity_score"
    CONCLUSION = "conclusion"
    PRIORITY = "priority"
    TOPIC = "topic"
    UNCERTAINTY = "uncertainty"
    RISK = "risk"
