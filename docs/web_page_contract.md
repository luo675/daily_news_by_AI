# Web Page Contract

## Scope

This note records the current page-layer contract for the server-rendered Web MVP pages:

- `GET /web/dashboard`
- `GET /web/documents`
- `GET /web/documents/{document_id}`
- `GET /web/sources`
- `GET /web/sources/{source_id}`
- `GET /web/watchlist`
- `GET /web/review`
- `GET /web/ask`
- `POST /web/ask` result view
- `GET /web/system`

This is a page/service assembly contract only.

Non-goals:

- no pipeline change
- no domain model change
- no persistence change
- no new storage path
- no new UI architecture

## Shared Page Rules

### Database Degradation Note

When page data is unavailable because of a DB read failure, page-level notes use:

- `Database note: Some page data is unavailable. <detail>`

This is the shared degraded-state wording for:

- Dashboard
- Documents list/detail
- Sources list
- Review
- System / Storage counts

### Missing Value Fallback

When a field is present in the page contract but the underlying value is blank or missing, the default visible fallback is:

- `-`

Exceptions are page-specific and called out below, such as:

- `Untitled document`
- `Unnamed source`
- `Unnamed entity`
- `Unnamed topic`

### Empty State Style

The current page style uses direct, neutral availability wording:

- `No <items> available.`

When a page has active filters, the empty state should mention the filter context rather than generic absence.

## Dashboard Contract

`WebMvpService.get_dashboard_data()` returns:

- `counts`
  - stable keys: `sources`, `documents`, `watchlist`, `reviews`
  - empty/db failure downgrade: numeric zeroes
- `recent_documents`
  - list items contain:
    - `id`
    - `title`
    - `source_name`
    - `created_at`
    - `published_at`
    - `status`
    - `summary_text`
    - `opportunity_count`
    - `risk_count`
    - `uncertainty_count`
  - summary must prefer reviewed effective summary values
  - time display renders `published_at` first and falls back to `created_at`
  - signal counts are lightweight dashboard hints; unavailable document-level risks render as `0`
  - empty state: `[]`, rendered as `No recent documents available.`
- `system_status`
  - keys:
    - `database_label`
    - `database_detail`
    - `provider_label`
    - `knowledge_label`
  - normal state:
    - `database_label='available'`
    - `database_detail` explains dashboard knowledge/count reads are available
    - `provider_label` summarizes enabled provider state
    - `knowledge_label` uses neutral availability wording for recent documents
  - degraded state:
    - `database_label='degraded'`
    - `database_detail` mirrors the DB error message
    - `knowledge_label='Recent knowledge changes are unavailable.'`
- `top_topics`
  - list of `(name, count)`
  - empty state: `[]`, rendered as `No topics available.`
- `providers`
  - existing provider objects from current storage path
  - empty state: `No providers available.`
- `qa_history`
  - existing ask history records from current storage path
  - empty state: `No recent Q&A available.`
- `db_error`
  - `None` in normal state
  - readable detail string when DB read fails

Dashboard terminology:

- `System Status`
- `Quick Actions`
- `Recent Documents`
- `Signals`
- `Top Topics`
- `AI Providers`
- `Recent Q&A`

Dashboard quick actions:

- `Open Documents` -> `/web/documents`
- `Ask Local Knowledge` -> `/web/ask`
- `Review Queue` -> `/web/review`

## Documents List Contract

`WebMvpService.list_document_views()` returns list items with:

- `id`
- `title`
- `source_name`
- `status`
- `language`
- `published_at`
- `summary_text`
- `key_points`
- `created_at`
- `opportunity_count`
- `risk_count`
- `uncertainty_count`

Downgrade rules:

- blank title -> `Untitled document`
- missing source -> `-`
- missing status/language/published or created time -> `-`
- missing summary text -> try effective `key_points`
- no summary and no key points -> `summary_text='-'`
- unavailable document-level risks -> `risk_count=0`
- empty result set -> `[]`

Documents list rendering rules:

- list column order follows detail-page semantics:
  - `source -> status -> language -> published/created -> summary -> signals -> detail`
- time column renders `published_at` first and falls back to `created_at`
- signals column renders lightweight counts for opportunities, risks, and uncertainties
- detail column links to `/web/documents/{document_id}`
- search form must echo current `q` and `source_id`
- page must show a `Filters currently applied` block
- source filter summary:
  - empty `source_id` -> `All sources`
  - matched `source_id` -> resolved source name
  - unmatched non-empty `source_id` -> `Unknown source filter`
- empty result with filters -> `No documents matched the current filters.`
- empty result without filters -> `No documents available.`
- DB degradation note uses the shared database-note wording

## Document Detail Contract

`WebMvpService.get_document_view()` returns:

- `id`
- `title`
- `source_name`
- `url`
- `status`
- `language`
- `published_at`
- `summary_en`
- `summary_zh`
- `key_points`
- `entities`
- `topics`
- `content_preview`

Downgrade rules:

- blank title -> `Untitled document`
- missing source/status/language/published time -> `-`
- missing URL -> empty string at service layer, rendered as `-`
- missing summary object -> empty `summary_en`, `summary_zh`, `key_points`
- blank label fallback:
  - entity relation exists but label is blank -> `Unnamed entity`
  - topic relation exists but label is blank -> `Unnamed topic`
- empty collection state:
  - no entity relations -> `entities=[]`, rendered as `No entities.`
  - no topic relations -> `topics=[]`, rendered as `No topics.`
- missing content -> empty `content_preview`, rendered as `-`
- DB degradation note uses the shared database-note wording when detail data is partially unavailable
- document not found -> stable not-found card, not an exception trace

## Sources Contract

`WebMvpService.list_source_page_views()` returns list items with:

- `id`
- `name`
- `editable_name`
- `source_type`
- `url`
- `credibility_level`
- `fetch_strategy`
- `is_active`
- `activity_label`
- `maintenance_status`
- `notes`
- `last_import_at`
- `last_result`
- `web_metadata`
- `raw_config_json`

`WebMvpService.get_source_page_view()` returns the same field set for the detail page.

Downgrade rules:

- blank source name -> `Unnamed source`
- blank source name keeps `editable_name=''` so detail-form inputs do not write display fallbacks back into source data
- missing URL / fetch strategy / last import / last result -> `-`
- missing source type / credibility level -> `-`
- blank maintenance status -> `ordinary`
- blank notes -> empty string in form fields, `-` in read-only note display
- empty `web_metadata` -> no extra metadata rows beyond standard fetch/maintenance/import/result rows
- enabled state uses `activity_label='enabled'`; disabled state uses `activity_label='disabled'`

Sources rendering rules:

- list and detail pages read from source page view dicts, not ORM attributes
- list view columns show:
  - source name
  - source type
  - URL
  - credibility level
  - enabled/disabled status chip
  - Web maintenance metadata
  - actions
- list source-name cells also show source notes with `-` fallback; user-entered names, URLs, notes, and metadata values are not translated
- source type and credibility level are rendered as lightweight scan chips
- `Source.config["_web"]` is read only for existing lightweight maintenance display; known standard fields are `maintenance_status`, `notes`, `last_import_at`, and `last_result`, and any additional non-empty keys are displayed as metadata rows
- empty list state -> `No sources available. Add a manually maintained source or check the database connection.`
- DB degradation note uses the shared database-note wording
- detail page maintenance status and activity label must use the same contract fields shown in the list
- the Sources page does not create a formal schema for `Source.config["_web"]`
- the Sources page does not add source discovery, crawling, registry expansion, migrations, or new CRUD flows beyond existing edit/detail/toggle/import entry points

Sources terminology:

- `Source Registry`
- `Edit Source`
- `Maintenance status`
- `Last import`
- `Last result`
- `Web metadata`

## Watchlist Contract

`WebMvpService.list_watchlist_page_views()` returns list items with:

- `id`
- `item_value`
- `item_type`
- `priority_level`
- `status`
- `group_name`
- `notes`
- `linked_entity`
- `updated_at`
- `created_at`
- `related_documents`
  - top 3 related documents only
  - each related document contains:
    - `id`
    - `title`
    - `source_name`
    - `published_at`
    - `created_at`

Downgrade rules:

- blank `item_value`, `item_type`, `priority_level`, `status`, `group_name`, `notes`, `updated_at`, or `created_at` -> `-`
- linked entity relation missing -> `-`
- linked entity relation present but unnamed -> `Unnamed entity`
- related document title missing -> `Untitled document`
- related document source/time missing -> `-`
- empty related documents -> `[]`, rendered as `No related documents yet.`
- empty watchlist -> `[]`, rendered as `No watchlist items yet.`
- DB read failure -> empty list plus the shared database-note wording; the route must not raise 500

Watchlist rendering rules:

- `/web/watchlist` reads from `list_watchlist_page_views()`, not ORM attributes
- visible item cards show:
  - item value
  - type
  - priority
  - status
  - group
  - notes
  - linked entity fallback
  - updated/created timestamps
  - related documents top 3
- shell copy is localized through `src/web/i18n.py`
- user-entered item values, notes, group names, linked entity names, and document titles are not translated
- existing create and status-update POST semantics stay unchanged

Watchlist terminology:

- `Watchlist`
- `Add Watchlist Item`
- `Related Documents`
- `Linked entity`

Current non-goals:

- no domain model change
- no new matching, crawling, discovery, RAG, vector search, or entity-resolution behavior
- no changes to Ask/Review override semantics
- no broad quality pass for Dashboard, Documents, System, or Sources

## Review Contract

Review page is an assembled view over:

- summary review items
- opportunity review items
- risk review items
- uncertainty review items

Current page-level wording rules:

- empty review page -> `No review items available.`
- empty history for a review item -> `No review history available for this item.`
- DB degradation note uses the shared database-note wording

Review terminology:

- `Automatic Result`
- `Effective Values`
- `Review History`
- `reset to auto`

Current non-goal:

- the page does not redefine review override semantics; it only renders what the service provides

## Ask Page Contract

### Ask History Page

`GET /web/ask` uses:

- enabled QA-capable providers for the provider select
- recent ask history for the right-column history cards

Empty state:

- no ask history -> `No recent Q&A available.`

### Ask Result Page

The result page requires:

- `question`
- `answer`

Optional fields and downgrade behavior:

- `answer_mode`
  - missing -> treated as `local_only`
- `provider_name`
  - missing -> rendered as `default/local only`
- `note`
  - missing -> omitted
- `created_at`
  - missing -> omitted from run details
- `error`
  - missing -> no `Error State` section
- `evidence`
  - missing/empty -> `No evidence available for this answer.`
- `opportunities`
  - missing/empty -> `No reviewed opportunities available for this answer.`
- `risks`
  - missing/empty -> `No reviewed risks available for this answer.`
- `uncertainties`
  - missing/empty -> `No reviewed uncertainties available for this answer.`
- `related_topics`
  - missing/empty -> `No related topics available for this answer.`
- `meta`
  - missing/empty/non-dict -> `No metadata available.`

Ask terminology:

- `Ask / Q&A`
- `Ask from Local Knowledge`
- `Run Details`
- `Evidence`
- `Opportunities`
- `Risks`
- `Uncertainties`
- `Related Topics`
- `Meta`

Current non-goal:

- the page does not change retrieval logic, review override logic, provider routing, or answer generation

## System / Storage Contract

`WebMvpService.get_system_page_data()` returns:

- `checks`
  - list items with:
    - `label`
    - `status`
    - `detail`
  - current labels:
    - `Database environment`
    - `Database connection`
    - `pgvector`
  - status vocabulary:
    - `available`
    - `degraded`
  - missing detail fallback -> `-`
- `database_counts`
  - list items with:
    - `name`
    - `count`
  - empty state -> `No database counts available.`
- `counts_error`
  - `None` in normal state
  - readable degradation detail when counts are unavailable
  - source priority:
    - first use the real counts-query failure reason when available
    - only fall back to degraded system-check detail when no explicit counts error exists
  - page note rendering uses the shared database-note wording
- `storage_files`
  - list items with:
    - `path`
    - `exists_label`
    - `size_bytes`
  - `exists_label` vocabulary:
    - `yes`
    - `no`
  - missing path fallback -> `-`
  - empty state -> `No storage files available.`
- `storage_overview`
  - list items with:
    - `area_key`
    - `primary_key`
    - `fallback_key`
    - `detail_key`
    - `path`
  - current storage facts:
    - main knowledge storage -> `PostgreSQL + pgvector`
    - Ask history -> `DB-first` + `JSON fallback`
    - AI provider config -> `DB-first` + `JSON fallback`
    - `Source.config["_web"]` remains in source config and is not a migration target
  - must not render API keys in plain text

System / Storage terminology:

- `Storage Overview`
- `System Checks`
- `Database Counts`
- `Storage Files`

Rendering rules:

- the page reads only from `get_system_page_data()`
- degraded probe results are shown through `status=degraded` plus the returned detail
- counts degradation additionally shows the shared database note
- storage overview is informational only and does not change storage strategy
