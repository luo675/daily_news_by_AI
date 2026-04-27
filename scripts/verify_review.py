from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from src.admin.review_schemas import OverrideStatus, ReviewHistoryResponse
from src.domain.models import DailyBrief, Document, OpportunityAssessment, ReviewEdit
from src.web import service as web_service_module
from src.web.service import WebMvpService


class FakeScalarResult:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def unique(self) -> "FakeScalarResult":
        return self

    def __iter__(self):
        return iter(self._items)


class FakeReadSession:
    def __init__(self, opportunities: list[OpportunityAssessment] | None = None, briefs: list[DailyBrief] | None = None) -> None:
        self._opportunities = opportunities
        self._briefs = briefs or []

    def scalars(self, stmt) -> FakeScalarResult:
        items = self._opportunities if self._opportunities is not None else self._briefs
        return FakeScalarResult(items)

    def close(self) -> None:
        return None


class FakeWriteSession:
    def __init__(self, opportunity: OpportunityAssessment | None = None, brief: DailyBrief | None = None) -> None:
        self._opportunity = opportunity
        self._brief = brief
        self.rolled_back = False

    def get(self, model, object_id):
        if self._opportunity is not None and object_id == self._opportunity.id:
            return self._opportunity
        if self._brief is not None and object_id == self._brief.id:
            return self._brief
        return None

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        return None


def build_opportunity() -> OpportunityAssessment:
    opportunity = OpportunityAssessment(
        id=uuid.uuid4(),
        title_zh="自动机会标题",
        title_en="Auto opportunity title",
        description_zh="自动说明",
        description_en="Auto summary",
        need_realness=4,
        market_gap=5,
        feasibility=6,
        priority=7,
        evidence_score=8,
        total_score=6.1,
        uncertainty=False,
        uncertainty_reason=None,
        status="candidate",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    supporting_document = Document(
        id=uuid.uuid4(),
        title="Backing document",
        created_at=datetime.now(timezone.utc),
    )
    opportunity.evidence_items = []
    opportunity._review_test_document = supporting_document
    return opportunity


def build_brief() -> DailyBrief:
    return DailyBrief(
        id=uuid.uuid4(),
        brief_date=datetime.now(timezone.utc),
        brief_type="on_demand",
        risks=[
            {
                "title": "Model provider concentration",
                "severity": "high",
                "description": "Too much workflow dependency on one provider.",
            }
        ],
        uncertainties=["Provider lock-in remains unclear."],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def main() -> None:
    service = WebMvpService()
    opportunity = build_opportunity()
    brief = build_brief()
    captured: dict[str, Any] = {}
    original_review_service = web_service_module.DatabaseReviewService

    class FakeDatabaseReviewService:
        def __init__(self, session) -> None:
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            if target_type == "uncertainty":
                uncertainty_overrides = {
                    "uncertainty_note": "Manual uncertainty note.",
                    "uncertainty_status": "watching",
                }
                uncertainty_read_overrides = {
                    "uncertainty_note": "Adjusted uncertainty note.",
                    "uncertainty_status": "resolved",
                }
                if captured.get("mode") == "uncertainty_read":
                    return uncertainty_read_overrides.get(field_name, auto_value)
                return uncertainty_overrides.get(field_name, auto_value)
            if target_type == "risk":
                risk_overrides = {
                    "severity": "medium",
                    "description": "Manual risk wording.",
                }
                risk_read_overrides = {
                    "severity": "low",
                    "description": "Risk review display override.",
                }
                if captured.get("mode") == "risk_read":
                    return risk_read_overrides.get(field_name, auto_value)
                return risk_overrides.get(field_name, auto_value)
            overrides = {
                "need_realness": 6,
                "market_gap": 5,
                "feasibility": 6,
                "priority_score": 7,
                "evidence_score": 8,
                "total_score": 6.1,
                "uncertainty": False,
                "uncertainty_reason": None,
                "status": "candidate",
            }
            read_overrides = {
                "need_realness": 9,
                "priority_score": 8,
                "uncertainty": True,
                "uncertainty_reason": "Needs follow-up",
                "status": "watching",
            }
            if captured.get("mode") == "read":
                return read_overrides.get(field_name, auto_value)
            return overrides.get(field_name, auto_value)

        def create_batch(self, target_type, target_id, batch, reason=None):
            captured["target_type"] = target_type
            captured["target_id"] = target_id
            captured["batch"] = batch
            captured["reason"] = reason
            return batch

        def get_override_status(self, target_type, target_id, field_name):
            if target_type == "uncertainty":
                return OverrideStatus(
                    field_name=field_name,
                    source="manual",
                    last_manual_value=None,
                    last_manual_at=None,
                    current_auto_value=None,
                )
            if target_type == "risk":
                return OverrideStatus(
                    field_name=field_name,
                    source="manual",
                    last_manual_value=None,
                    last_manual_at=None,
                    current_auto_value=None,
                )
            manual_fields = {"need_realness", "priority_score", "uncertainty", "uncertainty_reason", "status"}
            return OverrideStatus(
                field_name=field_name,
                source="manual" if field_name in manual_fields else "auto",
                last_manual_value=None,
                last_manual_at=None,
                current_auto_value=None,
            )

        def get_history(self, target_type, target_id, field_name=None):
            if target_type == "uncertainty":
                edit = ReviewEdit(
                    id=uuid.uuid4(),
                    target_type=target_type,
                    target_id=target_id,
                    field_name="uncertainty_note",
                    old_value='"Provider lock-in remains unclear."',
                    new_value='"Adjusted uncertainty note."',
                    reviewer="owner",
                    reason="Uncertainty review",
                    created_at=datetime.now(timezone.utc),
                )
                return ReviewHistoryResponse(
                    target_type=target_type,
                    target_id=target_id,
                    edits=[edit],
                    total_count=1,
                    latest_values={"uncertainty_note": "Adjusted uncertainty note."},
                )
            if target_type == "risk":
                edit = ReviewEdit(
                    id=uuid.uuid4(),
                    target_type=target_type,
                    target_id=target_id,
                    field_name="severity",
                    old_value='"medium"',
                    new_value='"low"',
                    reviewer="owner",
                    reason="Risk review",
                    created_at=datetime.now(timezone.utc),
                )
                return ReviewHistoryResponse(
                    target_type=target_type,
                    target_id=target_id,
                    edits=[edit],
                    total_count=1,
                    latest_values={"severity": "low"},
                )
            edit = ReviewEdit(
                id=uuid.uuid4(),
                target_type=target_type,
                target_id=target_id,
                field_name="need_realness",
                old_value="6",
                new_value="9",
                reviewer="owner",
                reason="Human review",
                created_at=datetime.now(timezone.utc),
            )
            return ReviewHistoryResponse(
                target_type=target_type,
                target_id=target_id,
                edits=[edit],
                total_count=1,
                latest_values={"need_realness": 9},
            )

    web_service_module.DatabaseReviewService = FakeDatabaseReviewService
    try:
        service._require_session = lambda: FakeWriteSession(opportunity)
        save_message = service.save_opportunity_review(
            str(opportunity.id),
            {
                "need_realness": "9",
                "market_gap": "5",
                "feasibility": "6",
                "priority_score": "8",
                "evidence_score": "8",
                "total_score": "6.1",
                "uncertainty": "true",
                "uncertainty_reason": "Needs follow-up",
                "status": "watching",
                "reason": "Human review",
            },
        )
        assert save_message == "Opportunity review saved."
        assert opportunity.need_realness == 4
        assert opportunity.status == "candidate"
        assert captured["target_type"] == "opportunity_score"
        assert captured["target_id"] == opportunity.id
        assert [edit.field_name for edit in captured["batch"]] == [
            "need_realness",
            "priority_score",
            "uncertainty",
            "uncertainty_reason",
            "status",
        ]

        captured["mode"] = "read"
        service._try_create_db_session = lambda: FakeReadSession([opportunity])
        views, error = service.list_review_opportunities()
        assert error is None
        assert len(views) == 1
        view = views[0]
        assert view.auto_values["need_realness"] == 4
        assert view.effective_values["need_realness"] == 9
        assert view.effective_values["priority_score"] == 8
        assert view.effective_values["uncertainty"] is True
        assert view.effective_values["status"] == "watching"
        assert view.source_document_title == "Backing document"
        assert len(view.history) == 1

        risk_item_id = f"{service._build_daily_brief_risk_item_id(brief.risks[0])}:0"
        risk_route_id = str(service._build_daily_brief_risk_target_id(brief.id, risk_item_id))
        service._require_session = lambda: FakeWriteSession(brief=brief)
        save_risk_message = service.save_risk_review(
            str(brief.id),
            risk_route_id,
            {
                "severity": "low",
                "description": "Risk review display override.",
                "reason": "Risk review",
            },
        )
        assert save_risk_message == "Risk review saved."
        assert brief.risks[0]["severity"] == "high"
        assert captured["target_type"] == "risk"

        captured["mode"] = "risk_read"
        service._try_create_db_session = lambda: FakeReadSession(briefs=[brief])
        risk_views, risk_error = service.list_review_risks()
        assert risk_error is None
        assert len(risk_views) == 1
        risk_view = risk_views[0]
        assert risk_view.auto_values["severity"] == "high"
        assert risk_view.effective_values["severity"] == "low"
        assert risk_view.effective_values["description"] == "Risk review display override."
        assert risk_view.item_id == risk_item_id
        assert risk_view.route_id == risk_route_id
        assert len(risk_view.history) == 1

        uncertainty_item_id = f"{service._build_daily_brief_uncertainty_item_id(brief.uncertainties[0])}:0"
        uncertainty_route_id = str(
            service._build_daily_brief_uncertainty_target_id(brief.id, uncertainty_item_id)
        )
        service._require_session = lambda: FakeWriteSession(brief=brief)
        save_uncertainty_message = service.save_uncertainty_review(
            str(brief.id),
            uncertainty_route_id,
            {
                "uncertainty_note": "Adjusted uncertainty note.",
                "uncertainty_status": "resolved",
                "reason": "Uncertainty review",
            },
        )
        assert save_uncertainty_message == "Uncertainty review saved."
        assert brief.uncertainties[0] == "Provider lock-in remains unclear."
        assert captured["target_type"] == "uncertainty"

        captured["mode"] = "uncertainty_read"
        service._try_create_db_session = lambda: FakeReadSession(briefs=[brief])
        uncertainty_views, uncertainty_error = service.list_review_uncertainties()
        assert uncertainty_error is None
        assert len(uncertainty_views) == 1
        uncertainty_view = uncertainty_views[0]
        assert uncertainty_view.auto_values["uncertainty_note"] == "Provider lock-in remains unclear."
        assert uncertainty_view.effective_values["uncertainty_note"] == "Adjusted uncertainty note."
        assert uncertainty_view.effective_values["uncertainty_status"] == "resolved"
        assert uncertainty_view.item_id == uncertainty_item_id
        assert uncertainty_view.route_id == uncertainty_route_id
        assert len(uncertainty_view.history) == 1
    finally:
        web_service_module.DatabaseReviewService = original_review_service

    print("verify_review.py: PASS")


if __name__ == "__main__":
    main()
