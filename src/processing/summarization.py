"""双语摘要骨架。"""

from __future__ import annotations

import re

from src.processing.schemas import BilingualSummary, CleanedDocument


class SummaryBuilder:
    """摘要生成器。

    当前使用轻量规则生成占位摘要，保证结构稳定可消费。
    """

    _sentence_pattern = re.compile(r"(?<=[.!?。！？])\s+")

    def build(self, cleaned: CleanedDocument) -> BilingualSummary:
        sentences = [
            part.strip()
            for part in self._sentence_pattern.split(cleaned.normalized_text)
            if part.strip()
        ]
        lead = sentences[0] if sentences else cleaned.normalized_text[:160]
        bullets = sentences[:3] if sentences else [cleaned.normalized_text[:80]]

        return BilingualSummary(
            zh=f"摘要骨架：{cleaned.normalized_title}。{lead[:120]}",
            en=f"Summary skeleton: {cleaned.normalized_title}. {lead[:160]}",
            bullets=bullets,
        )
