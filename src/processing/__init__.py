"""处理流水线骨架。

提供清洗去重、双语摘要、实体抽取、主题抽取、冲突检测的最小可运行实现。
当前阶段只定义清晰的输入输出结构和模块边界，不追求完整算法。
"""

from src.processing.cleaning import CleaningPipeline
from src.processing.conflicts import ConflictDetector
from src.processing.extraction import EntityExtractor, TopicExtractor
from src.processing.pipeline import ProcessingPipeline
from src.processing.schemas import (
    BilingualSummary,
    CleanedDocument,
    ConflictRecord,
    ConflictSignal,
    EntityMention,
    ProcessingResult,
    TopicAssignment,
)
from src.processing.summarization import SummaryBuilder

__all__ = [
    "BilingualSummary",
    "CleanedDocument",
    "ConflictRecord",
    "ConflictSignal",
    "EntityMention",
    "TopicAssignment",
    "ProcessingResult",
    "CleaningPipeline",
    "SummaryBuilder",
    "EntityExtractor",
    "TopicExtractor",
    "ConflictDetector",
    "ProcessingPipeline",
]
