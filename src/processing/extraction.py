"""实体抽取与主题归类骨架。"""

from __future__ import annotations

import re
from collections import Counter

from src.domain.enums import EntityType
from src.processing.schemas import CleanedDocument, EntityMention, TopicAssignment


class EntityExtractor:
    """最小实体抽取器。

    使用轻量规则抽取高频专有词，重点保证输出结构稳定。
    """

    _token_pattern = re.compile(r"\b[A-Z][a-zA-Z0-9\-]{2,}\b")

    def extract(self, cleaned: CleanedDocument) -> list[EntityMention]:
        counter = Counter(self._token_pattern.findall(cleaned.normalized_text))
        entities: list[EntityMention] = []

        for name, count in counter.most_common(5):
            entity_type = self._infer_type(name)
            entities.append(
                EntityMention(
                    entity_type=entity_type,
                    name=name,
                    normalized_name=name.lower(),
                    confidence=min(0.4 + count * 0.1, 0.95),
                    evidence_text=name,
                )
            )

        return entities

    def _infer_type(self, name: str) -> EntityType:
        lowered = name.lower()
        if lowered in {"openai", "anthropic", "google", "microsoft", "meta"}:
            return EntityType.COMPANY
        if lowered in {"gpt", "claude", "gemini", "llama"}:
            return EntityType.MODEL
        return EntityType.KEYWORD


class TopicExtractor:
    """最小主题抽取器。"""

    _topic_rules: dict[str, tuple[str, tuple[str, ...]]] = {
        "agent": ("AI Agents", ("agent", "workflow", "automation")),
        "model": ("Foundation Models", ("model", "llm", "training", "inference")),
        "tooling": ("Developer Tooling", ("developer", "coding", "tool", "stack")),
        "robotics": ("Robotics", ("robot", "embodied", "control")),
        "startup": ("Startup Opportunities", ("market", "product", "customer", "startup")),
    }

    def extract(self, cleaned: CleanedDocument) -> list[TopicAssignment]:
        lowered = cleaned.normalized_text.lower()
        topics: list[TopicAssignment] = []

        for topic_key, (topic_name, keywords) in self._topic_rules.items():
            hits = sum(1 for keyword in keywords if keyword in lowered)
            if not hits:
                continue
            score = min(0.3 + hits * 0.15, 1.0)
            topics.append(
                TopicAssignment(
                    topic_key=topic_key,
                    topic_name=topic_name,
                    relevance_score=score,
                    rationale=f"命中关键词 {hits} 个",
                )
            )

        return topics
