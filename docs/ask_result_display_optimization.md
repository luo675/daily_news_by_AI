# Ask Result Display Optimization

## Goal

Improve `/web/ask` result readability without changing Ask retrieval logic, provider routing, or storage behavior.

This is a presentation-only follow-up task.

## Current Problem

The current Ask result page is functionally correct, but the output is still dense:

- answer metadata is mixed into the same visual block as the answer body
- evidence items are shown as a flat list
- users cannot quickly distinguish result status, answer body, and evidence quality
- history cards on `/web/ask` are useful but too compressed to support quick scanning of recent outcomes

## Design Direction

Keep the existing two-column layout, but make the result state easier to scan.

### Left column: Answer summary

Split the current answer panel into four sections:

1. Question
2. Answer
3. Run metadata
4. Error state, only when present

Run metadata should remain compact and explicit:

- `mode`
- `provider`
- `note`
- `created_at` when available

### Right column: Evidence summary

Replace the current plain evidence list with card-like evidence rows.

Each evidence row should show:

- title
- source type: document or brief
- short snippet or summary
- optional match basis when available

Document evidence should keep links.
Brief evidence should stay non-link text unless a real target page exists.

## Display Rules

- If `answer_mode=insufficient_local_evidence`, visually mark the result as incomplete rather than normal success.
- If `answer_mode=local_fallback`, show a small warning-style status line because external provider failed but local answer still exists.
- If `error` is empty, do not reserve visible space for it.
- If `evidence` is empty, show a short explicit empty-state message instead of a blank list.
- Preserve the current local-first wording; do not market the page as advanced RAG.

## History List Optimization

For `/web/ask` history cards:

- keep recent question as the title
- show one compact metadata line with `mode`, `provider`, and `created_at`
- show `note` only when non-empty
- truncate long answer bodies in history view, but keep full answer on result view

## Non-goals

- no retrieval change
- no evidence ranking change
- no provider routing change
- no AI prompt change
- no storage change
- no new review target

## Suggested Implementation Slice

If implemented next, keep it to:

- `src/api/routes/web.py`
- maybe one or two small formatting helpers in `src/web/service.py` only if strictly needed
- targeted tests for Ask page rendering

## Acceptance For Next Task

The next implementation task should be considered complete when:

- `/web/ask` result page is easier to scan
- metadata, answer body, and evidence are visually separated
- existing Ask behavior stays unchanged
- existing Ask tests still pass
- new rendering tests cover the updated layout and status presentation
