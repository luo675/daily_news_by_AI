# Web MVP Browser Smoke Checklist

Date of latest pass:

- `2026-05-02`

Result summary:

- Passed with local Edge headless browser smoke checks against `uvicorn src.api.app:create_app --factory --reload`.
- Verified `/web/dashboard`, `/web/documents`, `/web/sources`, `/web/review`, `/web/watchlist`, `/web/ask`, `/web/ai-settings`, and `/web/system`.
- Confirmed default Chinese shell copy and `?lang=en` English shell copy on the listed pages.
- Confirmed AI Settings list and edit pages only exposed masked keys, not plaintext `api_key` values.
- Watchlist was in empty-state mode during smoke; the create form rendered and the page remained navigable.

Scope:

- `/web/dashboard`
- `/web/documents`
- `/web/sources`
- `/web/review`
- `/web/watchlist`
- `/web/ask`
- `/web/ai-settings`
- `/web/system`

This checklist is for a minimal real-browser smoke pass against the Web MVP.
It verifies that the page shell opens in a browser, the main navigation works, and the most important page-level affordances are visible.
It is not a full end-to-end test.
It does not validate real business data quality, ingestion correctness, provider quality, or production-grade persistence behavior.

## Boundary

### Route-level smoke

Route-level smoke is the fast, service-mocked coverage already present in `tests/`.
It checks page contracts and redirect behavior without using a real browser.

### Browser smoke

Browser smoke is this checklist.
It checks that the server-rendered pages can open and be navigated in a real browser session.
It should use local app startup only.

### Real DB / integration

Real DB / integration verification is a separate layer.
It is only needed when you want to confirm actual persistence, live database state, or external provider behavior.
This checklist does not replace that layer.

## Local Start

Use the existing FastAPI app factory and local virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn src.api.app:create_app --factory --reload
```

Then open:

- `http://127.0.0.1:8000/web`

If you want to pin English shell copy during manual inspection, append `?lang=en` to the relevant page URL.

## Smoke Pass

Complete the following in a real browser:

1. Open `/web/dashboard`.
1. Confirm the page returns `200` in the browser and the shell loads.
1. Click the main navigation links and confirm they open the expected pages.
1. Repeat the same for `/web/documents`, `/web/sources`, `/web/review`, `/web/watchlist`, `/web/ask`, `/web/ai-settings`, and `/web/system`.
1. Open each page with `?lang=en` at least once and confirm the shell copy switches to English.
1. Return to the default language pages and confirm the shell copy is Chinese.

## Page Checks

### Dashboard

- The page opens without a blank screen.
- The top navigation is visible and clickable.
- The main content area renders at least one dashboard section.

### Documents

- The list page opens.
- If documents exist, the detail route is reachable from the list page and the detail view opens.
- If no documents exist, the empty state renders and the page remains navigable back to the list.

### Sources

- The list page opens.
- If sources exist, the detail page is reachable from the list page and the detail view opens.
- If no sources exist, the empty state renders and the page remains navigable back to the list.

### Review

- The review page opens.
- The filter links are visible.
- The page remains navigable after selecting a filter link.

### Watchlist

- The page opens.
- The create form is visible.
- If watchlist items exist, the item cards are visible.
- If no watchlist items exist, the empty state renders.
- The page remains navigable through the main nav.

### Ask

- The page opens.
- The Ask form is visible.
- The provider select is visible if providers are configured.

### AI Settings

- The list page opens.
- The configured provider table is visible if providers exist.
- No plaintext API key is visible in the rendered page.
- The edit page opens from the list page and still does not show a plaintext key.

### System

- The page opens.
- The storage overview and system checks are visible.

## Minimal Navigation Matrix

Check these links from the browser shell:

- `Dashboard` -> `/web/dashboard`
- `Documents` -> `/web/documents`
- `Sources` -> `/web/sources`
- `Review` -> `/web/review`
- `Watchlist` -> `/web/watchlist`
- `Ask` -> `/web/ask`
- `AI Settings` -> `/web/ai-settings`
- `System` -> `/web/system`

For each page, verify the browser keeps working after a navigation click and does not land on an error page.

## Acceptance Notes

Pass criteria:

- every listed page opens in a browser session
- the main navigation is clickable
- `?lang=en` shows the English shell copy
- default pages show Chinese shell copy
- AI Settings does not reveal plaintext `api_key`
- Ask shows its form controls
- Review shows its filter links

Fail criteria:

- blank page
- server error page
- broken navigation link
- English shell not switching under `?lang=en`
- plaintext key exposure on AI Settings
- missing Ask form or Review filters

## Suggested Verification Flow

1. Run the local app with the command above.
1. Open `/web/dashboard`.
1. Click through the main nav to each target page.
1. Re-open each target page with `?lang=en`.
1. On AI Settings, confirm only masked keys are shown.
1. On Ask, confirm the form is present.
1. On Review, confirm filter links are present.
1. Record any broken page, missing shell copy, or key exposure before treating the pass as complete.

## Explicit Non-Goals

- full Playwright automation
- cross-browser compatibility matrix
- visual regression testing
- real provider invocation
- real database migration validation
- ingestion or ranking correctness
- business-data completeness checks
