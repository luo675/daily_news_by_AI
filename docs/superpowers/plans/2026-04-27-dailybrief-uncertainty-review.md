# DailyBrief Uncertainty Review Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Review web flow so a human can review one `DailyBrief.uncertainties` item at a time using `review_edits` overrides instead of mutating the stored `DailyBrief.uncertainties` JSON.

**Architecture:** Treat each uncertainty item inside `DailyBrief.uncertainties` as a review target. Build a stable internal `item_id` from the uncertainty text plus duplicate occurrence index, derive a stable UUID `target_id`, use its string form as URL-safe `route_id`, and store manual edits in `review_edits` with `target_type="uncertainty"`. The Review page renders automatic uncertainty values side-by-side with effective values and reset-to-auto controls.

**Tech Stack:** FastAPI, SQLAlchemy ORM, server-rendered HTML, existing `DatabaseReviewService`, pytest, lightweight verification script

---

## Chunk 1: Verification First

### Task 1: Add failing tests for the uncertainty review loop

**Files:**
- Modify: `tests/test_web_review_opportunities.py`

- [ ] **Step 1: Write failing tests for uncertainty display**

Cover:
- uncertainty items read from `DailyBrief.uncertainties`
- stable `item_id` / derived `target_id`
- automatic values and effective values rendered on the Review page

- [ ] **Step 2: Write failing tests for submit and reset**

Cover:
- POST submit for one uncertainty item
- explicit `reset_uncertainty_note` and `reset_uncertainty_status`
- reset leading back to automatic values

- [ ] **Step 3: Write failing tests for duplicate items**

Cover:
- same brief containing duplicate uncertainty strings produces distinct targets

- [ ] **Step 4: Run tests to confirm failure**

Run: `pytest tests/test_web_review_opportunities.py -q`
Expected: FAIL because uncertainty review helpers and page wiring do not exist yet.

## Chunk 2: Service Layer

### Task 2: Add DailyBrief uncertainty review helpers

**Files:**
- Modify: `src/web/service.py`

- [ ] **Step 1: Add minimal uncertainty review helper structures**

Create a small internal view/helper for:
- source `DailyBrief`
- one uncertainty item
- stable `item_id`
- stable derived UUID `target_id`
- URL-safe `route_id`
- automatic values
- effective values
- review history

- [ ] **Step 2: Add list/read helpers**

Implement helpers to:
- list recent `DailyBrief` rows with uncertainty items
- compute effective `uncertainty_note` / `uncertainty_status`
- derive stable target ids from `brief_id + item_id`

- [ ] **Step 3: Add save helper**

Implement `save_uncertainty_review(brief_id, route_id, form)` that:
- finds the exact uncertainty item inside the brief
- compares submitted values against current effective values
- writes only changed fields to `review_edits`
- supports explicit reset-to-auto
- never mutates `DailyBrief.uncertainties`

- [ ] **Step 4: Re-run tests**

Run: `pytest tests/test_web_review_opportunities.py -q`
Expected: service-level uncertainty tests pass or remaining failures are isolated to route/page rendering.

## Chunk 3: Review Page

### Task 3: Render uncertainty cards and wire POST route

**Files:**
- Modify: `src/api/routes/web.py`

- [ ] **Step 1: Render uncertainty review cards**

Add an uncertainties section to `/web/review` with:
- automatic uncertainty text read-only
- brief id and item id
- editable effective `uncertainty_note` / `uncertainty_status`
- reset-to-auto checkboxes
- recent audit history

- [ ] **Step 2: Add submit route**

Add POST route for one uncertainty item, passing `brief_id` and `route_id` to the service save helper.

- [ ] **Step 3: Keep the interaction minimal**

Use plain form POST + redirect only. No JavaScript or broader review architecture changes.

## Chunk 4: Final Verification

### Task 4: Verify the full uncertainty review loop

**Files:**
- Modify: `scripts/verify_review.py`

- [ ] **Step 1: Extend verification script**

Add a focused uncertainty verification path that proves:
- automatic uncertainty source is read correctly
- manual overrides display correctly
- reset returns to automatic values
- audit records remain in `review_edits`

- [ ] **Step 2: Run verification**

Run:
- `python scripts/verify_review.py`
- `pytest tests/test_web_review_opportunities.py tests/test_web_ask.py -q`

Expected:
- verification script PASS
- uncertainty review tests PASS

- [ ] **Step 3: Note residual risk**

Call out that this iteration covers only `DailyBrief.uncertainties`, not any new persistence model or conflict binding.
