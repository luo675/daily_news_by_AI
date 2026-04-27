"""Mappers from processing/scoring/briefing outputs into domain objects."""

from __future__ import annotations

from datetime import timezone
from uuid import UUID, uuid4

from src.application.schemas import (
    DocumentMappingBundle,
    MapperNote,
    OpportunityMappingBundle,
)
from src.briefing.schemas import DailyBriefDraft
from src.domain.models import (
    BriefType,
    DailyBrief,
    Document,
    DocumentEntity,
    DocumentStatus,
    DocumentSummary,
    Entity,
    EvidenceType,
    OpportunityAssessment,
    OpportunityEvidence,
    OpportunityStatus,
    Topic,
    DocumentTopic,
)
from src.processing.schemas import ProcessingResult
from src.scoring.schemas import OpportunityDraft


class DomainMapper:
    """Convert stage-one pipeline outputs into domain model instances."""

    def map_processing_result(
        self,
        document_id: UUID,
        result: ProcessingResult,
    ) -> DocumentMappingBundle:
        raw_document = result.cleaned_document.raw_document
        metadata = {
            "source_type": raw_document.source_type.value,
            "source_name": raw_document.source_name,
            "credibility_level": raw_document.credibility_level.value,
            "cleaning": {
                "removed_lines": result.cleaned_document.removed_lines,
                "metadata": result.cleaned_document.metadata,
            },
            "raw_metadata": raw_document.metadata.model_dump(exclude_none=True),
        }
        document = Document(
            id=document_id,
            title=result.cleaned_document.normalized_title,
            url=raw_document.url,
            author=raw_document.author,
            published_at=raw_document.published_at,
            fetched_at=raw_document.fetched_at,
            content_text=raw_document.content_text,
            language=raw_document.language,
            status=DocumentStatus.PROCESSED,
            content_hash=raw_document.content_hash or result.cleaned_document.dedup_key,
            metadata_=metadata,
        )

        summary = DocumentSummary(
            id=uuid4(),
            document_id=document_id,
            summary_zh=result.summary.zh,
            summary_en=result.summary.en,
            key_points=result.summary.bullets,
            tags=self._build_summary_tags(result),
            generated_by="auto",
        )

        entity_records: list[Entity] = []
        document_entity_records: list[DocumentEntity] = []
        entity_ids: dict[tuple[str, str], UUID] = {}
        entity_keys_by_id: dict[UUID, tuple[str, str]] = {}
        for mention in result.entities:
            entity_key = (mention.entity_type.value, mention.normalized_name)
            entity_id = entity_ids.get(entity_key)
            if entity_id is None:
                entity_id = uuid4()
                entity_ids[entity_key] = entity_id
                entity_keys_by_id[entity_id] = entity_key
                entity_records.append(
                    Entity(
                        id=entity_id,
                        entity_type=mention.entity_type.value,
                        name=mention.normalized_name,
                        aliases=self._merge_aliases(mention),
                        description=mention.evidence_text,
                    )
                )

            document_entity_records.append(
                DocumentEntity(
                    id=uuid4(),
                    document_id=document_id,
                    entity_id=entity_id,
                    relevance_score=mention.confidence,
                    context=mention.evidence_text,
                )
            )

        topic_records: list[Topic] = []
        document_topic_records: list[DocumentTopic] = []
        topic_ids: dict[str, UUID] = {}
        topic_keys_by_id: dict[UUID, str] = {}
        for assignment in result.topics:
            topic_id = topic_ids.get(assignment.topic_key)
            if topic_id is None:
                topic_id = uuid4()
                topic_ids[assignment.topic_key] = topic_id
                topic_keys_by_id[topic_id] = assignment.topic_name.strip().lower()
                topic_records.append(
                    Topic(
                        id=topic_id,
                        name_zh=assignment.topic_name,
                        name_en=assignment.topic_name,
                        description=assignment.rationale,
                    )
                )

            document_topic_records.append(
                DocumentTopic(
                    id=uuid4(),
                    document_id=document_id,
                    topic_id=topic_id,
                    relevance_score=assignment.relevance_score,
                )
            )

        notes = [
            MapperNote(
                target="document_summaries",
                field_name="tags",
                status="placeholder",
                detail="Tags are derived from topic keys and entity names until tagging logic is added.",
            ),
            MapperNote(
                target="entities",
                field_name="description",
                status="placeholder",
                detail="Entity descriptions reuse evidence_text until entity enrichment is implemented.",
            ),
            MapperNote(
                target="topics",
                field_name="name_zh",
                status="placeholder",
                detail="Chinese topic names currently mirror topic_name until bilingual topic generation exists.",
            ),
            MapperNote(
                target="topics",
                field_name="description",
                status="future_algorithm",
                detail="Topic descriptions currently reuse rationale and should come from taxonomy or clustering later.",
            ),
        ]

        return DocumentMappingBundle(
            document=document,
            summary=summary,
            entities=entity_records,
            document_entities=document_entity_records,
            topics=topic_records,
            document_topics=document_topic_records,
            entity_keys_by_id=entity_keys_by_id,
            topic_keys_by_id=topic_keys_by_id,
            notes=notes,
        )

    def map_opportunity_draft(
        self,
        document_id: UUID,
        draft: OpportunityDraft,
        source_url: str | None = None,
    ) -> OpportunityMappingBundle:
        assessment = OpportunityAssessment(
            id=uuid4(),
            title_zh=draft.title_zh,
            title_en=draft.title_en,
            description_zh=draft.summary_zh,
            description_en=draft.summary_en,
            need_realness=draft.score.need_realness,
            market_gap=draft.score.market_gap,
            feasibility=draft.score.feasibility,
            priority=draft.score.priority,
            evidence_score=draft.score.evidence,
            total_score=draft.score.total,
            uncertainty=draft.uncertainty,
            uncertainty_reason=draft.uncertainty_reason,
            status=OpportunityStatus.CANDIDATE,
        )

        evidence_items = self._build_opportunity_evidence(
            opportunity_id=assessment.id,
            document_id=document_id,
            draft=draft,
            source_url=source_url,
        )
        notes = [
            MapperNote(
                target="opportunity_assessments",
                field_name="status",
                status="placeholder",
                detail="Status defaults to candidate until review workflow and promotion logic exist.",
            ),
            MapperNote(
                target="opportunity_evidence",
                field_name="evidence_type",
                status="future_algorithm",
                detail="Evidence types are currently inferred heuristically from supporting topics/entities.",
            ),
        ]
        return OpportunityMappingBundle(
            assessment=assessment,
            evidence_items=evidence_items,
            notes=notes,
        )

    def map_daily_brief_draft(self, draft: DailyBriefDraft) -> DailyBrief:
        brief_time = draft.generated_at.astimezone(timezone.utc)
        opportunities = [self._serialize_opportunity(item) for item in draft.opportunities]
        uncertainties = [
            item.uncertainty_reason or item.title_en
            for item in draft.opportunities
            if item.uncertainty
        ]

        return DailyBrief(
            id=uuid4(),
            brief_date=brief_time,
            brief_type=BriefType.ON_DEMAND,
            content_zh=self._render_brief_markdown_zh(draft),
            content_en=self._render_brief_markdown_en(draft),
            summary_zh=draft.summary.zh,
            summary_en=draft.summary.en,
            highlights=draft.highlights.items,
            opportunities=opportunities,
            risks=draft.risks.items,
            uncertainties=uncertainties,
            watchlist_updates=draft.watchlist_updates.items,
            pending_questions=draft.open_questions.items,
            as_of_time=brief_time,
        )

    def _build_summary_tags(self, result: ProcessingResult) -> list[str]:
        topic_tags = [item.topic_key for item in result.topics]
        entity_tags = [item.normalized_name for item in result.entities[:5]]
        return list(dict.fromkeys(topic_tags + entity_tags))

    def _merge_aliases(self, mention) -> list[str]:
        values = [mention.name, mention.normalized_name, *mention.aliases]
        return list(dict.fromkeys(item for item in values if item))

    def _build_opportunity_evidence(
        self,
        opportunity_id: UUID,
        document_id: UUID,
        draft: OpportunityDraft,
        source_url: str | None,
    ) -> list[OpportunityEvidence]:
        evidence_items: list[OpportunityEvidence] = []

        for entity in draft.supporting_entities[:3]:
            evidence_items.append(
                OpportunityEvidence(
                    id=uuid4(),
                    opportunity_id=opportunity_id,
                    document_id=document_id,
                    evidence_type=(
                        EvidenceType.QUOTE if entity.evidence_text else EvidenceType.EXPERT_OPINION
                    ),
                    content=entity.evidence_text or f"Entity support: {entity.normalized_name}",
                    source_url=source_url,
                )
            )

        for topic in draft.supporting_topics[:3]:
            evidence_items.append(
                OpportunityEvidence(
                    id=uuid4(),
                    opportunity_id=opportunity_id,
                    document_id=document_id,
                    evidence_type=EvidenceType.TREND,
                    content=topic.rationale or f"Topic support: {topic.topic_name}",
                    source_url=source_url,
                )
            )

        if not evidence_items:
            evidence_items.append(
                OpportunityEvidence(
                    id=uuid4(),
                    opportunity_id=opportunity_id,
                    document_id=document_id,
                    evidence_type=EvidenceType.TREND,
                    content=draft.summary_en,
                    source_url=source_url,
                )
            )

        return evidence_items

    def _serialize_opportunity(self, draft: OpportunityDraft) -> dict[str, object]:
        return {
            "title_zh": draft.title_zh,
            "title_en": draft.title_en,
            "summary_zh": draft.summary_zh,
            "summary_en": draft.summary_en,
            "score": draft.score.model_dump(),
            "uncertainty": draft.uncertainty,
            "uncertainty_reason": draft.uncertainty_reason,
        }

    def _render_brief_markdown_zh(self, draft: DailyBriefDraft) -> str:
        return "\n".join(
            [
                "# 每日简报",
                "",
                "## 摘要",
                draft.summary.zh,
                "",
                f"## {draft.highlights.title}",
                *[f"- {item}" for item in draft.highlights.items],
                "",
                f"## {draft.risks.title}",
                *[f"- {item}" for item in draft.risks.items],
                "",
                f"## {draft.watchlist_updates.title}",
                *[f"- {item}" for item in draft.watchlist_updates.items],
                "",
                f"## {draft.open_questions.title}",
                *[f"- {item}" for item in draft.open_questions.items],
            ]
        )

    def _render_brief_markdown_en(self, draft: DailyBriefDraft) -> str:
        opportunity_lines = [
            f"- {item.title_en}: {item.score.total}"
            for item in draft.opportunities
        ] or ["- No scored opportunities."]
        return "\n".join(
            [
                "# Daily Brief",
                "",
                "## Summary",
                draft.summary.en,
                "",
                "## Highlights",
                *[f"- {item}" for item in draft.highlights.items],
                "",
                "## Opportunities",
                *opportunity_lines,
                "",
                "## Risks",
                *[f"- {item}" for item in draft.risks.items],
                "",
                "## Open Questions",
                *[f"- {item}" for item in draft.open_questions.items],
            ]
        )
