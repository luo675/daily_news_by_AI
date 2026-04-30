# Web MVP Route-Level Smoke Checklist

Date of latest pass:

- `2026-04-30`

Scope:

- Dashboard
- Documents list/detail
- Sources list/detail/actions
- Watchlist list/create/status
- Review list/save
- Ask page/result
- System / Storage

This checklist is for route-level, service-mocked Web MVP acceptance/smoke coverage.
It verifies that the primary user paths render and submit correctly with stable page contracts.
It does not represent real browser automation, real database integration, or true persistence round-trips.

## Repro Command

Run:

```bash
pytest tests/test_web_mvp_acceptance.py tests/test_web_i18n.py -q
pytest tests/test_web_mvp_acceptance.py tests/test_web_ask.py tests/test_web_review_opportunities.py tests/test_web_dashboard_documents.py -q
```

## Primary Chain

### Dashboard

- [x] `/web/dashboard` renders
- [x] counts render
- [x] recent document summary renders
- [x] system status renders
- [x] smoke assertion checks at least one core content block, not only status code

### Documents

- [x] `/web/documents` renders
- [x] list page uses page-view contract
- [x] filter summary renders
- [x] `/web/documents/{document_id}` renders
- [x] detail page shows stable fallback values
- [x] smoke assertion checks core list/detail content, not only status code

### Sources

- [x] `/web/sources` renders
- [x] source registry uses page-view contract
- [x] `/web/sources/{source_id}` renders
- [x] edit form renders without writing display fallback values into inputs
- [x] toggle action redirects to the expected Sources target
- [x] import action redirects to the expected Sources target

### Watchlist

- [x] `/web/watchlist` renders
- [x] watchlist list page uses page-view contract
- [x] item cards show type, priority, status, group, notes, linked entity, timestamps, and related documents
- [x] empty watchlist state is stable
- [x] database degradation shows the shared database note
- [x] English shell copy renders with `?lang=en`
- [x] create and status-update routes keep existing redirect semantics

### Review

- [x] `/web/review` renders
- [x] empty review state is stable
- [x] save review route redirects to the expected Review target

### Ask

- [x] `/web/ask` renders
- [x] empty history state is stable
- [x] ask submit renders result view
- [x] result empty sections render stable fallback wording
- [x] ask submit smoke assertion checks answer/result content, not only status code

### System / Storage

- [x] `/web/system` renders
- [x] system checks render
- [x] database counts render
- [x] storage file table renders
- [x] counts-only degradation shows shared database note

## Blocking Defects

Current result:

- None found in the current route-level, service-mocked smoke run above.

## Non-Blocking Experience Issues

Current observations:

- Acceptance coverage is route-level and service-mocked; it does not replace a real browser pass against a live database.
- It does not prove real persistence writes, browser behavior, CSS/layout behavior, or end-to-end backend integration.
- The checklist confirms contract stability and primary flow closure, not production data quality or operational latency.

## Current Acceptance Boundary

This checklist intentionally does not validate:

- real browser automation
- real database integration
- true persistence round-trip behavior
- pipeline correctness
- ingestion correctness
- provider quality
- review scoring quality
- end-user browser layout quirks

Those belong to separate verification layers.
