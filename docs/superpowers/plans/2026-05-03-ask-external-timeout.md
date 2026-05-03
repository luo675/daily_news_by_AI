# Ask External Timeout Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Increase Ask's external chat/completions read timeout to 60 seconds while preserving existing fallback behavior and keeping AI Settings tests unchanged.

**Architecture:** Touch only the Ask provider call in `src/web/service.py`. Keep evidence assembly, retrieval-first behavior, and provider test timeout untouched. Add or update a focused Ask test to prove the external call uses the new timeout and still falls back cleanly on provider failure.

**Tech Stack:** Python, pytest, SQLAlchemy-backed web service helpers.

---

### Task 1: Update Ask timeout

**Files:**
- Modify: `src/web/service.py`

- [ ] **Step 1: Change the Ask chat/completions timeout**

Update the `request.urlopen(..., timeout=25)` call in the Ask external answer path to `timeout=60`.

- [ ] **Step 2: Keep AI Settings provider test timeout unchanged**

Do not modify the `/models` provider test timeout in the AI Settings test path.

- [ ] **Step 3: Preserve fallback behavior**

Leave the existing exception handling so provider failures still fall back to `local_fallback` and record the original timeout/error message.

### Task 2: Verify with tests

**Files:**
- Modify: `tests/test_web_ask.py`

- [ ] **Step 1: Add or update a test for Ask timeout**

Cover that the Ask external request uses a 60 second timeout.

- [ ] **Step 2: Add or update a fallback test**

Cover that a provider exception still produces `local_fallback` and preserves the error string.

- [ ] **Step 3: Run the relevant pytest targets**

Run focused `tests/test_web_ask.py` cases first, then the related Web MVP smoke/acceptance tests.

