# Opportunity Review Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Review web flow so a human can review and revise one `OpportunityAssessment` at a time using `review_edits` overrides instead of mutating the auto-generated opportunity record.

**Architecture:** Keep `OpportunityAssessment` read-only and store manual edits in `review_edits` with `target_type="opportunity_score"` and `target_id=<opportunity_id>`. Build effective display values in `src/web/service.py`, render them on the Review page, and submit edits through a dedicated web route that writes only changed fields.

**Tech Stack:** FastAPI, SQLAlchemy ORM, server-rendered HTML, existing `DatabaseReviewService`, Python verification script

---

## Chunk 1: Verification First

### Task 1: Add a focused opportunity review verification script

**Files:**
- Modify: `scripts/verify_review.py`

- [ ] **Step 1: Write the failing verification case**

Add a new verification path that:
- creates one `OpportunityAssessment`
- reads its automatic values
- writes manual edits through the web service path
- reloads effective values
- asserts manual values override display values
- asserts the base `OpportunityAssessment` row remains unchanged
- asserts `review_edits` history exists

- [ ] **Step 2: Run verification to confirm failure**

Run: `python scripts/verify_review.py`
Expected: FAIL because the web service does not yet expose opportunity review save/load behavior.

- [ ] **Step 3: Keep the verification minimal**

Reuse existing script style and only add the assertions needed for the opportunity review loop.

## Chunk 2: Service Layer

### Task 2: Add read and write helpers for opportunity review

**Files:**
- Modify: `src/web/service.py`

- [ ] **Step 1: Add opportunity imports and small helper structures**

Load `OpportunityAssessment` and define a small internal view/helper for:
- auto values
- effective values
- review history

- [ ] **Step 2: Implement review read helpers**

Add helpers to:
- list recent review documents with opportunities preloaded
- get review history for one opportunity target
- compute effective opportunity field values with `DatabaseReviewService.get_effective_value()`

- [ ] **Step 3: Implement save helper**

Add a `save_opportunity_review(opportunity_id, form)` method that:
- loads the target opportunity
- compares submitted values against current effective values
- writes only changed fields to `review_edits`
- never updates the `OpportunityAssessment` row

- [ ] **Step 4: Run verification for service behavior**

Run: `python scripts/verify_review.py`
Expected: service-side assertions move closer to passing, with any remaining failure isolated to route/page wiring.

## Chunk 3: Review Page

### Task 3: Extend the Review page and submit route

**Files:**
- Modify: `src/api/routes/web.py`

- [ ] **Step 1: Render opportunities ahead of summaries**

On `/web/review`, show each opportunity as its own review card with:
- immutable automatic values
- editable effective values
- reason field
- recent audit entries

- [ ] **Step 2: Add a dedicated submit route**

Add a POST route like `/web/review/opportunities/{opportunity_id}` that calls `save_opportunity_review()`.

- [ ] **Step 3: Keep the interaction minimal**

Use ordinary form POST + redirect only. No JavaScript, partial rendering, or new page architecture.

## Chunk 4: Final Verification

### Task 4: Verify the full loop

**Files:**
- Modify: `scripts/verify_review.py`

- [ ] **Step 1: Run the verification script**

Run: `python scripts/verify_review.py`
Expected: PASS for the new opportunity review loop checks.

- [ ] **Step 2: Run targeted pytest if needed**

Run: `pytest tests/test_web_ask.py -q`
Expected: PASS, giving a light regression check for the existing web flow.

- [ ] **Step 3: Summarize residual risk**

Call out that this iteration covers opportunities only and does not yet generalize to risks or uncertainties.
