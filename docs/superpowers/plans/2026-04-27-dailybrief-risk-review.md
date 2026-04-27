# DailyBrief Risk Review Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Review web flow so a human can review one `DailyBrief.risks` item at a time using `review_edits` overrides instead of mutating the stored `DailyBrief.risks` JSON.

**Architecture:** Treat each risk item inside `DailyBrief.risks` as a review target. Build a stable `item_id` from `title + description + severity` when one is not already present, derive a stable UUID target id from `brief_id + item_id`, and store manual edits in `review_edits` with `target_type="risk"`. The Review page renders automatic risk values side-by-side with effective values and reset-to-auto controls.

**Tech Stack:** FastAPI, SQLAlchemy ORM, server-rendered HTML, existing `DatabaseReviewService`, pytest, lightweight verification script

---

## Chunk 1: Verification First

### Task 1: Add failing tests for the risk review loop

**Files:**
- Modify: `tests/test_web_review_opportunities.py`

- [ ] **Step 1: Write failing tests for risk display**

Cover:
- risk items read from `DailyBrief.risks`
- stable `item_id` / derived target id
- automatic values and effective values rendered on the Review page

- [ ] **Step 2: Write failing tests for submit and reset**

Cover:
- POST submit for one risk item
- explicit `reset_severity` and `reset_description`
- reset leading back to automatic values

- [ ] **Step 3: Write failing tests for atomic submission**

Cover:
- one invalid risk field in a batch causes no commit

- [ ] **Step 4: Run tests to confirm failure**

Run: `pytest tests/test_web_review_opportunities.py -q`
Expected: FAIL because risk review helpers and page wiring do not exist yet.

## Chunk 2: Service Layer

### Task 2: Add DailyBrief risk review helpers

**Files:**
- Modify: `src/web/service.py`

- [ ] **Step 1: Add minimal risk review helper structures**

Create a small internal view/helper for:
- source `DailyBrief`
- one risk item
- stable `item_id`
- stable derived UUID target id
- automatic values
- effective values
- review history

- [ ] **Step 2: Add list/read helpers**

Implement helpers to:
- list recent `DailyBrief` rows with risk items
- compute effective `severity` / `description`
- derive stable target ids from `brief_id + item_id`

- [ ] **Step 3: Add save helper**

Implement `save_risk_review(brief_id, item_id, form)` that:
- finds the exact risk item inside the brief
- compares submitted values against current effective values
- writes only changed fields to `review_edits`
- supports explicit reset-to-auto
- never mutates `DailyBrief.risks`

- [ ] **Step 4: Re-run tests**

Run: `pytest tests/test_web_review_opportunities.py -q`
Expected: service-level risk tests pass or remaining failures are isolated to route/page rendering.

## Chunk 3: Review Page

### Task 3: Render risk cards and wire POST route

**Files:**
- Modify: `src/api/routes/web.py`

- [ ] **Step 1: Render risk review cards**

Add a risks section to `/web/review` with:
- risk title read-only
- brief id and item id
- automatic `severity` / `description`
- editable effective values
- reset-to-auto checkboxes
- recent audit history

- [ ] **Step 2: Add submit route**

Add POST route for one risk item, passing `brief_id` and `item_id` to the service save helper.

- [ ] **Step 3: Keep the interaction minimal**

Use plain form POST + redirect only. No JavaScript or broader review architecture changes.

## Chunk 4: Final Verification

### Task 4: Verify the full risk review loop

**Files:**
- Modify: `scripts/verify_review.py`

- [ ] **Step 1: Extend or adapt verification script**

Add a focused risk verification path that proves:
- automatic risk source is read correctly
- manual overrides display correctly
- reset returns to automatic values
- audit records remain in `review_edits`

- [ ] **Step 2: Run verification**

Run:
- `python scripts/verify_review.py`
- `pytest tests/test_web_review_opportunities.py -q`

Expected:
- verification script PASS
- risk review tests PASS

- [ ] **Step 3: Note residual risk**

Call out that this iteration covers only `DailyBrief.risks`, not uncertainties or any new persistence model.
