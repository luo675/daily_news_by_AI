# Ask Reviewed Evidence Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Ask/Q&A prefer reviewed opportunities, risks, and uncertainties in local evidence while keeping the existing retrieval-first boundary.

**Architecture:** Keep `WebMvpService.ask_question()` as the orchestration point. Add a second local retrieval path for `DailyBrief`, then enrich document and brief evidence with effective reviewed values through `DatabaseReviewService`, falling back to automatic values when no review exists.

**Tech Stack:** FastAPI, SQLAlchemy ORM, pytest

---

### Task 1: Add failing Ask tests for reviewed evidence priority

**Files:**
- Modify: `tests/test_web_ask.py`
- Test: `tests/test_web_ask.py`

- [ ] Add failing tests for reviewed opportunity evidence priority.
- [ ] Add failing tests for brief risk/uncertainty evidence priority and auto fallback.
- [ ] Add a failing route render test for non-document evidence in Ask result output.
- [ ] Run targeted Ask tests and confirm the new cases fail for the expected reason.

### Task 2: Implement reviewed-first Ask evidence assembly

**Files:**
- Modify: `src/web/service.py`

- [ ] Add minimal `DailyBrief` retrieval for Ask using existing term-matching style.
- [ ] Enrich document evidence with reviewed opportunity effective values via `OpportunityAssessment`.
- [ ] Build brief evidence from `DailyBrief.risks` and `DailyBrief.uncertainties`, applying reviewed effective values.
- [ ] Merge document and brief evidence, preserve local-only and bounded external-AI behavior, and keep automatic fallback when no review exists.

### Task 3: Keep Ask result rendering compatible

**Files:**
- Modify: `src/api/routes/web.py`
- Test: `tests/test_web_ask.py`

- [ ] Make Ask result evidence rendering tolerate brief evidence items that do not have a document detail link.
- [ ] Keep page changes minimal and text-only.

### Task 4: Verify the Ask regression surface

**Files:**
- Modify: `tests/test_web_ask.py`
- Optional: `scripts/verify_review.py`

- [ ] Run targeted Ask tests until green.
- [ ] Run the existing Ask baseline tests to confirm no regression.
- [ ] Update a verification script only if the new behavior cannot be covered cleanly in pytest.
