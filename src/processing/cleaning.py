"""清洗与去重骨架。"""

from __future__ import annotations

import re

from src.ingestion.schemas import RawDocumentInput
from src.ingestion.validators import compute_content_hash
from src.processing.schemas import CleanedDocument


class CleaningPipeline:
    """文档清洗器。

    当前只提供最小实现：
    - 去除首尾空白
    - 折叠连续空行
    - 统一标题与正文中的多余空白
    - 生成稳定去重键
    """

    _blank_line_pattern = re.compile(r"\n\s*\n+", re.MULTILINE)
    _inline_space_pattern = re.compile(r"[ \t]+")

    def clean(self, document: RawDocumentInput) -> CleanedDocument:
        """执行清洗。"""
        original = document.content_text.strip()
        normalized_text, removed_lines = self._normalize_text(original)
        normalized_title = self._normalize_inline_text(document.title)

        dedup_source = f"{normalized_title}\n{normalized_text}"
        dedup_key = compute_content_hash(dedup_source)

        return CleanedDocument(
            raw_document=document,
            normalized_text=normalized_text,
            normalized_title=normalized_title,
            dedup_key=dedup_key,
            removed_lines=removed_lines,
            metadata={
                "language": document.language,
                "source_type": document.source_type.value,
            },
        )

    def _normalize_text(self, text: str) -> tuple[str, int]:
        normalized_lines: list[str] = []
        consecutive_blank_lines = 0
        removed_lines = 0

        for raw_line in text.splitlines():
            normalized_line = self._normalize_inline_text(raw_line)
            if normalized_line:
                normalized_lines.append(normalized_line)
                consecutive_blank_lines = 0
                continue

            consecutive_blank_lines += 1
            if consecutive_blank_lines == 1:
                normalized_lines.append("")
            else:
                removed_lines += 1

        normalized_text = "\n".join(normalized_lines).strip()
        normalized_text = self._blank_line_pattern.sub("\n\n", normalized_text)
        return normalized_text, removed_lines

    def _normalize_inline_text(self, text: str) -> str:
        return self._inline_space_pattern.sub(" ", text).strip()
