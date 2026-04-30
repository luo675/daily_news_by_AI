# Web MVP Bilingual Switch Task

## Current Status

Phase 1 is now implemented and accepted for the current Web MVP shell copy baseline.

Completed:

- lightweight page-layer i18n helper in `src/web/i18n.py`
- language resolution rule:
  - URL `lang`
  - cookie fallback
  - default `zh`
- shared page-layer language context injection in `src/api/app.py`
- shared page layout language switching in `src/api/routes/web.py`
- major shell-copy localization for:
  - `Dashboard`
  - `Documents`
  - `Document Detail`
  - `Sources`
  - `Review`
  - `Ask`
  - `Watchlist`
  - `AI Settings`
  - `System`
- Ask evidence fallback shell copy is localized for missing title/snippet cases
- `/web` entry redirect preserves the resolved language explicitly
- Ask status styling is based on raw `answer_mode`, not translated labels
- route-level and page tests updated for default Chinese UI shell copy

Not completed:

- any content translation behavior
- any heavier i18n framework or frontend rewrite

## Goal

Add a stable Chinese / English UI switch for the Web MVP.

The first pass is page-layer internationalization, not content translation.

## Scope

- `Dashboard`
- `Documents`
- `Sources`
- `Review`
- `Ask`
- `Watchlist`
- `AI Settings`
- `System`

## What should switch

- navigation labels
- page titles
- button text
- table headers
- empty states
- degraded-state notes
- helper / status text

## What should not switch automatically

- source content
- document titles
- summaries
- entity/topic names
- review data

Those should remain source-of-truth text unless a later task explicitly defines a translation policy.

## Constraints

- Prefer server-rendered page-layer i18n.
- Keep the current page contracts stable.
- Do not modify `src/application/*`, `src/domain/*`, or `src/processing/*` in the first pass.
- Preserve the current page path and context when switching language.

## Suggested implementation shape

- introduce a language selector or `lang` query parameter
- centralize page copy in a small translation helper or dictionary
- keep the default language explicit
- make the switch repeatable across all Web MVP pages

## Acceptance boundary

- UI copy can be rendered in Chinese or English
- switching language does not lose the current page context
- page contracts remain stable
- the task does not become a full content translation system

## Verified behavior

- default page language is `zh`
- explicit `?lang=en` switches the page shell copy to English
- valid language selection persists through cookie
- language switch links preserve current page path and query while overriding `lang`
- `Ask` page shell copy is fully wired through the shared helper pattern
- `Watchlist`, `AI Settings`, and `System` shell copy are wired through the shared helper pattern
- `/web?lang=en` redirects to `/web/dashboard?lang=en`
- cookie fallback keeps `/web` redirect language-aware
- fallback evidence title/snippet shell copy switches by language
- `pytest -q` currently reports `108 passed`

## Recommended Next Step

Do not continue localization cleanup as the default next task. Treat the Web page-layer bilingual shell-copy baseline as complete for the current MVP.

Recommended next Web/product step:

1. pick a new focused page-quality task on top of the stable baseline
2. keep the task small and page-scoped
3. update route-level smoke coverage only where it protects an existing contract

Keep the following boundary unchanged:

- do not translate knowledge content
- do not modify `src/application/*`
- do not modify `src/domain/*`
- do not modify `src/processing/*`

## Follow-up decision

If content translation is needed later, define it as a separate task with explicit rules for which fields can be translated and how translated text is stored or displayed.
