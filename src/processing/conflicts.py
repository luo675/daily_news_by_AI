"""冲突检测骨架。"""

from __future__ import annotations

from src.processing.schemas import ConflictRecord, ConflictSignal, ProcessingResult


class ConflictDetector:
    """最小冲突检测器。

    当前仅检测显式的矛盾信号词，输出结构先稳定下来。
    """

    _pairs = (
        ("increase", "decrease", "factual"),
        ("will", "won't", "opinion"),
        ("before", "after", "temporal"),
    )

    def detect(self, result: ProcessingResult) -> list[ConflictRecord]:
        text = result.cleaned_document.normalized_text.lower()
        conflicts: list[ConflictRecord] = []

        for positive, negative, conflict_type in self._pairs:
            if positive in text and negative in text:
                conflicts.append(
                    ConflictRecord(
                        conflict_type=conflict_type,
                        resolution_status="unresolved",
                        summary=f"检测到可能的{conflict_type}冲突：同时出现 {positive!r} 与 {negative!r}",
                        uncertainty=True,
                        signals=[
                            ConflictSignal(
                                signal_type="keyword_pair",
                                description=f"同时命中 {positive}/{negative}",
                                evidence_text=f"{positive} / {negative}",
                            )
                        ],
                    )
                )

        return conflicts
