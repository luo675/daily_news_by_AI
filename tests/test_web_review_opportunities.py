from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
import shutil

import pytest

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.routes import web as web_routes
from src.admin.review_schemas import ReviewHistoryResponse
from src.admin.review_service_db import DatabaseReviewService, InvalidReviewError
from src.admin import review_service_db
from src.admin.review_schemas import ReviewEditCreate, OverrideStatus
from src.domain.models import DailyBrief, Document, DocumentSummary, OpportunityAssessment, ReviewEdit
from src.web.service import OpportunityReviewView, RiskReviewView, SummaryReviewView, UncertaintyReviewView, WebMvpService

from src.web import service as web_service_module

@pytest.fixture
def workspace_tmp_path() -> Path:
    root = Path("tests") / ".tmp" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)

def _configure_web_storage(monkeypatch, tmp_path: Path) -> None:
    web_dir = tmp_path / "web"
    monkeypatch.setattr(web_service_module, "WEB_CONFIG_DIR", web_dir)
    monkeypatch.setattr(web_service_module, "AI_SETTINGS_PATH", web_dir / "ai_settings.json")
    monkeypatch.setattr(web_service_module, "QA_HISTORY_PATH", web_dir / "qa_history.json")

def _build_opportunity() -> OpportunityAssessment:
    opportunity = OpportunityAssessment(
        id=uuid.uuid4(),
        title_zh="自动机会标题",
        title_en="Auto opportunity title",
        description_zh="自动机会说明",
        description_en="Auto opportunity summary",
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
    evidence_document = Document(
        id=uuid.uuid4(),
        title="Backing document",
        created_at=datetime.now(timezone.utc),
    )
    opportunity.evidence_items = []
    opportunity._review_test_document = evidence_document
    return opportunity

def _build_document_with_summary() -> Document:
    document = Document(
        id=uuid.uuid4(),
        title="Reviewed summary document",
        content_text="AI coding tools changed this week with new review workflows.",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    document.summary = DocumentSummary(
        id=uuid.uuid4(),
        document_id=document.id,
        summary_zh="自动中文摘要",
        summary_en="Automatic English summary",
        key_points=["Auto key point one", "Auto key point two"],
    )
    return document

def _build_brief_with_risks() -> DailyBrief:
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
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

def _build_brief_with_duplicate_risks() -> DailyBrief:
    duplicate = {
        "title": "Model provider concentration",
        "severity": "high",
        "description": "Too much workflow dependency on one provider.",
    }
    return DailyBrief(
        id=uuid.uuid4(),
        brief_date=datetime.now(timezone.utc),
        brief_type="on_demand",
        risks=[duplicate.copy(), duplicate.copy()],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

def _build_brief_with_special_item_id() -> DailyBrief:
    return DailyBrief(
        id=uuid.uuid4(),
        brief_date=datetime.now(timezone.utc),
        brief_type="on_demand",
        risks=[
            {
                "item_id": "risk/with special?chars#1",
                "title": "Model provider concentration",
                "severity": "high",
                "description": "Too much workflow dependency on one provider.",
            }
        ],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

def _build_brief_with_uncertainties() -> DailyBrief:
    return DailyBrief(
        id=uuid.uuid4(),
        brief_date=datetime.now(timezone.utc),
        brief_type="on_demand",
        uncertainties=["Provider lock-in remains unclear."],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

def _build_brief_with_duplicate_uncertainties() -> DailyBrief:
    return DailyBrief(
        id=uuid.uuid4(),
        brief_date=datetime.now(timezone.utc),
        brief_type="on_demand",
        uncertainties=[
            "Provider lock-in remains unclear.",
            "Provider lock-in remains unclear.",
        ],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

class _FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def unique(self):
        return self

    def __iter__(self):
        return iter(self._items)

class _FakeReadSession:
    def __init__(self, opportunities=None, briefs=None):
        self._opportunities = opportunities
        self._briefs = briefs or []
        self.closed = False

    def scalars(self, stmt):
        items = self._opportunities if self._opportunities is not None else self._briefs
        return _FakeScalarResult(items)

    def close(self):
        self.closed = True

class _FakeWriteSession:
    def __init__(
        self,
        opportunity: OpportunityAssessment | None = None,
        brief: DailyBrief | None = None,
        summary: DocumentSummary | None = None,
    ):
        self.opportunity = opportunity
        self.brief = brief
        self.summary = summary
        self.closed = False
        self.rolled_back = False

    def get(self, model, object_id):
        if self.opportunity is not None and object_id == self.opportunity.id:
            return self.opportunity
        if self.brief is not None and object_id == self.brief.id:
            return self.brief
        if self.summary is not None and object_id == self.summary.id:
            return self.summary
        return None

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True

class _FakeAtomicSession:
    def __init__(self):
        self.pending = []
        self.persisted = []
        self.commit_count = 0
        self.rollback_count = 0

    def add(self, item):
        if getattr(item, "id", None) is None:
            item.id = uuid.uuid4()
        self.pending.append(item)

    def commit(self):
        self.commit_count += 1
        self.persisted.extend(self.pending)
        self.pending = []

    def rollback(self):
        self.rollback_count += 1
        self.pending = []

    def refresh(self, item):
        return None

    def scalar(self, stmt):
        return None

    def scalars(self, stmt):
        return []

def test_list_review_opportunities_applies_manual_overrides(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    opportunity = _build_opportunity()
    read_session = _FakeReadSession([opportunity])

    monkeypatch.setattr(service, "_try_create_db_session", lambda: read_session)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            overrides = {
                "need_realness": 9,
                "priority_score": 8,
                "uncertainty": True,
                "uncertainty_reason": "manual note",
            }
            return overrides.get(field_name, auto_value)

        def get_history(self, target_type, target_id, field_name=None):
            edit = ReviewEdit(
                id=uuid.uuid4(),
                target_type=target_type,
                target_id=target_id,
                field_name="need_realness",
                old_value="4",
                new_value="9",
                reviewer="owner",
                reason="manual override",
                created_at=datetime.now(timezone.utc),
            )
            return ReviewHistoryResponse(
                target_type=target_type,
                target_id=target_id,
                edits=[edit],
                total_count=1,
                latest_values={"need_realness": 9},
            )

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    views, error = service.list_review_opportunities()

    assert error is None
    assert len(views) == 1
    assert views[0].auto_values["need_realness"] == 4
    assert views[0].effective_values["need_realness"] == 9
    assert views[0].effective_values["priority_score"] == 8
    assert views[0].effective_values["uncertainty"] is True
    assert views[0].effective_values["uncertainty_reason"] == "manual note"

def test_save_summary_review_writes_review_edits_only(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    document = _build_document_with_summary()
    summary = document.summary
    assert summary is not None
    write_session = _FakeWriteSession(summary=summary)
    captured: dict[str, object] = {}

    monkeypatch.setattr(service, "_require_session", lambda: write_session)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            return auto_value

        def get_override_status(self, target_type, target_id, field_name):
            return OverrideStatus(
                field_name=field_name,
                source="auto",
                last_manual_value=None,
                last_manual_at=None,
                current_auto_value=None,
            )

        def create_batch(self, target_type, target_id, batch, reason=None):
            captured["target_type"] = target_type
            captured["target_id"] = target_id
            captured["batch"] = batch
            return batch

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    message = service.save_summary_review(
        str(summary.id),
        {
            "summary_zh": "人工中文摘要",
            "summary_en": "Manual English summary",
            "key_points": "Manual key point one\nManual key point two",
            "reason": "Summary review",
        },
    )

    assert message == "Summary review saved."
    assert summary.summary_zh == "自动中文摘要"
    assert summary.summary_en == "Automatic English summary"
    assert summary.key_points == ["Auto key point one", "Auto key point two"]
    edits = captured["batch"]
    assert [edit.field_name for edit in edits] == ["summary_zh", "summary_en", "key_points"]
    assert edits[0].new_value == "人工中文摘要"
    assert edits[1].new_value == "Manual English summary"
    assert edits[2].new_value == ["Manual key point one", "Manual key point two"]

def test_save_summary_review_reset_to_auto(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    document = _build_document_with_summary()
    summary = document.summary
    assert summary is not None
    write_session = _FakeWriteSession(summary=summary)
    captured: dict[str, object] = {}

    monkeypatch.setattr(service, "_require_session", lambda: write_session)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            values = {
                "summary_zh": "人工中文摘要",
                "summary_en": "Manual English summary",
                "key_points": ["Manual key point one"],
            }
            return values[field_name]

        def get_override_status(self, target_type, target_id, field_name):
            return OverrideStatus(
                field_name=field_name,
                source="manual",
                last_manual_value=None,
                last_manual_at=datetime.now(timezone.utc),
                current_auto_value=None,
            )

        def create_batch(self, target_type, target_id, batch, reason=None):
            captured["batch"] = batch
            return batch

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    message = service.save_summary_review(
        str(summary.id),
        {
            "summary_zh": "",
            "reset_summary_zh": "on",
            "summary_en": "",
            "reset_summary_en": "on",
            "key_points": "",
            "reset_key_points": "on",
            "reason": "Reset summary fields",
        },
    )

    assert message == "Summary review saved."
    edits = captured["batch"]
    assert [edit.field_name for edit in edits] == ["summary_zh", "summary_en", "key_points"]
    assert edits[0].new_value == review_service_db.RESET_TO_AUTO_SENTINEL
    assert edits[1].new_value == review_service_db.RESET_TO_AUTO_SENTINEL
    assert edits[2].new_value == review_service_db.RESET_TO_AUTO_SENTINEL

def test_save_opportunity_review_writes_review_edits_only(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    opportunity = _build_opportunity()
    write_session = _FakeWriteSession(opportunity)
    captured: dict[str, object] = {}

    monkeypatch.setattr(service, "_require_session", lambda: write_session)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            current = {
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
            return current[field_name]

        def get_override_status(self, target_type, target_id, field_name):
            return OverrideStatus(
                field_name=field_name,
                source="manual" if field_name == "need_realness" else "auto",
                last_manual_value=None,
                last_manual_at=None,
                current_auto_value=None,
            )

        def create_batch(self, target_type, target_id, batch, reason=None):
            captured["target_type"] = target_type
            captured["target_id"] = target_id
            captured["batch"] = batch
            captured["reason"] = reason
            return batch

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    message = service.save_opportunity_review(
        str(opportunity.id),
        {
            "need_realness": "9",
            "market_gap": "5",
            "feasibility": "6",
            "priority_score": "7",
            "evidence_score": "8",
            "total_score": "6.1",
            "uncertainty": "true",
            "uncertainty_reason": "Needs follow-up",
            "status": "watching",
            "reason": "Human review",
        },
    )

    assert message == "Opportunity review saved."
    assert opportunity.need_realness == 4
    assert opportunity.status == "candidate"
    assert captured["target_type"] == "opportunity_score"
    assert captured["target_id"] == opportunity.id
    edits = captured["batch"]
    assert [edit.field_name for edit in edits] == [
        "need_realness",
        "uncertainty",
        "uncertainty_reason",
        "status",
    ]
    assert edits[0].old_value == 6
    assert edits[0].new_value == 9

def test_save_opportunity_review_clearing_manual_field_resets_to_auto(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    assert hasattr(review_service_db, "RESET_TO_AUTO_SENTINEL")

    service = WebMvpService()
    opportunity = _build_opportunity()
    write_session = _FakeWriteSession(opportunity)
    captured: dict[str, object] = {}

    monkeypatch.setattr(service, "_require_session", lambda: write_session)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            values = {
                "need_realness": 9,
                "market_gap": 5,
                "feasibility": 6,
                "priority_score": 7,
                "evidence_score": 8,
                "total_score": 6.1,
                "uncertainty": False,
                "uncertainty_reason": None,
                "status": "candidate",
            }
            return values[field_name]

        def get_override_status(self, target_type, target_id, field_name):
            if field_name == "need_realness":
                return OverrideStatus(
                    field_name=field_name,
                    source="manual",
                    last_manual_value=9,
                    last_manual_at=datetime.now(timezone.utc),
                    current_auto_value=4,
                )
            return OverrideStatus(
                field_name=field_name,
                source="auto",
                last_manual_value=None,
                last_manual_at=None,
                current_auto_value=None,
            )

        def create_batch(self, target_type, target_id, batch, reason=None):
            captured["batch"] = batch
            return batch

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    message = service.save_opportunity_review(
        str(opportunity.id),
        {
            "need_realness": "",
            "market_gap": "5",
            "feasibility": "6",
            "priority_score": "7",
            "evidence_score": "8",
            "total_score": "6.1",
            "uncertainty": "false",
            "uncertainty_reason": "",
            "status": "candidate",
            "reason": "Reset to automatic",
        },
    )

    assert message == "Opportunity review saved."
    edits = captured["batch"]
    assert len(edits) == 1
    assert edits[0].field_name == "need_realness"
    assert edits[0].new_value == review_service_db.RESET_TO_AUTO_SENTINEL

def test_database_review_service_uses_auto_value_when_latest_edit_is_reset_marker() -> None:
    assert hasattr(review_service_db, "RESET_TO_AUTO_SENTINEL")
    service = DatabaseReviewService(_FakeAtomicSession())
    target_id = uuid.uuid4()

    service._get_latest_edit = lambda target_type, object_id, field_name: ReviewEdit(
        id=uuid.uuid4(),
        target_type=target_type,
        target_id=object_id,
        field_name=field_name,
        old_value="9",
        new_value=f'"{review_service_db.RESET_TO_AUTO_SENTINEL}"',
        reviewer="owner",
        reason="reset",
        created_at=datetime.now(timezone.utc),
    )

    assert service.get_effective_value("opportunity_score", target_id, "need_realness", 4) == 4

def test_database_review_service_create_batch_is_atomic() -> None:
    session = _FakeAtomicSession()
    service = DatabaseReviewService(session)

    with pytest.raises(InvalidReviewError):
        service.create_batch(
            "opportunity_score",
            uuid.uuid4(),
            [
                ReviewEditCreate(field_name="need_realness", new_value=9, old_value=4),
                ReviewEditCreate(field_name="summary_zh", new_value="invalid for opportunity_score"),
            ],
        )

    assert session.commit_count == 0
    assert session.persisted == []

def test_review_page_renders_opportunity_review_card(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    opportunity = _build_opportunity()
    edit = ReviewEdit(
        id=uuid.uuid4(),
        target_type="opportunity_score",
        target_id=opportunity.id,
        field_name="need_realness",
        old_value="4",
        new_value="9",
        reviewer="owner",
        reason="manual override",
        created_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(
        web_routes.service,
        "list_review_opportunities",
        lambda: (
            [
                OpportunityReviewView(
                    opportunity=opportunity,
                    auto_values={"need_realness": 4, "priority_score": 7, "uncertainty": False},
                    effective_values={"need_realness": 9, "priority_score": 8, "uncertainty": True},
                    history=[edit],
                    source_document_title="Backing document",
                )
            ],
            None,
        ),
    )
    monkeypatch.setattr(web_routes.service, "list_review_documents", lambda: ([], None))

    client = TestClient(create_app())
    response = client.get("/web/review")

    assert response.status_code == 200
    assert "机会审阅" in response.text
    assert "Auto opportunity title" in response.text
    assert "Backing document" in response.text
    assert "action=\"/web/review/opportunities/" in response.text
    assert "name=\"reset_status\"" in response.text
    assert "name=\"reset_uncertainty\"" in response.text

def test_review_page_renders_summary_review_card(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    document = _build_document_with_summary()
    summary = document.summary
    assert summary is not None
    edit = ReviewEdit(
        id=uuid.uuid4(),
        target_type="summary",
        target_id=summary.id,
        field_name="summary_en",
        old_value='"Automatic English summary"',
        new_value='"Manual English summary"',
        reviewer="owner",
        reason="manual override",
        created_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(web_routes.service, "list_review_uncertainties", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_risks", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_opportunities", lambda: ([], None))
    monkeypatch.setattr(
        web_routes.service,
        "list_review_documents",
        lambda: (
            [
                SummaryReviewView(
                    document=document,
                    summary=summary,
                    auto_values={
                        "summary_zh": "自动中文摘要",
                        "summary_en": "Automatic English summary",
                        "key_points": ["Auto key point one", "Auto key point two"],
                    },
                    effective_values={
                        "summary_zh": "人工中文摘要",
                        "summary_en": "Manual English summary",
                        "key_points": ["Manual key point one"],
                    },
                    history=[edit],
                )
            ],
            None,
        ),
    )

    client = TestClient(create_app())
    response = client.get("/web/review")

    assert response.status_code == 200
    assert "摘要审阅" in response.text
    assert "Reviewed summary document" in response.text
    assert "自动结果" in response.text
    assert "生效值" in response.text
    assert "Manual Effective Values" not in response.text
    assert "审阅历史" in response.text
    assert "name=\"reset_summary_zh\"" in response.text
    assert "name=\"reset_summary_en\"" in response.text
    assert "name=\"reset_key_points\"" in response.text
    assert f"action=\"/web/review/{summary.id}?lang=zh\"" in response.text

def test_review_page_renders_english_shell_when_lang_query_requests_en(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    document = _build_document_with_summary()
    summary = document.summary
    assert summary is not None
    monkeypatch.setattr(web_routes.service, "list_review_uncertainties", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_risks", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_opportunities", lambda: ([], None))
    monkeypatch.setattr(
        web_routes.service,
        "list_review_documents",
        lambda: (
            [
                SummaryReviewView(
                    document=document,
                    summary=summary,
                    auto_values={"summary_zh": "", "summary_en": "Automatic English summary", "key_points": []},
                    effective_values={"summary_zh": "", "summary_en": "Automatic English summary", "key_points": []},
                    history=[],
                )
            ],
            None,
        ),
    )

    client = TestClient(create_app())
    response = client.get("/web/review?lang=en&type=summary")

    assert response.status_code == 200
    assert "Review" in response.text
    assert "Summary Review" in response.text
    assert "Automatic Result" in response.text
    assert "Effective Values" in response.text
    assert "Review History" in response.text
    assert "/web/review?lang=en" in response.text
    assert "/web/review?lang=en&amp;type=opportunity" in response.text
    assert f"action=\"/web/review/{summary.id}?lang=en&amp;type=summary\"" in response.text
    assert "摘要审阅" not in response.text

def test_review_page_renders_type_specific_empty_state(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    monkeypatch.setattr(web_routes.service, "list_review_uncertainties", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_risks", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_opportunities", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_documents", lambda: ([], None))

    client = TestClient(create_app())
    response = client.get("/web/review?type=risk")

    assert response.status_code == 200
    assert "\u5f53\u524d\u7b5b\u9009\uff1a\u98ce\u9669" in response.text
    assert "\u6682\u65e0\u98ce\u9669\u5ba1\u9605\u9879\u3002" in response.text
    assert "\u6682\u65e0\u5ba1\u9605\u9879\u3002" not in response.text


def test_review_page_renders_english_type_specific_empty_state(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    monkeypatch.setattr(web_routes.service, "list_review_uncertainties", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_risks", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_opportunities", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_documents", lambda: ([], None))

    client = TestClient(create_app())
    response = client.get("/web/review?lang=en&type=summary")

    assert response.status_code == 200
    assert "Current filter: Summary" in response.text
    assert "No summary review items available." in response.text
    assert "No review items available." not in response.text


@pytest.mark.parametrize(
    "review_type, expected_counts, present_texts, absent_texts",
    [
        (
            "summary",
            {"uncertainties": 0, "risks": 0, "opportunities": 0, "documents": 1},
            ["Reviewed summary document"],
            ["Auto opportunity title", "Model provider concentration", "Provider lock-in remains unclear."],
        ),
        (
            "opportunity",
            {"uncertainties": 0, "risks": 0, "opportunities": 1, "documents": 0},
            ["Auto opportunity title"],
            ["Reviewed summary document", "Model provider concentration", "Provider lock-in remains unclear."],
        ),
        (
            "risk",
            {"uncertainties": 0, "risks": 1, "opportunities": 0, "documents": 0},
            ["Model provider concentration"],
            ["Reviewed summary document", "Auto opportunity title", "Provider lock-in remains unclear."],
        ),
        (
            "uncertainty",
            {"uncertainties": 1, "risks": 0, "opportunities": 0, "documents": 0},
            ["Provider lock-in remains unclear."],
            ["Reviewed summary document", "Auto opportunity title", "Model provider concentration"],
        ),
        (
            "bogus",
            {"uncertainties": 1, "risks": 1, "opportunities": 1, "documents": 1},
            ["Reviewed summary document", "Auto opportunity title", "Model provider concentration", "Provider lock-in remains unclear."],
            [],
        ),
    ],
)
def test_review_page_type_filter_calls_only_requested_service(
    monkeypatch,
    workspace_tmp_path: Path,
    review_type: str,
    expected_counts: dict[str, int],
    present_texts: list[str],
    absent_texts: list[str],
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)

    summary_document = _build_document_with_summary()
    summary = summary_document.summary
    assert summary is not None
    opportunity = _build_opportunity()
    brief_risk = _build_brief_with_risks()
    brief_uncertainty = _build_brief_with_uncertainties()
    risk_target_id = uuid.uuid4()
    uncertainty_target_id = uuid.uuid4()

    counts = {"uncertainties": 0, "risks": 0, "opportunities": 0, "documents": 0}

    def _count(name: str, payload: tuple[list[object], str | None]):
        def _inner():
            counts[name] += 1
            return payload

        return _inner

    monkeypatch.setattr(
        web_routes.service,
        "list_review_uncertainties",
        _count(
            "uncertainties",
            (
                [
                    UncertaintyReviewView(
                        brief=brief_uncertainty,
                        uncertainty_item=brief_uncertainty.uncertainties[0],
                        item_id="uncertainty-item-1",
                        route_id=str(uncertainty_target_id),
                        target_id=uncertainty_target_id,
                        auto_values={"uncertainty_note": "Provider lock-in remains unclear.", "uncertainty_status": None},
                        effective_values={"uncertainty_note": "Manual uncertainty note.", "uncertainty_status": None},
                        history=[],
                    )
                ],
                None,
            ),
        ),
    )
    monkeypatch.setattr(
        web_routes.service,
        "list_review_risks",
        _count(
            "risks",
            (
                [
                    RiskReviewView(
                        brief=brief_risk,
                        risk_item=brief_risk.risks[0],
                        item_id="risk-item-1",
                        route_id=str(risk_target_id),
                        target_id=risk_target_id,
                        auto_values={"severity": "high", "description": "Too much workflow dependency on one provider."},
                        effective_values={"severity": "medium", "description": "Manual risk wording."},
                        history=[],
                    )
                ],
                None,
            ),
        ),
    )
    monkeypatch.setattr(
        web_routes.service,
        "list_review_opportunities",
        _count(
            "opportunities",
            (
                [
                    OpportunityReviewView(
                        opportunity=opportunity,
                        auto_values={"need_realness": 4, "priority_score": 7, "uncertainty": False},
                        effective_values={"need_realness": 9, "priority_score": 8, "uncertainty": True},
                        history=[],
                        source_document_title="Backing document",
                    )
                ],
                None,
            ),
        ),
    )
    monkeypatch.setattr(
        web_routes.service,
        "list_review_documents",
        _count(
            "documents",
            (
                [
                    SummaryReviewView(
                        document=summary_document,
                        summary=summary,
                        auto_values={
                            "summary_zh": "自动中文摘要",
                            "summary_en": "Automatic English summary",
                            "key_points": ["Auto key point one", "Auto key point two"],
                        },
                        effective_values={
                            "summary_zh": "人工中文摘要",
                            "summary_en": "Manual English summary",
                            "key_points": ["Manual key point one"],
                        },
                        history=[],
                    )
                ],
                None,
            ),
        ),
    )

    client = TestClient(create_app())
    response = client.get(f"/web/review?type={review_type}")

    assert response.status_code == 200
    assert counts == expected_counts
    for text in present_texts:
        assert text in response.text
    for text in absent_texts:
        assert text not in response.text

def test_review_page_submit_includes_explicit_reset_flags(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    captured: dict[str, object] = {}
    opportunity_id = str(uuid.uuid4())

    def _save(opportunity_id_arg: str, form: dict[str, str]) -> str:
        captured["opportunity_id"] = opportunity_id_arg
        captured["form"] = form
        return "Opportunity review saved."

    monkeypatch.setattr(web_routes.service, "save_opportunity_review", _save)

    client = TestClient(create_app())
    response = client.post(
        f"/web/review/opportunities/{opportunity_id}",
        data={
            "status": "watching",
            "reset_status": "on",
            "uncertainty": "true",
            "reset_uncertainty": "on",
            "reason": "Reset selected fields",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert captured["opportunity_id"] == opportunity_id
    assert captured["form"]["reset_status"] == "on"
    assert captured["form"]["reset_uncertainty"] == "on"

def test_review_summary_submit_preserves_current_type_and_lang(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    summary_id = str(uuid.uuid4())

    monkeypatch.setattr(
        web_routes.service,
        "save_summary_review",
        lambda summary_id_arg, form: "Summary review saved.",
    )

    client = TestClient(create_app())
    response = client.post(
        f"/web/review/{summary_id}?lang=en&type=summary",
        data={"summary_en": "Manual summary"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/web/review?")
    assert "lang=en" in response.headers["location"]
    assert "type=summary" in response.headers["location"]

@pytest.mark.parametrize(
    "route, data, expected_type, saver_name, saver",
    [
        (
            "/web/review/opportunities/{item_id}?lang=en&type=opportunity",
            {"need_realness": "8"},
            "opportunity",
            "save_opportunity_review",
            lambda item_id, form: "Opportunity review saved.",
        ),
        (
            "/web/review/risks/{brief_id}/{item_id}?lang=en&type=risk",
            {"severity": "medium"},
            "risk",
            "save_risk_review",
            lambda brief_id, item_id, form: "Risk review saved.",
        ),
        (
            "/web/review/uncertainties/{brief_id}/{item_id}?lang=en&type=uncertainty",
            {"uncertainty_note": "Manual note"},
            "uncertainty",
            "save_uncertainty_review",
            lambda brief_id, item_id, form: "Uncertainty review saved.",
        ),
    ],
)
def test_review_non_summary_submit_preserves_current_type_and_lang(
    monkeypatch,
    workspace_tmp_path: Path,
    route: str,
    data: dict[str, str],
    expected_type: str,
    saver_name: str,
    saver,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    brief_id = str(uuid.uuid4())
    item_id = str(uuid.uuid4())
    monkeypatch.setattr(web_routes.service, saver_name, saver)

    client = TestClient(create_app())
    response = client.post(
        route.format(brief_id=brief_id, item_id=item_id),
        data=data,
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/web/review?")
    assert "lang=en" in response.headers["location"]
    assert f"type={expected_type}" in response.headers["location"]

def test_list_review_risks_applies_manual_overrides(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    brief = _build_brief_with_risks()
    read_session = _FakeReadSession(briefs=[brief])

    monkeypatch.setattr(service, "_try_create_db_session", lambda: read_session)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            overrides = {
                "severity": "medium",
                "description": "Manual risk wording.",
            }
            return overrides.get(field_name, auto_value)

        def get_history(self, target_type, target_id, field_name=None):
            edit = ReviewEdit(
                id=uuid.uuid4(),
                target_type=target_type,
                target_id=target_id,
                field_name="severity",
                old_value='"high"',
                new_value='"medium"',
                reviewer="owner",
                reason="manual override",
                created_at=datetime.now(timezone.utc),
            )
            return ReviewHistoryResponse(
                target_type=target_type,
                target_id=target_id,
                edits=[edit],
                total_count=1,
                latest_values={"severity": "medium"},
            )

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    views, error = service.list_review_risks()

    assert error is None
    assert len(views) == 1
    assert views[0].risk_item["severity"] == "high"
    assert views[0].effective_values["severity"] == "medium"
    assert views[0].effective_values["description"] == "Manual risk wording."
    assert views[0].item_id

def test_list_review_risks_gives_duplicate_items_distinct_targets(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    brief = _build_brief_with_duplicate_risks()
    read_session = _FakeReadSession(briefs=[brief])

    monkeypatch.setattr(service, "_try_create_db_session", lambda: read_session)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            return auto_value

        def get_history(self, target_type, target_id, field_name=None):
            return ReviewHistoryResponse(
                target_type=target_type,
                target_id=target_id,
                edits=[],
                total_count=0,
                latest_values={},
            )

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    views, error = service.list_review_risks()

    assert error is None
    assert len(views) == 2
    assert views[0].item_id != views[1].item_id
    assert views[0].target_id != views[1].target_id

def test_save_risk_review_writes_review_edits_only(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    brief = _build_brief_with_risks()
    write_session = _FakeWriteSession(brief=brief)
    captured: dict[str, object] = {}

    monkeypatch.setattr(service, "_require_session", lambda: write_session)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            current = {
                "severity": "medium",
                "description": "Manual risk wording.",
            }
            return current[field_name]

        def get_override_status(self, target_type, target_id, field_name):
            return OverrideStatus(
                field_name=field_name,
                source="manual",
                last_manual_value=None,
                last_manual_at=None,
                current_auto_value=None,
            )

        def create_batch(self, target_type, target_id, batch, reason=None):
            captured["target_type"] = target_type
            captured["target_id"] = target_id
            captured["batch"] = batch
            return batch

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    message = service.save_risk_review(
        str(brief.id),
        str(service._build_daily_brief_risk_target_id(brief.id, f"{service._build_daily_brief_risk_item_id(brief.risks[0])}:0")),
        {
            "severity": "low",
            "description": "Adjusted risk wording.",
            "reason": "Risk review",
        },
    )

    assert message == "Risk review saved."
    assert brief.risks[0]["severity"] == "high"
    edits = captured["batch"]
    assert [edit.field_name for edit in edits] == ["severity", "description"]

def test_save_risk_review_reset_to_auto(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    brief = _build_brief_with_risks()
    write_session = _FakeWriteSession(brief=brief)
    captured: dict[str, object] = {}

    monkeypatch.setattr(service, "_require_session", lambda: write_session)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            current = {
                "severity": "medium",
                "description": "Manual risk wording.",
            }
            return current[field_name]

        def get_override_status(self, target_type, target_id, field_name):
            return OverrideStatus(
                field_name=field_name,
                source="manual",
                last_manual_value=None,
                last_manual_at=None,
                current_auto_value=None,
            )

        def create_batch(self, target_type, target_id, batch, reason=None):
            captured["batch"] = batch
            return batch

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    message = service.save_risk_review(
        str(brief.id),
        str(service._build_daily_brief_risk_target_id(brief.id, f"{service._build_daily_brief_risk_item_id(brief.risks[0])}:0")),
        {
            "severity": "low",
            "reset_severity": "on",
            "description": "Adjusted risk wording.",
            "reset_description": "on",
            "reason": "Reset risk fields",
        },
    )

    assert message == "Risk review saved."
    edits = captured["batch"]
    assert edits[0].new_value == review_service_db.RESET_TO_AUTO_SENTINEL
    assert edits[1].new_value == review_service_db.RESET_TO_AUTO_SENTINEL

def test_database_review_service_create_batch_is_atomic_for_risk() -> None:
    session = _FakeAtomicSession()
    service = DatabaseReviewService(session)

    with pytest.raises(InvalidReviewError):
        service.create_batch(
            "risk",
            uuid.uuid4(),
            [
                ReviewEditCreate(field_name="severity", new_value="low", old_value="high"),
                ReviewEditCreate(field_name="summary_zh", new_value="invalid for risk"),
            ],
        )

    assert session.commit_count == 0
    assert session.persisted == []

def test_review_page_renders_risk_review_card(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    brief = _build_brief_with_risks()
    target_id = uuid.uuid4()
    edit = ReviewEdit(
        id=uuid.uuid4(),
        target_type="risk",
        target_id=target_id,
        field_name="severity",
        old_value='"high"',
        new_value='"medium"',
        reviewer="owner",
        reason="manual override",
        created_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(
        web_routes.service,
        "list_review_risks",
        lambda: (
            [
                RiskReviewView(
                    brief=brief,
                    risk_item=brief.risks[0],
                    item_id="risk-item-1",
                    route_id=str(target_id),
                    target_id=target_id,
                    auto_values={"severity": "high", "description": "Too much workflow dependency on one provider."},
                    effective_values={"severity": "medium", "description": "Manual risk wording."},
                    history=[edit],
                )
            ],
            None,
        ),
    )
    monkeypatch.setattr(web_routes.service, "list_review_opportunities", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_documents", lambda: ([], None))

    client = TestClient(create_app())
    response = client.get("/web/review")

    assert response.status_code == 200
    assert "风险审阅" in response.text
    assert "生效值" in response.text
    assert "审阅历史" in response.text
    assert "Model provider concentration" in response.text
    assert "name=\"reset_severity\"" in response.text
    assert "name=\"reset_description\"" in response.text
    assert f"action=\"/web/review/risks/{brief.id}/{target_id}?lang=zh\"" in response.text

def test_review_page_submit_risk_includes_reset_flags(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    captured: dict[str, object] = {}
    brief_id = str(uuid.uuid4())
    risk_target_id = str(uuid.uuid4())

    def _save(brief_id_arg: str, risk_target_id_arg: str, form: dict[str, str]) -> str:
        captured["brief_id"] = brief_id_arg
        captured["risk_target_id"] = risk_target_id_arg
        captured["form"] = form
        return "Risk review saved."

    monkeypatch.setattr(web_routes.service, "save_risk_review", _save)

    client = TestClient(create_app())
    response = client.post(
        f"/web/review/risks/{brief_id}/{risk_target_id}",
        data={
            "severity": "low",
            "reset_severity": "on",
            "description": "Risk reset",
            "reset_description": "on",
            "reason": "Reset risk fields",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert captured["brief_id"] == brief_id
    assert captured["risk_target_id"] == risk_target_id
    assert captured["form"]["reset_severity"] == "on"
    assert captured["form"]["reset_description"] == "on"

def test_review_page_uses_safe_risk_route_id_for_special_item_id(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    brief = _build_brief_with_special_item_id()
    target_id = uuid.uuid4()
    monkeypatch.setattr(
        web_routes.service,
        "list_review_risks",
        lambda: (
            [
                RiskReviewView(
                    brief=brief,
                    risk_item=brief.risks[0],
                    item_id="risk/with special?chars#1",
                    route_id=str(target_id),
                    target_id=target_id,
                    auto_values={"severity": "high", "description": "Too much workflow dependency on one provider."},
                    effective_values={"severity": "high", "description": "Too much workflow dependency on one provider."},
                    history=[],
                )
            ],
            None,
        ),
    )
    monkeypatch.setattr(web_routes.service, "list_review_opportunities", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_documents", lambda: ([], None))

    client = TestClient(create_app())
    response = client.get("/web/review")

    assert response.status_code == 200
    assert f"/web/review/risks/{brief.id}/{target_id}" in response.text
    assert "risk/with special?chars#1" not in response.text.split(f"/web/review/risks/{brief.id}/", 1)[1].split('"', 1)[0]

def test_list_review_uncertainties_applies_manual_overrides(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    brief = _build_brief_with_uncertainties()
    read_session = _FakeReadSession(briefs=[brief])

    monkeypatch.setattr(service, "_try_create_db_session", lambda: read_session)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            overrides = {
                "uncertainty_note": "Manual uncertainty note.",
                "uncertainty_status": "watching",
            }
            return overrides.get(field_name, auto_value)

        def get_history(self, target_type, target_id, field_name=None):
            edit = ReviewEdit(
                id=uuid.uuid4(),
                target_type=target_type,
                target_id=target_id,
                field_name="uncertainty_note",
                old_value='"Provider lock-in remains unclear."',
                new_value='"Manual uncertainty note."',
                reviewer="owner",
                reason="manual override",
                created_at=datetime.now(timezone.utc),
            )
            return ReviewHistoryResponse(
                target_type=target_type,
                target_id=target_id,
                edits=[edit],
                total_count=1,
                latest_values={"uncertainty_note": "Manual uncertainty note."},
            )

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    views, error = service.list_review_uncertainties()

    assert error is None
    assert len(views) == 1
    assert views[0].uncertainty_item == "Provider lock-in remains unclear."
    assert views[0].effective_values["uncertainty_note"] == "Manual uncertainty note."
    assert views[0].effective_values["uncertainty_status"] == "watching"

def test_list_review_uncertainties_gives_duplicate_items_distinct_targets(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    brief = _build_brief_with_duplicate_uncertainties()
    read_session = _FakeReadSession(briefs=[brief])

    monkeypatch.setattr(service, "_try_create_db_session", lambda: read_session)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            return auto_value

        def get_history(self, target_type, target_id, field_name=None):
            return ReviewHistoryResponse(
                target_type=target_type,
                target_id=target_id,
                edits=[],
                total_count=0,
                latest_values={},
            )

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    views, error = service.list_review_uncertainties()

    assert error is None
    assert len(views) == 2
    assert views[0].item_id != views[1].item_id
    assert views[0].target_id != views[1].target_id

def test_save_uncertainty_review_writes_review_edits_only(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    brief = _build_brief_with_uncertainties()
    write_session = _FakeWriteSession(brief=brief)
    captured: dict[str, object] = {}
    route_id = str(
        service._build_daily_brief_uncertainty_target_id(
            brief.id,
            f"{service._build_daily_brief_uncertainty_item_id(brief.uncertainties[0])}:0",
        )
    )

    monkeypatch.setattr(service, "_require_session", lambda: write_session)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            current = {
                "uncertainty_note": "Manual uncertainty note.",
                "uncertainty_status": "watching",
            }
            return current[field_name]

        def get_override_status(self, target_type, target_id, field_name):
            return OverrideStatus(
                field_name=field_name,
                source="manual",
                last_manual_value=None,
                last_manual_at=None,
                current_auto_value=None,
            )

        def create_batch(self, target_type, target_id, batch, reason=None):
            captured["target_type"] = target_type
            captured["target_id"] = target_id
            captured["batch"] = batch
            return batch

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    message = service.save_uncertainty_review(
        str(brief.id),
        route_id,
        {
            "uncertainty_note": "Adjusted uncertainty note.",
            "uncertainty_status": "resolved",
            "reason": "Uncertainty review",
        },
    )

    assert message == "Uncertainty review saved."
    assert brief.uncertainties[0] == "Provider lock-in remains unclear."
    edits = captured["batch"]
    assert [edit.field_name for edit in edits] == ["uncertainty_note", "uncertainty_status"]

def test_save_uncertainty_review_note_only_does_not_create_status_override(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    brief = _build_brief_with_uncertainties()
    write_session = _FakeWriteSession(brief=brief)
    captured: dict[str, object] = {}
    route_id = str(
        service._build_daily_brief_uncertainty_target_id(
            brief.id,
            f"{service._build_daily_brief_uncertainty_item_id(brief.uncertainties[0])}:0",
        )
    )

    monkeypatch.setattr(service, "_require_session", lambda: write_session)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            current = {
                "uncertainty_note": "Provider lock-in remains unclear.",
                "uncertainty_status": None,
            }
            return current[field_name]

        def get_override_status(self, target_type, target_id, field_name):
            return OverrideStatus(
                field_name=field_name,
                source="auto",
                last_manual_value=None,
                last_manual_at=None,
                current_auto_value=None,
            )

        def create_batch(self, target_type, target_id, batch, reason=None):
            captured["batch"] = batch
            return batch

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    message = service.save_uncertainty_review(
        str(brief.id),
        route_id,
        {
            "uncertainty_note": "Adjusted uncertainty note.",
            "uncertainty_status": "",
            "reason": "Uncertainty note only",
        },
    )

    assert message == "Uncertainty review saved."
    edits = captured["batch"]
    assert [edit.field_name for edit in edits] == ["uncertainty_note"]

def test_save_uncertainty_review_placeholder_status_does_not_create_status_override(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    brief = _build_brief_with_uncertainties()
    write_session = _FakeWriteSession(brief=brief)
    captured: dict[str, object] = {}
    route_id = str(
        service._build_daily_brief_uncertainty_target_id(
            brief.id,
            f"{service._build_daily_brief_uncertainty_item_id(brief.uncertainties[0])}:0",
        )
    )

    monkeypatch.setattr(service, "_require_session", lambda: write_session)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            current = {
                "uncertainty_note": "Provider lock-in remains unclear.",
                "uncertainty_status": None,
            }
            return current[field_name]

        def get_override_status(self, target_type, target_id, field_name):
            return OverrideStatus(
                field_name=field_name,
                source="auto",
                last_manual_value=None,
                last_manual_at=None,
                current_auto_value=None,
            )

        def create_batch(self, target_type, target_id, batch, reason=None):
            captured["batch"] = batch
            return batch

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    message = service.save_uncertainty_review(
        str(brief.id),
        route_id,
        {
            "uncertainty_note": "Adjusted uncertainty note.",
            "uncertainty_status": "__UNCHANGED__",
            "reason": "Uncertainty note only",
        },
    )

    assert message == "Uncertainty review saved."
    edits = captured["batch"]
    assert [edit.field_name for edit in edits] == ["uncertainty_note"]

def test_save_uncertainty_review_reset_to_auto(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    brief = _build_brief_with_uncertainties()
    write_session = _FakeWriteSession(brief=brief)
    captured: dict[str, object] = {}
    route_id = str(
        service._build_daily_brief_uncertainty_target_id(
            brief.id,
            f"{service._build_daily_brief_uncertainty_item_id(brief.uncertainties[0])}:0",
        )
    )

    monkeypatch.setattr(service, "_require_session", lambda: write_session)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            current = {
                "uncertainty_note": "Manual uncertainty note.",
                "uncertainty_status": "watching",
            }
            return current[field_name]

        def get_override_status(self, target_type, target_id, field_name):
            return OverrideStatus(
                field_name=field_name,
                source="manual",
                last_manual_value=None,
                last_manual_at=None,
                current_auto_value=None,
            )

        def create_batch(self, target_type, target_id, batch, reason=None):
            captured["batch"] = batch
            return batch

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)

    message = service.save_uncertainty_review(
        str(brief.id),
        route_id,
        {
            "uncertainty_note": "Adjusted uncertainty note.",
            "reset_uncertainty_note": "on",
            "uncertainty_status": "resolved",
            "reset_uncertainty_status": "on",
            "reason": "Reset uncertainty fields",
        },
    )

    assert message == "Uncertainty review saved."
    edits = captured["batch"]
    assert edits[0].new_value == review_service_db.RESET_TO_AUTO_SENTINEL
    assert edits[1].new_value == review_service_db.RESET_TO_AUTO_SENTINEL

def test_review_page_renders_uncertainty_review_card(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    brief = _build_brief_with_uncertainties()
    target_id = uuid.uuid4()
    edit = ReviewEdit(
        id=uuid.uuid4(),
        target_type="uncertainty",
        target_id=target_id,
        field_name="uncertainty_note",
        old_value='"Provider lock-in remains unclear."',
        new_value='"Manual uncertainty note."',
        reviewer="owner",
        reason="manual override",
        created_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(
        web_routes.service,
        "list_review_uncertainties",
        lambda: (
            [
                UncertaintyReviewView(
                    brief=brief,
                    uncertainty_item=brief.uncertainties[0],
                    item_id="uncertainty-item-1",
                    route_id=str(target_id),
                    target_id=target_id,
                    auto_values={"uncertainty_note": "Provider lock-in remains unclear.", "uncertainty_status": None},
                    effective_values={"uncertainty_note": "Manual uncertainty note.", "uncertainty_status": None},
                    history=[edit],
                )
            ],
            None,
        ),
    )
    monkeypatch.setattr(web_routes.service, "list_review_risks", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_opportunities", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_documents", lambda: ([], None))

    client = TestClient(create_app())
    response = client.get("/web/review")

    assert response.status_code == 200
    assert "不确定性审阅" in response.text
    assert "生效值" in response.text
    assert "审阅历史" in response.text
    assert "Provider lock-in remains unclear." in response.text
    assert '<option value="__UNCHANGED__" selected>-- 保持自动值 / 不做人工覆盖 --</option>' in response.text
    assert '<option value="open" selected>' not in response.text
    assert "name=\"reset_uncertainty_note\"" in response.text
    assert "name=\"reset_uncertainty_status\"" in response.text
    assert f"action=\"/web/review/uncertainties/{brief.id}/{target_id}?lang=zh\"" in response.text

def test_review_page_renders_empty_state_with_shared_review_language(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    monkeypatch.setattr(web_routes.service, "list_review_uncertainties", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_risks", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_opportunities", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_documents", lambda: ([], None))

    client = TestClient(create_app())
    response = client.get("/web/review")

    assert response.status_code == 200
    assert "暂无审阅项。" in response.text

def test_review_page_renders_shared_database_note(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    monkeypatch.setattr(web_routes.service, "list_review_uncertainties", lambda: ([], "Database session unavailable."))
    monkeypatch.setattr(web_routes.service, "list_review_risks", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_opportunities", lambda: ([], None))
    monkeypatch.setattr(web_routes.service, "list_review_documents", lambda: ([], None))

    client = TestClient(create_app())
    response = client.get("/web/review")

    assert response.status_code == 200
    assert "数据库提示:" in response.text
    assert "部分页面数据暂不可用。" in response.text
    assert "Database session unavailable." in response.text

def test_review_page_submit_uncertainty_includes_reset_flags(monkeypatch, workspace_tmp_path: Path) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    captured: dict[str, object] = {}
    brief_id = str(uuid.uuid4())
    route_id = str(uuid.uuid4())

    def _save(brief_id_arg: str, route_id_arg: str, form: dict[str, str]) -> str:
        captured["brief_id"] = brief_id_arg
        captured["route_id"] = route_id_arg
        captured["form"] = form
        return "Uncertainty review saved."

    monkeypatch.setattr(web_routes.service, "save_uncertainty_review", _save)

    client = TestClient(create_app())
    response = client.post(
        f"/web/review/uncertainties/{brief_id}/{route_id}",
        data={
            "uncertainty_note": "Adjusted uncertainty note.",
            "reset_uncertainty_note": "on",
            "uncertainty_status": "resolved",
            "reset_uncertainty_status": "on",
            "reason": "Reset uncertainty fields",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert captured["brief_id"] == brief_id
    assert captured["route_id"] == route_id
    assert captured["form"]["reset_uncertainty_note"] == "on"
    assert captured["form"]["reset_uncertainty_status"] == "on"

def test_review_page_submit_uncertainty_placeholder_preserves_form_and_skips_status_edit(
    monkeypatch,
    workspace_tmp_path: Path,
) -> None:
    _configure_web_storage(monkeypatch, workspace_tmp_path)
    service = WebMvpService()
    brief = _build_brief_with_uncertainties()
    write_session = _FakeWriteSession(brief=brief)
    captured: dict[str, object] = {}
    route_id = str(
        service._build_daily_brief_uncertainty_target_id(
            brief.id,
            f"{service._build_daily_brief_uncertainty_item_id(brief.uncertainties[0])}:0",
        )
    )

    monkeypatch.setattr(service, "_require_session", lambda: write_session)

    class FakeDatabaseReviewService:
        def __init__(self, session):
            self.session = session

        def get_effective_value(self, target_type, target_id, field_name, auto_value=None):
            current = {
                "uncertainty_note": "Provider lock-in remains unclear.",
                "uncertainty_status": None,
            }
            return current[field_name]

        def get_override_status(self, target_type, target_id, field_name):
            return OverrideStatus(
                field_name=field_name,
                source="auto",
                last_manual_value=None,
                last_manual_at=None,
                current_auto_value=None,
            )

        def create_batch(self, target_type, target_id, batch, reason=None):
            captured["batch"] = batch
            return batch

    def _save(brief_id_arg: str, route_id_arg: str, form: dict[str, str]) -> str:
        captured["brief_id"] = brief_id_arg
        captured["route_id"] = route_id_arg
        captured["form"] = form
        return service.save_uncertainty_review(brief_id_arg, route_id_arg, form)

    monkeypatch.setattr("src.web.service.DatabaseReviewService", FakeDatabaseReviewService)
    monkeypatch.setattr(web_routes.service, "save_uncertainty_review", _save)

    client = TestClient(create_app())
    response = client.post(
        f"/web/review/uncertainties/{brief.id}/{route_id}",
        data={
            "uncertainty_note": "Adjusted uncertainty note.",
            "uncertainty_status": "__UNCHANGED__",
            "reason": "Uncertainty note only",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert captured["brief_id"] == str(brief.id)
    assert captured["route_id"] == route_id
    assert captured["form"]["uncertainty_note"] == "Adjusted uncertainty note."
    assert captured["form"]["uncertainty_status"] == "__UNCHANGED__"
    edits = captured["batch"]
    assert [edit.field_name for edit in edits] == ["uncertainty_note"]

def test_database_review_service_create_batch_is_atomic_for_uncertainty() -> None:
    session = _FakeAtomicSession()
    service = DatabaseReviewService(session)

    with pytest.raises(InvalidReviewError):
        service.create_batch(
            "uncertainty",
            uuid.uuid4(),
            [
                ReviewEditCreate(field_name="uncertainty_note", new_value="Updated note", old_value="Auto note"),
                ReviewEditCreate(field_name="summary_zh", new_value="invalid for uncertainty"),
            ],
        )

    assert session.commit_count == 0
    assert session.persisted == []
