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

## Ask Result Contract

This section freezes the current lightweight contract for the `/web/ask` result view.

Scope:

- this is a page rendering contract for `src/api/routes/web.py`
- this is not a unified API schema redesign
- this does not change Ask retrieval, provider routing, or history storage

### Result View: Required Fields

The Ask result page currently requires these fields to exist on the object returned by `service.ask_question()`:

- `question`
  - used as the left-column question block
  - if missing: rendering is not contract-safe
- `answer`
  - used as the left-column answer block
  - if missing: rendering is not contract-safe

These are the only hard-required fields for the result page itself.

### Result View: Optional Fields With Stable Downgrade

- `answer_mode`
  - purpose: drives result status line and run metadata
  - downgrade: if missing or empty, the page falls back to `local_only`
- `provider_name`
  - purpose: shown in run metadata
  - downgrade: if missing or empty, render `provider=-`
- `note`
  - purpose: shown in run metadata
  - downgrade: if missing or empty, omit the note line
- `created_at`
  - purpose: shown in run metadata when available
  - downgrade: if missing or empty, omit the created time line
- `error`
  - purpose: shown in `Error State`
  - downgrade: if missing or empty, do not render the error block
- `evidence`
  - purpose: right-column evidence cards
  - downgrade: if missing, `None`, or empty, show explicit evidence empty state
- `opportunities`
  - purpose: optional structured result section
  - downgrade: if missing, `None`, or empty, show `No opportunities extracted.`
- `risks`
  - purpose: optional structured result section
  - downgrade: if missing, `None`, or empty, show `No risks extracted.`
- `uncertainties`
  - purpose: optional structured result section
  - downgrade: if missing, `None`, or empty, show `No uncertainties extracted.`
- `related_topics`
  - purpose: optional structured result section
  - downgrade: if missing, `None`, or empty, show `No related topics extracted.`
- `meta`
  - purpose: optional metadata section
  - downgrade: if missing, not a dict, or empty, show `No metadata available.`

### Evidence Item Contract

Each entry inside `evidence` is treated as an evidence item. The page is tolerant of partial items.

Expected fields:

- `title`
  - preferred evidence label
  - downgrade: if missing, render `Untitled evidence`
- `document_id`
  - if present, treat the evidence as document-backed and render a document link
  - if absent, render plain text evidence title
- `evidence_type`
  - optional explicit source type
  - downgrade: infer `document` when `document_id` exists, otherwise infer `brief`
- `snippet`
  - preferred evidence body text
  - downgrade: use `summary`
- `summary`
  - fallback evidence body text
  - downgrade: if both `snippet` and `summary` are empty, render `No snippet available.`
- `match_basis`
  - optional evidence metadata
  - downgrade: omit the line when absent

### Reviewed Evidence Rule

For reviewed evidence, the page contract is:

- the Ask result should display the already-resolved effective value
- the page must not reinterpret review state on its own
- the page does not compute manual-vs-auto precedence
- reviewed opportunities, risks, and uncertainties are expected to arrive inside `evidence[*].summary` or `evidence[*].snippet` already resolved to effective values

That means:

- if a manual override exists, Ask should surface the override
- if reset-to-auto was applied, Ask should surface the automatic value again
- the page only renders what the Ask result object provides

### Page Dependency Split

Fields the page directly depends on:

- hard required: `question`, `answer`
- status + metadata dependency: `answer_mode`, `provider_name`, `note`, `created_at`, `error`
- right-column dependency: `evidence`, `opportunities`, `risks`, `uncertainties`, `related_topics`, `meta`

Fields that are optional enhancements rather than hard dependencies:

- `provider_name`
- `note`
- `created_at`
- `error`
- all structured sections other than `question` and `answer`
- evidence subfields other than a minimally renderable title/body fallback

## Ask History Contract

The `/web/ask` history list uses a separate lightweight contract from `service.list_qa_history()`.

Required by the current history card rendering:

- `question`
- `answer`
- `answer_mode`

Optional with downgrade:

- `provider_name`
  - fallback: `-`
- `created_at`
  - fallback: `-`
- `note`
  - if empty, omit the note line

History rendering keeps the answer truncated in history view and leaves full answer rendering to the result page.
