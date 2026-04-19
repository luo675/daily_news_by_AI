"""数据采集层

提供来源注册、统一输入 Schema、来源适配器和基础校验。
对应 TC-02（来源分类规则）、TC-03（可信度规则）、TC-08（采集输入规范）。
"""

from src.ingestion.schemas import RawDocumentInput, DocumentMetadata
from src.ingestion.source_registry import SourceRegistry, SourceConfig
from src.ingestion.adapters import (
    BaseSourceAdapter,
    BlogAdapter,
    SpeechAdapter,
    InterviewAdapter,
    PodcastTranscriptAdapter,
    ManualImportAdapter,
    AdapterRegistry,
)
from src.ingestion.validators import validate_raw_document

__all__ = [
    "RawDocumentInput",
    "DocumentMetadata",
    "SourceRegistry",
    "SourceConfig",
    "BaseSourceAdapter",
    "BlogAdapter",
    "SpeechAdapter",
    "InterviewAdapter",
    "PodcastTranscriptAdapter",
    "ManualImportAdapter",
    "AdapterRegistry",
    "validate_raw_document",
]
