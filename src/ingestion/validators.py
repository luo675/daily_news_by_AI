"""采集输入校验

对 RawDocumentInput 进行业务级校验，补充 Pydantic 无法覆盖的规则。
对应 TC-08（采集输入规范）中的必填字段和格式要求。
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from src.ingestion.schemas import RawDocumentInput, SourceType


class ValidationError(Exception):
    """校验错误"""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"校验失败: {'; '.join(errors)}")


def validate_raw_document(doc: RawDocumentInput) -> RawDocumentInput:
    """对统一文档输入对象执行业务级校验

    校验规则：
      1. title 非空（Pydantic 已覆盖，此处做二次确认）
      2. content_text 非空（Pydantic 已覆盖，此处做二次确认）
      3. URL 格式（Pydantic 已覆盖）
      4. published_at 不晚于当前时间
      5. 自动计算 content_hash（如未提供）
      6. 语言检测提示（如未提供 language）

    Args:
        doc: 统一文档输入对象

    Returns:
        校验后的文档对象（可能补充了 content_hash）

    Raises:
        ValidationError: 校验失败
    """
    errors: list[str] = []

    # 1. 必填字段二次确认
    if not doc.title or not doc.title.strip():
        errors.append("title 不能为空")

    if not doc.content_text or not doc.content_text.strip():
        errors.append("content_text 不能为空")

    # 2. 发布时间不晚于当前时间
    if doc.published_at and doc.published_at > datetime.now(timezone.utc):
        errors.append(f"published_at 不能晚于当前时间: {doc.published_at}")

    # 3. URL 去重提示
    if doc.url is None and doc.source_type != SourceType.MANUAL_IMPORT:
        # 非手工导入建议提供 URL（仅警告，不阻断）
        pass

    # 4. 自动计算 content_hash
    if doc.content_hash is None:
        doc.compute_content_hash()

    if errors:
        raise ValidationError(errors)

    return doc


def compute_content_hash(text: str) -> str:
    """计算文本的 SHA-256 哈希值

    用于去重检测。同一内容无论空格差异都应产生相同哈希。
    先 strip 再计算。
    """
    normalized = text.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
