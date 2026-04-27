# Web Local Storage Boundary

## Scope

This document fixes the current storage boundary for the Web MVP's local operational data.

It only covers:

- Ask history
- AI provider config
- Existing Web-only source maintenance metadata

It does not redefine the main knowledge storage model.

## Current Boundary

### 1. Ask history

Ask history is now:

- DB-first
- JSON-fallback

Primary path:

- New Ask records are written to PostgreSQL first.
- Ask history pages read from PostgreSQL first.

Fallback path:

- If DB session creation fails, or Ask history persistence fails during commit, the system falls back to `configs/web/qa_history.json`.
- If Ask history cannot be read from DB, the system falls back to `configs/web/qa_history.json`.

Important non-goal:

- Old `configs/web/qa_history.json` data is not auto-imported into DB.

Current persisted fields:

- `question`
- `answer`
- `answer_mode`
- `provider_name`
- `evidence`
- `error`
- `note`
- `created_at`

### 2. AI provider config

AI provider config is now:

- DB-first
- JSON-fallback

Primary path:

- Provider list reads from PostgreSQL first.
- New provider save and provider edit write to PostgreSQL first.
- Provider test status updates write to PostgreSQL first.

Fallback path:

- If DB session creation fails, or DB write path fails, the system falls back to `configs/web/ai_settings.json`.
- If DB has no provider records or is unavailable, the system falls back to `configs/web/ai_settings.json`.

Important non-goal:

- Old `configs/web/ai_settings.json` data is not auto-imported into DB.

Security boundary kept unchanged:

- API keys are still stored locally.
- The Web page still does not echo plaintext API keys back into edit inputs.
- The UI still shows masked keys only.

### 3. Source maintenance metadata

`Source.config["_web"]` remains in place.

It is still the current carrier for Web-only source maintenance metadata such as:

- `maintenance_status`
- `notes`
- `last_import_at`
- `last_result`

This is intentionally kept as-is and is not part of the current storage migration target.

## Stable Boundaries

The following boundaries should be treated as stable unless a separate task explicitly changes them:

- Do not change `src/application/*` for this Web local storage topic.
- Do not change `src/domain/*` for this Web local storage topic.
- Do not change `src/processing/*` for this Web local storage topic.
- Do not replace the main PostgreSQL + pgvector knowledge storage path.
- Do not introduce a new main storage abstraction layer.
- Do not turn this into a secrets-management project.
- Do not refactor `src/web/service.py` just to make the structure cleaner.
- Do not change Ask provider routing strategy as part of storage-only work.
- Do not change Review architecture as part of storage-only work.

## Re-runnable Verification

### 1. Migration

Run:

```powershell
alembic upgrade head
```

Expected:

- migration succeeds
- both `ask_history_records` and `ai_provider_configs` exist in PostgreSQL

### 2. Automated tests

Run:

```powershell
pytest tests\test_web_ask.py
pytest tests\test_web_review_opportunities.py
```

Expected:

- Ask history DB-first tests pass
- Ask history JSON fallback tests pass
- AI provider DB-first tests pass
- AI provider JSON fallback tests pass
- Review regression tests still pass

### 3. Manual verification: Ask history

Steps:

1. Open `/web/ask`
2. Submit a unique question
3. Confirm the result page renders normally
4. Go back to `/web/ask`
5. Confirm the new history item is visible

Expected:

- Ask still works
- new record is shown in history
- normal flow does not depend on old JSON files

### 4. Manual verification: AI provider config

Steps:

1. Open `/web/ai-settings`
2. Create a provider
3. Confirm the provider appears in the provider list
4. Open the provider detail page
5. Confirm the saved key is masked, not echoed as plaintext
6. Open `/web/ask`
7. Confirm the provider can still appear in the provider selector under the current rules

Expected:

- provider config is readable after save
- Ask still uses the same provider selection behavior
- UI behavior is unchanged

### 5. Fallback verification

Ask history fallback:

1. Make DB unavailable
2. Ensure `configs/web/qa_history.json` contains at least one valid record
3. Open `/web/ask`

Expected:

- page still renders
- legacy JSON history still appears

Provider fallback:

1. Make DB unavailable
2. Ensure `configs/web/ai_settings.json` contains at least one valid provider record
3. Open `/web/ai-settings`

Expected:

- page still renders
- legacy JSON provider still appears

## Operational Note

Current intent is compatibility, not migration completion.

That means:

- DB is the preferred storage boundary
- JSON remains a compatibility and failure fallback
- legacy JSON is tolerated
- legacy JSON is not automatically normalized into DB
