"""API 层

面向通用 AI Agent 的结构化 API。
对应 TC-17（检索接口）、TC-18（统一返回）、TC-19（鉴权与配额）。
"""

from src.api.app import create_app
from src.api.schemas import (
    BilingualText,
    UnifiedResponse,
    ErrorResponse,
    MetaInfo,
    OpportunityScore,
    EvidenceItem,
    WatchlistUpdate,
)

__all__ = [
    "create_app",
    "BilingualText",
    "UnifiedResponse",
    "ErrorResponse",
    "MetaInfo",
    "OpportunityScore",
    "EvidenceItem",
    "WatchlistUpdate",
]
