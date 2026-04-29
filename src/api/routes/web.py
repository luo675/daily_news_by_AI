"""Server-rendered Web MVP routes."""

from __future__ import annotations

from html import escape
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.web.service import WebMvpService

router = APIRouter(include_in_schema=False)
service = WebMvpService()


async def _read_form(request: Request) -> dict[str, str]:
    body = await request.body()
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _bool_label(value: bool) -> str:
    return "yes" if value else "no"


def _truncate_text(value: object, *, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(limit - 1, 0)].rstrip()}..."


def _coerce_items(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _render_value(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple)):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(parts) if parts else "-"
    if isinstance(value, dict):
        parts = [f"{key}={value[key]}" for key in value if value[key] is not None and str(value[key]).strip()]
        return ", ".join(parts) if parts else "-"
    text = str(value).strip()
    return text or "-"


def _render_definition_rows(rows: list[tuple[str, object]]) -> str:
    parts: list[str] = []
    for label, value in rows:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        rendered_value = _render_value(value)
        parts.append(f"<div><strong>{escape(label)}:</strong> {escape(rendered_value)}</div>")
    return "".join(parts)


def _render_text_rows(rows: list[tuple[str, object]]) -> str:
    parts: list[str] = []
    for label, value in rows:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        rendered_value = _render_value(value)
        parts.append(f"<div>{escape(label)}: {escape(rendered_value)}</div>")
    return "".join(parts)


def _render_structured_list(items: object, *, empty_message: str) -> str:
    values = _coerce_items(items)
    if not values:
        return f"<div class='muted'>{escape(empty_message)}</div>"
    rendered: list[str] = []
    for item in values:
        if isinstance(item, dict):
            title = str(
                item.get("title")
                or item.get("name")
                or item.get("title_en")
                or item.get("title_zh")
                or item.get("description")
                or "Untitled item"
            )
            detail = _render_value(
                {
                    key: value
                    for key, value in item.items()
                    if key not in {"title", "name", "title_en", "title_zh"} and str(value or "").strip()
                }
            )
            rendered.append(
                f"<li><strong>{escape(title)}</strong>"
                f"{'' if detail == '-' else f'<div class=\"muted\">{escape(detail)}</div>'}</li>"
            )
            continue
        rendered.append(f"<li>{escape(str(item))}</li>")
    return f"<ul>{''.join(rendered)}</ul>"


def _render_meta_section(meta: object) -> str:
    if not isinstance(meta, dict) or not any(value is not None and str(value).strip() for value in meta.values()):
        return "<div class='muted'>No metadata available.</div>"
    return _render_definition_rows([(str(key), value) for key, value in meta.items()])


def _format_ask_provider_name(value: object) -> str:
    text = str(value or "").strip()
    return text or "default/local only"


def _format_count_label(count: int, singular: str, plural: str | None = None) -> str:
    word = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {word}"


def _build_ask_metadata_rows(result: dict[str, object], *, include_status: bool) -> list[tuple[str, object]]:
    status_label, _ = _build_ask_status(result)
    evidence_items = _coerce_items(result.get("evidence"))
    first_match_basis = ""
    for item in evidence_items:
        if isinstance(item, dict) and str(item.get("match_basis") or "").strip():
            first_match_basis = str(item.get("match_basis")).strip()
            break

    rows: list[tuple[str, object]] = []
    if include_status:
        rows.append(("Status", status_label))
    rows.extend(
        [
            ("Mode", str(result.get("answer_mode") or "local_only")),
            ("Provider", _format_ask_provider_name(result.get("provider_name"))),
            ("Created", str(result.get("created_at") or "").strip() or "-"),
            ("Evidence", _format_count_label(len(evidence_items), "item")),
        ]
    )
    if first_match_basis:
        rows.append(("Match", first_match_basis))
    note = str(result.get("note") or "").strip()
    if note:
        rows.append(("Note", note))
    return rows


def _build_ask_status(result: dict[str, object]) -> tuple[str, str]:
    answer_mode = str(result.get("answer_mode") or "local_only")
    if answer_mode == "insufficient_local_evidence":
        return "incomplete", "Local evidence was not sufficient for a reliable answer."
    if answer_mode == "local_fallback":
        return "fallback warning", "Showing local answer because the external provider failed."
    if answer_mode == "local_with_external_reasoning":
        return "bounded external reasoning", "External reasoning stayed constrained to retrieved local evidence."
    return "local answer", "Answer rendered from local evidence only."


def _render_ask_evidence(items: object) -> str:
    evidence_items = _coerce_items(items)
    if not evidence_items:
        return "<div class='muted'>No local evidence was attached to this answer.</div>"
    cards: list[str] = []
    for raw_item in evidence_items:
        item = raw_item if isinstance(raw_item, dict) else {"title": str(raw_item)}
        title = str(item.get("title") or "Untitled evidence")
        summary = str(item.get("summary") or "").strip()
        snippet = str(item.get("snippet") or "").strip() or summary or "No snippet available."
        source_type = str(item.get("evidence_type") or ("document" if item.get("document_id") else "brief"))
        match_basis = str(item.get("match_basis") or "").strip()
        if item.get("document_id"):
            title_html = f"<a href='/web/documents/{escape(str(item['document_id']))}'>{escape(title)}</a>"
        else:
            title_html = escape(title)
        meta_rows = [("Source", source_type)]
        if match_basis:
            meta_rows.append(("Match", match_basis))
        cards.append(
            f"""
            <article class="ask-evidence-card">
              <h3>{title_html}</h3>
              <div class="muted">{_render_text_rows(meta_rows)}</div>
              <div class="pre">{escape(snippet)}</div>
            </article>
            """
        )
    return "".join(cards)


def _layout(title: str, body: str, message: str | None = None) -> HTMLResponse:
    nav_items = [
        ("/web/dashboard", "Dashboard"),
        ("/web/documents", "Documents"),
        ("/web/review", "Review"),
        ("/web/watchlist", "Watchlist"),
        ("/web/ask", "Ask"),
        ("/web/sources", "Sources"),
        ("/web/ai-settings", "AI Settings"),
        ("/web/system", "System"),
    ]
    nav_html = "".join(
        f'<a class="nav-link" href="{href}">{escape(label)}</a>' for href, label in nav_items
    )
    message_html = f'<div class="message">{escape(message)}</div>' if message else ""
    html = f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{escape(title)}</title>
      <style>
        :root {{
          --bg: #f5f2ea;
          --panel: #fffdf8;
          --ink: #1f2933;
          --muted: #607080;
          --line: #d6cec2;
          --accent: #9e3d22;
          --accent-soft: #f3d8cf;
        }}
        * {{ box-sizing: border-box; }}
        body {{
          margin: 0;
          font-family: Georgia, "Noto Serif SC", serif;
          color: var(--ink);
          background:
            radial-gradient(circle at top left, #efe1d1 0, transparent 26rem),
            linear-gradient(180deg, #f8f4ed 0%, var(--bg) 100%);
        }}
        a {{ color: var(--accent); text-decoration: none; }}
        .shell {{ max-width: 1220px; margin: 0 auto; padding: 24px 18px 48px; }}
        .topbar {{
          display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between;
          margin-bottom: 18px;
        }}
        h1 {{ margin: 0; font-size: 2rem; }}
        .sub {{ color: var(--muted); margin-top: 6px; }}
        .nav {{
          display: flex; flex-wrap: wrap; gap: 8px; margin: 18px 0 24px;
        }}
        .nav-link {{
          padding: 8px 12px; border: 1px solid var(--line); border-radius: 999px;
          background: rgba(255,255,255,0.65);
        }}
        .message {{
          margin-bottom: 16px; padding: 12px 14px; border-radius: 10px;
          background: var(--accent-soft); border: 1px solid #ddb1a4;
        }}
        .grid {{ display: grid; gap: 16px; }}
        .cols-2 {{ grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }}
        .cols-3 {{ grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }}
        .card {{
          background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 16px;
          box-shadow: 0 8px 24px rgba(82, 63, 49, 0.06);
        }}
        .card h2, .card h3 {{ margin-top: 0; }}
        .metric {{ font-size: 1.9rem; font-weight: 700; }}
        .muted {{ color: var(--muted); }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--line); vertical-align: top; }}
        form {{ display: grid; gap: 10px; }}
        input, textarea, select, button {{
          width: 100%; padding: 10px 12px; border: 1px solid #baa999; border-radius: 10px;
          background: white; font: inherit;
        }}
        textarea {{ min-height: 110px; resize: vertical; }}
        button {{
          width: auto; cursor: pointer; background: var(--accent); color: white; border: none; padding: 10px 16px;
        }}
        .inline {{
          display: inline-flex; gap: 8px; align-items: center; width: auto;
        }}
        .stack {{ display: grid; gap: 12px; }}
        .chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
        .chip {{
          display: inline-block; padding: 4px 10px; border-radius: 999px; background: #efe8dc; color: #5f503e;
        }}
        .ask-section {{ display: grid; gap: 10px; margin-bottom: 14px; }}
        .ask-section:last-child {{ margin-bottom: 0; }}
        .ask-status {{
          border-left: 4px solid var(--accent); background: #fbf1ea; padding: 12px; border-radius: 10px;
        }}
        .ask-status.warning {{ border-left-color: #b45309; background: #fff4e5; }}
        .ask-status.incomplete {{ border-left-color: #9f1239; background: #fff1f2; }}
        .ask-evidence-card {{
          border: 1px solid var(--line); border-radius: 12px; padding: 12px; background: #fcfaf5;
        }}
        .ask-evidence-card h3 {{ margin: 0 0 8px; font-size: 1rem; }}
        .compact-list {{ display: grid; gap: 12px; }}
        .pre {{
          white-space: pre-wrap; background: #f8f4ed; border: 1px solid var(--line); border-radius: 10px; padding: 12px;
        }}
      </style>
    </head>
    <body>
      <div class="shell">
        <div class="topbar">
          <div>
            <h1>{escape(title)}</h1>
            <div class="sub">daily_news personal knowledge workbench</div>
          </div>
        </div>
        <nav class="nav">{nav_html}</nav>
        {message_html}
        {body}
      </div>
    </body>
    </html>
    """
    return HTMLResponse(html)


def _redirect(target: str, message: str) -> RedirectResponse:
    encoded = urlencode({"message": message})
    return RedirectResponse(f"{target}?{encoded}", status_code=303)


@router.get("/web")
async def web_index() -> RedirectResponse:
    return RedirectResponse("/web/dashboard", status_code=303)


@router.get("/web/dashboard")
async def dashboard(message: str | None = None) -> HTMLResponse:
    data = service.get_dashboard_data()
    counts = data["counts"]
    docs_html = "".join(
        f"<tr><td><a href='/web/documents/{doc.id}'>{escape(doc.title)}</a></td>"
        f"<td>{escape(doc.source.name if doc.source else '-')}</td>"
        f"<td>{escape(str(doc.created_at))}</td></tr>"
        for doc in data["recent_documents"]
    ) or "<tr><td colspan='3'>No documents yet.</td></tr>"
    topics_html = "".join(
        f"<li>{escape(name)} ({count})</li>" for name, count in data["top_topics"]
    ) or "<li>No topic data.</li>"
    qa_html = "".join(
        f"<li><strong>{escape(item['question'])}</strong> <span class='muted'>[{escape(item['answer_mode'])}]</span></li>"
        for item in data["qa_history"]
    ) or "<li>No Q&A history.</li>"
    provider_html = "".join(
        f"<li>{escape(provider.name)} - {escape(provider.model)}"
        f" <span class='muted'>(default={_bool_label(provider.is_default)}, enabled={_bool_label(provider.is_enabled)})</span></li>"
        for provider in data["providers"]
    ) or "<li>No provider configured.</li>"
    db_note = (
        f"<div class='card'><strong>Database note:</strong> {escape(data['db_error'])}</div>"
        if data["db_error"]
        else ""
    )
    body = f"""
    <div class="grid cols-3">
      <div class="card"><div class="muted">Sources</div><div class="metric">{counts['sources']}</div></div>
      <div class="card"><div class="muted">Documents</div><div class="metric">{counts['documents']}</div></div>
      <div class="card"><div class="muted">Watchlist</div><div class="metric">{counts['watchlist']}</div></div>
      <div class="card"><div class="muted">Review Edits</div><div class="metric">{counts['reviews']}</div></div>
    </div>
    {db_note}
    <div class="grid cols-2" style="margin-top:16px;">
      <section class="card">
        <h2>Recent Documents</h2>
        <table>
          <thead><tr><th>Title</th><th>Source</th><th>Created</th></tr></thead>
          <tbody>{docs_html}</tbody>
        </table>
      </section>
      <section class="card">
        <h2>Top Topics</h2>
        <ul>{topics_html}</ul>
        <h3>AI Providers</h3>
        <ul>{provider_html}</ul>
        <h3>Recent Q&A</h3>
        <ul>{qa_html}</ul>
      </section>
    </div>
    """
    return _layout("Dashboard", body, message=message)


@router.get("/web/sources")
async def sources_page(message: str | None = None) -> HTMLResponse:
    sources, error = service.list_source_views()
    rows = "".join(
        f"<tr>"
        f"<td><a href='/web/sources/{source.source.id}'>{escape(source.source.name)}</a></td>"
        f"<td>{escape(source.source.source_type)}</td>"
        f"<td>{escape(source.source.url or '-')}</td>"
        f"<td>{escape(source.source.credibility_level)}</td>"
        f"<td>{escape(source.source.fetch_strategy)}</td>"
        f"<td>{escape('active' if source.source.is_active else 'disabled')}</td>"
        f"<td>{escape(source.maintenance_status)}</td>"
        f"<td>{escape(source.last_import_at or '-')}</td>"
        f"<td>{escape(source.last_result or '-')}</td>"
        f"<td>"
        f"<a class='nav-link' href='/web/sources/{source.source.id}'>Edit</a> "
        f"<form class='inline' method='post' action='/web/sources/{source.source.id}/toggle'><button>Toggle</button></form> "
        f"<form class='inline' method='post' action='/web/sources/{source.source.id}/import'><button>Import</button></form>"
        f"</td>"
        f"</tr>"
        for source in sources
    ) or "<tr><td colspan='10'>No sources found.</td></tr>"
    error_html = f"<div class='card'><strong>Database note:</strong> {escape(error)}</div>" if error else ""
    source_type_options = "".join(
        f"<option value='{escape(value)}'>{escape(value)}</option>" for value in service.list_source_type_values()
    )
    credibility_options = "".join(
        f"<option value='{escape(value)}'>{escape(value)}</option>" for value in service.list_credibility_values()
    )
    maintenance_status_options = "".join(
        f"<option value='{escape(value)}'>{escape(value)}</option>"
        for value in service.list_web_assignable_maintenance_status_values()
    )
    body = f"""
    {error_html}
    <div class="grid cols-2">
      <section class="card">
        <h2>Add Source</h2>
        <p class="muted">Ordinary web editing manages source configuration only. Formal seed baseline decisions remain in the maintenance workflow.</p>
        <form method="post" action="/web/sources">
          <input name="name" placeholder="Source name" required>
          <select name="source_type">{source_type_options}</select>
          <input name="url" placeholder="https://example.com/article-or-homepage">
          <select name="credibility_level">{credibility_options}</select>
          <input name="fetch_strategy" value="manual" placeholder="manual / rss / api / scrape">
          <select name="maintenance_status">{maintenance_status_options}</select>
          <textarea name="notes" placeholder="Maintenance notes, seed classification context, known limitations"></textarea>
          <textarea name="config_json" placeholder='Optional source config JSON, for example {{"rss_url":"https://..."}}'></textarea>
          <label><input type="checkbox" name="is_active" checked> active</label>
          <button>Create Source</button>
        </form>
      </section>
      <section class="card">
        <h2>Source Registry</h2>
        <table>
          <thead><tr><th>Name</th><th>Type</th><th>URL</th><th>Cred</th><th>Fetch</th><th>Status</th><th>Maint</th><th>Last Import</th><th>Last Result</th><th>Actions</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </section>
    </div>
    """
    return _layout("Sources", body, message=message)


@router.post("/web/sources")
async def create_source(request: Request) -> RedirectResponse:
    message = service.create_source(await _read_form(request))
    return _redirect("/web/sources", message)


@router.get("/web/sources/{source_id}")
async def source_detail(source_id: str, message: str | None = None) -> HTMLResponse:
    source_view, error = service.get_source_view(source_id)
    if source_view is None:
        body = f"<div class='card'>Source not found. {escape(error or '')}</div>"
        return _layout("Source Detail", body, message=message)
    source = source_view.source
    source_type_options = "".join(
        f"<option value='{escape(value)}'{' selected' if value == source.source_type else ''}>{escape(value)}</option>"
        for value in service.list_source_type_values()
    )
    credibility_options = "".join(
        f"<option value='{escape(value)}'{' selected' if value == source.credibility_level else ''}>{escape(value)}</option>"
        for value in service.list_credibility_values()
    )
    if source_view.maintenance_status == "formal_seed":
        maintenance_status_input = (
            f"<div class='pre'>formal_seed</div>"
            f"<input type='hidden' name='maintenance_status' value='formal_seed'>"
            f"<div class='muted'>Formal seed baseline status is visible here but not editable from the ordinary web form.</div>"
        )
    else:
        maintenance_status_options = "".join(
            f"<option value='{escape(value)}'{' selected' if value == source_view.maintenance_status else ''}>{escape(value)}</option>"
            for value in service.list_web_assignable_maintenance_status_values()
        )
        maintenance_status_input = (
            f"<select name='maintenance_status'>{maintenance_status_options}</select>"
            f"<div class='muted'>Formal seed baseline promotion is not handled in ordinary web editing.</div>"
        )
    body = f"""
    <div class="grid cols-2">
      <section class="card">
        <h2>Edit Source</h2>
        <p class="muted">This form updates source configuration and observation notes. It is not the authority for formal seed promotion.</p>
        <form method="post" action="/web/sources/{source.id}">
          <input name="name" value="{escape(source.name)}" required>
          <select name="source_type">{source_type_options}</select>
          <input name="url" value="{escape(source.url or '')}" placeholder="https://example.com/article-or-homepage">
          <select name="credibility_level">{credibility_options}</select>
          <input name="fetch_strategy" value="{escape(source.fetch_strategy)}">
          {maintenance_status_input}
          <textarea name="notes" placeholder="Maintenance notes">{escape(source_view.notes)}</textarea>
          <textarea name="config_json" placeholder='Optional source config JSON'>{escape(source_view.raw_config_json)}</textarea>
          <label><input type="checkbox" name="is_active" {'checked' if source.is_active else ''}> active</label>
          <button>Save Source</button>
        </form>
      </section>
      <section class="card stack">
        <div><strong>Maintenance status:</strong> {escape(source_view.maintenance_status)}</div>
        <div><strong>Last import:</strong> {escape(source_view.last_import_at or '-')}</div>
        <div><strong>Last result:</strong> {escape(source_view.last_result or '-')}</div>
        <div><strong>Notes:</strong><div class="pre">{escape(source_view.notes or '-')}</div></div>
        <div class="inline">
          <form class='inline' method='post' action='/web/sources/{source.id}/toggle'><button>Toggle Active</button></form>
          <form class='inline' method='post' action='/web/sources/{source.id}/import'><button>Import Now</button></form>
          <a href="/web/sources">Back to Sources</a>
        </div>
      </section>
    </div>
    """
    return _layout("Source Detail", body, message=message)


@router.post("/web/sources/{source_id}")
async def update_source(source_id: str, request: Request) -> RedirectResponse:
    message = service.update_source(source_id, await _read_form(request))
    return _redirect(f"/web/sources/{source_id}", message)


@router.post("/web/sources/{source_id}/toggle")
async def toggle_source(source_id: str) -> RedirectResponse:
    return _redirect("/web/sources", service.toggle_source(source_id))


@router.post("/web/sources/{source_id}/import")
async def import_source(source_id: str) -> RedirectResponse:
    return _redirect("/web/sources", service.import_source(source_id))


@router.get("/web/documents")
async def documents_page(
    message: str | None = None,
    q: str = "",
    source_id: str = "",
) -> HTMLResponse:
    documents, error = service.list_documents(query=q, source_id=source_id)
    sources, _ = service.list_sources()
    source_options = ["<option value=''>All sources</option>"]
    for source in sources:
        selected = " selected" if source_id == str(source.id) else ""
        source_options.append(f"<option value='{source.id}'{selected}>{escape(source.name)}</option>")
    rows = "".join(
        f"<tr>"
        f"<td><a href='/web/documents/{doc.id}'>{escape(doc.title)}</a></td>"
        f"<td>{escape(doc.source.name if doc.source else '-')}</td>"
        f"<td>{escape(doc.language or '-')}</td>"
        f"<td>{escape(doc.status)}</td>"
        f"<td>{escape((doc.summary.summary_en or doc.summary.summary_zh)[:160] if doc.summary and (doc.summary.summary_en or doc.summary.summary_zh) else '-')}</td>"
        f"</tr>"
        for doc in documents
    ) or "<tr><td colspan='5'>No documents found.</td></tr>"
    error_html = f"<div class='card'><strong>Database note:</strong> {escape(error)}</div>" if error else ""
    body = f"""
    {error_html}
    <div class="grid cols-2">
      <section class="card">
        <h2>Search</h2>
        <form method="get" action="/web/documents">
          <input name="q" value="{escape(q)}" placeholder="Search title, content, URL">
          <select name="source_id">{''.join(source_options)}</select>
          <button>Apply</button>
        </form>
      </section>
      <section class="card">
        <h2>Document List</h2>
        <table>
          <thead><tr><th>Title</th><th>Source</th><th>Lang</th><th>Status</th><th>Summary</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </section>
    </div>
    """
    return _layout("Documents / Knowledge", body, message=message)


@router.get("/web/documents/{document_id}")
async def document_detail(document_id: str, message: str | None = None) -> HTMLResponse:
    document, error = service.get_document(document_id)
    if document is None:
        body = f"<div class='card'>Document not found. {escape(error or '')}</div>"
        return _layout("Document Detail", body, message=message)
    entity_html = "".join(
        f"<span class='chip'>{escape(link.entity.name)} ({escape(link.entity.entity_type)})</span>"
        for link in document.document_entities
    ) or "<span class='muted'>No entities.</span>"
    topic_html = "".join(
        f"<span class='chip'>{escape(link.topic.name_en or link.topic.name_zh or 'Unnamed')}</span>"
        for link in document.document_topics
    ) or "<span class='muted'>No topics.</span>"
    key_points = "<br>".join(escape(point) for point in (document.summary.key_points if document.summary else []) or [])
    body = f"""
    <div class="grid cols-2">
      <section class="card stack">
        <div><strong>Title:</strong> {escape(document.title)}</div>
        <div><strong>Source:</strong> {escape(document.source.name if document.source else '-')}</div>
        <div><strong>URL:</strong> <a href="{escape(document.url or '#')}">{escape(document.url or '-')}</a></div>
        <div><strong>Status:</strong> {escape(document.status)}</div>
        <div><strong>Language:</strong> {escape(document.language or '-')}</div>
        <div><strong>Published:</strong> {escape(str(document.published_at) if document.published_at else '-')}</div>
        <div><strong>Summary EN:</strong><div class="pre">{escape(document.summary.summary_en if document.summary and document.summary.summary_en else '-')}</div></div>
        <div><strong>Summary ZH:</strong><div class="pre">{escape(document.summary.summary_zh if document.summary and document.summary.summary_zh else '-')}</div></div>
        <div><strong>Key Points:</strong><div class="pre">{key_points or '-'}</div></div>
      </section>
      <section class="card stack">
        <div><strong>Entities</strong><div class="chips">{entity_html}</div></div>
        <div><strong>Topics</strong><div class="chips">{topic_html}</div></div>
        <div><strong>Content Preview</strong><div class="pre">{escape((document.content_text or '')[:2400] or '-')}</div></div>
        <div class="inline">
          <a href="/web/review">Go to Review</a>
          <a href="/web/ask">Ask from this knowledge</a>
        </div>
      </section>
    </div>
    """
    if error:
        body = f"<div class='card'><strong>Database note:</strong> {escape(error)}</div>{body}"
    return _layout("Document Detail", body, message=message)


@router.get("/web/review")
async def review_page(message: str | None = None) -> HTMLResponse:
    uncertainties, uncertainty_error = service.list_review_uncertainties()
    risks, risk_error = service.list_review_risks()
    opportunities, opportunity_error = service.list_review_opportunities()
    documents, error = service.list_review_documents()
    sections = []
    uncertainty_sections = []
    risk_sections = []
    opportunity_sections = []
    for item in uncertainties:
        history_html = "".join(
            f"<li>{escape(edit.field_name)} -> {escape(str(edit.new_value))} <span class='muted'>{escape(str(edit.created_at))}</span></li>"
            for edit in item.history
        ) or "<li>No review history for this item.</li>"
        current_uncertainty_status = item.effective_values.get("uncertainty_status")
        uncertainty_status_options = []
        if current_uncertainty_status is None:
            uncertainty_status_options.append(
                '<option value="__UNCHANGED__" selected>-- keep auto / no manual override --</option>'
            )
        for value in ("open", "watching", "resolved"):
            selected = " selected" if current_uncertainty_status == value else ""
            uncertainty_status_options.append(
                f'<option value="{escape(value)}"{selected}>{escape(value)}</option>'
            )
        uncertainty_sections.append(
            f"""
            <section class="card">
              <h2>Uncertainty Review</h2>
              <div><strong>{escape(item.uncertainty_item)}</strong></div>
              <div class="muted">Brief id: {item.brief.id}</div>
              <div class="muted">Uncertainty item id: {escape(item.item_id)}</div>
                <div class="grid cols-2" style="margin-top:12px;">
                  <div>
                    <h3>Automatic Result</h3>
                    <div class="pre">uncertainty_note={escape(str(item.auto_values.get("uncertainty_note") or ""))}
uncertainty_status={escape(str(item.auto_values.get("uncertainty_status") or ""))}</div>
                  </div>
                  <div>
                    <h3>Effective Values</h3>
                    <form method="post" action="/web/review/uncertainties/{item.brief.id}/{item.route_id}">
                      <textarea name="uncertainty_note" placeholder="uncertainty_note">{escape(str(item.effective_values.get("uncertainty_note") or ""))}</textarea>
                      <label><input type="checkbox" name="reset_uncertainty_note"> reset to auto</label>
                      <select name="uncertainty_status">{"".join(uncertainty_status_options)}</select>
                      <label><input type="checkbox" name="reset_uncertainty_status"> reset to auto</label>
                      <input name="reason" placeholder="Why are you editing this uncertainty?">
                      <button>Save Uncertainty Review</button>
                    </form>
                  </div>
                </div>
                <h3>Review History</h3>
                <ul>{history_html}</ul>
              </section>
              """
        )
    for item in risks:
        history_html = "".join(
            f"<li>{escape(edit.field_name)} -> {escape(str(edit.new_value))} <span class='muted'>{escape(str(edit.created_at))}</span></li>"
            for edit in item.history
        ) or "<li>No review history for this item.</li>"
        severity_options = "".join(
            f"<option value='{escape(value)}'{' selected' if item.effective_values.get('severity') == value else ''}>{escape(value)}</option>"
            for value in ("high", "medium", "low")
        )
        risk_sections.append(
            f"""
            <section class="card">
              <h2>Risk Review</h2>
              <div><strong>{escape(str(item.risk_item.get("title") or "Untitled risk"))}</strong></div>
              <div class="muted">Brief id: {item.brief.id}</div>
              <div class="muted">Risk item id: {escape(item.item_id)}</div>
                <div class="grid cols-2" style="margin-top:12px;">
                  <div>
                    <h3>Automatic Result</h3>
                    <div class="pre">severity={escape(str(item.auto_values.get("severity") or ""))}
description={escape(str(item.auto_values.get("description") or ""))}</div>
                  </div>
                  <div>
                    <h3>Effective Values</h3>
                    <form method="post" action="/web/review/risks/{item.brief.id}/{item.route_id}">
                      <select name="severity">{severity_options}</select>
                      <label><input type="checkbox" name="reset_severity"> reset to auto</label>
                      <textarea name="description" placeholder="description">{escape(str(item.effective_values.get("description") or ""))}</textarea>
                      <label><input type="checkbox" name="reset_description"> reset to auto</label>
                      <input name="reason" placeholder="Why are you editing this risk?">
                      <button>Save Risk Review</button>
                    </form>
                  </div>
                </div>
                <h3>Review History</h3>
                <ul>{history_html}</ul>
              </section>
              """
        )
    for item in opportunities:
        opportunity = item.opportunity
        history_html = "".join(
            f"<li>{escape(edit.field_name)} -> {escape(str(edit.new_value))} <span class='muted'>{escape(str(edit.created_at))}</span></li>"
            for edit in item.history
        ) or "<li>No review history for this item.</li>"
        status_options = "".join(
            f"<option value='{escape(value)}'{' selected' if item.effective_values.get('status') == value else ''}>{escape(value)}</option>"
            for value in ("candidate", "confirmed", "dismissed", "watching")
        )
        uncertainty_options = "".join(
            f"<option value='{value}'{' selected' if item.effective_values.get('uncertainty') is selected else ''}>{label}</option>"
            for value, selected, label in (
                ("true", True, "true"),
                ("false", False, "false"),
            )
        )
        opportunity_sections.append(
            f"""
            <section class="card">
              <h2>Opportunity Review</h2>
              <div><strong>{escape(opportunity.title_en or opportunity.title_zh or "Untitled opportunity")}</strong></div>
              <div class="muted">Opportunity target id: {opportunity.id}</div>
              <div class="muted">Source document: {escape(item.source_document_title or '-')}</div>
                <div class="grid cols-2" style="margin-top:12px;">
                  <div>
                    <h3>Automatic Result</h3>
                  <div class="pre">need_realness={escape(str(item.auto_values.get("need_realness")))}
market_gap={escape(str(item.auto_values.get("market_gap")))}
feasibility={escape(str(item.auto_values.get("feasibility")))}
priority_score={escape(str(item.auto_values.get("priority_score")))}
evidence_score={escape(str(item.auto_values.get("evidence_score")))}
total_score={escape(str(item.auto_values.get("total_score")))}
  uncertainty={escape(str(item.auto_values.get("uncertainty")))}
  uncertainty_reason={escape(str(item.auto_values.get("uncertainty_reason") or ""))}
  status={escape(str(item.auto_values.get("status") or ""))}</div>
                  </div>
                  <div>
                    <h3>Effective Values</h3>
                    <form method="post" action="/web/review/opportunities/{opportunity.id}">
                    <input name="need_realness" type="number" min="1" max="10" value="{escape(str(item.effective_values.get("need_realness") or ""))}" placeholder="need_realness">
                    <label><input type="checkbox" name="reset_need_realness"> reset to auto</label>
                    <input name="market_gap" type="number" min="1" max="10" value="{escape(str(item.effective_values.get("market_gap") or ""))}" placeholder="market_gap">
                    <label><input type="checkbox" name="reset_market_gap"> reset to auto</label>
                    <input name="feasibility" type="number" min="1" max="10" value="{escape(str(item.effective_values.get("feasibility") or ""))}" placeholder="feasibility">
                    <label><input type="checkbox" name="reset_feasibility"> reset to auto</label>
                    <input name="priority_score" type="number" min="1" max="10" value="{escape(str(item.effective_values.get("priority_score") or ""))}" placeholder="priority_score">
                    <label><input type="checkbox" name="reset_priority_score"> reset to auto</label>
                    <input name="evidence_score" type="number" min="1" max="10" value="{escape(str(item.effective_values.get("evidence_score") or ""))}" placeholder="evidence_score">
                    <label><input type="checkbox" name="reset_evidence_score"> reset to auto</label>
                    <input name="total_score" type="number" step="0.1" value="{escape(str(item.effective_values.get("total_score") or ""))}" placeholder="total_score">
                    <label><input type="checkbox" name="reset_total_score"> reset to auto</label>
                    <select name="uncertainty">{uncertainty_options}</select>
                    <label><input type="checkbox" name="reset_uncertainty"> reset to auto</label>
                    <input name="uncertainty_reason" value="{escape(str(item.effective_values.get("uncertainty_reason") or ""))}" placeholder="uncertainty_reason">
                    <label><input type="checkbox" name="reset_uncertainty_reason"> reset to auto</label>
                    <select name="status">{status_options}</select>
                    <label><input type="checkbox" name="reset_status"> reset to auto</label>
                      <input name="reason" placeholder="Why are you editing this opportunity?">
                      <button>Save Opportunity Review</button>
                    </form>
                  </div>
                </div>
                <h3>Review History</h3>
                <ul>{history_html}</ul>
              </section>
              """
        )
    for item in documents:
        document = item.document
        summary = item.summary
        history = item.history
        history_html = "".join(
            f"<li>{escape(edit.field_name)} -> {escape(str(edit.new_value))} <span class='muted'>{escape(str(edit.created_at))}</span></li>"
            for edit in history[:5]
        ) or "<li>No review history for this item.</li>"
        auto_key_points_text = "\n".join(str(point) for point in item.auto_values.get("key_points") or [])
        effective_key_points_text = "\n".join(str(point) for point in item.effective_values.get("key_points") or [])
        sections.append(
            f"""
            <section class="card">
              <h2>Summary Review</h2>
              <div><strong>{escape(document.title)}</strong></div>
              <div class="muted">Summary target id: {summary.id}</div>
                <div class="grid cols-2" style="margin-top:12px;">
                  <div>
                    <h3>Automatic Result</h3>
                    <div class="pre">summary_zh={escape(str(item.auto_values.get("summary_zh") or ""))}
summary_en={escape(str(item.auto_values.get("summary_en") or ""))}
key_points={escape(auto_key_points_text)}</div>
                  </div>
                  <div>
                    <h3>Effective Values</h3>
                    <form method="post" action="/web/review/{summary.id}">
                    <textarea name="summary_zh" placeholder="summary_zh">{escape(str(item.effective_values.get("summary_zh") or ""))}</textarea>
                    <label><input type="checkbox" name="reset_summary_zh"> reset to auto</label>
                    <textarea name="summary_en" placeholder="summary_en">{escape(str(item.effective_values.get("summary_en") or ""))}</textarea>
                    <label><input type="checkbox" name="reset_summary_en"> reset to auto</label>
                    <textarea name="key_points" placeholder="One key point per line">{escape(effective_key_points_text)}</textarea>
                    <label><input type="checkbox" name="reset_key_points"> reset to auto</label>
                      <input name="reason" placeholder="Why are you editing this summary?">
                      <button>Save Review</button>
                    </form>
                  </div>
                </div>
                <h3>Review History</h3>
                <ul>{history_html}</ul>
              </section>
              """
        )
    content = "".join(uncertainty_sections + risk_sections + opportunity_sections + sections) or "<div class='card'>No reviewed summaries, opportunities, risks, or uncertainties are available.</div>"
    notes = []
    if uncertainty_error:
        notes.append(f"<div class='card'><strong>Database note:</strong> {escape(uncertainty_error)}</div>")
    if risk_error:
        notes.append(f"<div class='card'><strong>Database note:</strong> {escape(risk_error)}</div>")
    if opportunity_error:
        notes.append(f"<div class='card'><strong>Database note:</strong> {escape(opportunity_error)}</div>")
    if error:
        notes.append(f"<div class='card'><strong>Database note:</strong> {escape(error)}</div>")
    if notes:
        content = "".join(notes) + content
    return _layout("Review", content, message=message)


@router.post("/web/review/{summary_id}")
async def save_review(summary_id: str, request: Request) -> RedirectResponse:
    message = service.save_summary_review(summary_id, await _read_form(request))
    return _redirect("/web/review", message)


@router.post("/web/review/opportunities/{opportunity_id}")
async def save_opportunity_review(opportunity_id: str, request: Request) -> RedirectResponse:
    message = service.save_opportunity_review(opportunity_id, await _read_form(request))
    return _redirect("/web/review", message)


@router.post("/web/review/risks/{brief_id}/{route_id}")
async def save_risk_review(brief_id: str, route_id: str, request: Request) -> RedirectResponse:
    message = service.save_risk_review(brief_id, route_id, await _read_form(request))
    return _redirect("/web/review", message)


@router.post("/web/review/uncertainties/{brief_id}/{route_id}")
async def save_uncertainty_review(brief_id: str, route_id: str, request: Request) -> RedirectResponse:
    message = service.save_uncertainty_review(brief_id, route_id, await _read_form(request))
    return _redirect("/web/review", message)


@router.get("/web/watchlist")
async def watchlist_page(message: str | None = None) -> HTMLResponse:
    items, error = service.list_watchlist_items()
    type_options = "".join(
        f"<option value='{escape(value)}'>{escape(value)}</option>"
        for value in service.list_watchlist_type_values()
    )
    priority_options = "".join(
        f"<option value='{escape(value)}'>{escape(value)}</option>"
        for value in service.list_priority_values()
    )
    rows = []
    for item in items:
        hits = service.list_watchlist_hits(item.item_value)[:3]
        hits_html = "".join(
            f"<li><a href='/web/documents/{doc.id}'>{escape(doc.title)}</a></li>" for doc in hits
        ) or "<li>No related documents yet.</li>"
        rows.append(
            f"""
            <section class="card">
              <h2>{escape(item.item_value)}</h2>
              <div class="muted">{escape(item.item_type)} / {escape(item.priority_level)} / {escape(item.status)}</div>
              <div>{escape(item.notes or '')}</div>
              <h3>Related Documents</h3>
              <ul>{hits_html}</ul>
              <div class="inline">
                <form class='inline' method='post' action='/web/watchlist/{item.id}/status'><input type='hidden' name='status' value='active'><button>Active</button></form>
                <form class='inline' method='post' action='/web/watchlist/{item.id}/status'><input type='hidden' name='status' value='paused'><button>Pause</button></form>
                <form class='inline' method='post' action='/web/watchlist/{item.id}/status'><input type='hidden' name='status' value='removed'><button>Remove</button></form>
              </div>
            </section>
            """
        )
    error_html = f"<div class='card'><strong>Database note:</strong> {escape(error)}</div>" if error else ""
    body = f"""
    {error_html}
    <div class="grid cols-2">
      <section class="card">
        <h2>Add Watchlist Item</h2>
        <form method="post" action="/web/watchlist">
          <select name="item_type">{type_options}</select>
          <input name="item_value" placeholder="OpenAI, Claude Code, agent ops..." required>
          <select name="priority_level">{priority_options}</select>
          <input name="group_name" placeholder="Optional group">
          <textarea name="notes" placeholder="Why track this item?"></textarea>
          <button>Create Watchlist Item</button>
        </form>
      </section>
      <section class="stack">{''.join(rows) or "<div class='card'>No watchlist items yet.</div>"}</section>
    </div>
    """
    return _layout("Watchlist", body, message=message)


@router.post("/web/watchlist")
async def create_watchlist(request: Request) -> RedirectResponse:
    message = service.create_watchlist_item(await _read_form(request))
    return _redirect("/web/watchlist", message)


@router.post("/web/watchlist/{item_id}/status")
async def set_watchlist_status(item_id: str, request: Request) -> RedirectResponse:
    form = await _read_form(request)
    return _redirect("/web/watchlist", service.update_watchlist_status(item_id, form.get("status", "")))


@router.get("/web/ask")
async def ask_page(message: str | None = None) -> HTMLResponse:
    providers = [
        provider
        for provider in service.list_ai_providers()
        if provider.is_enabled and "qa" in provider.supported_tasks
    ]
    history = service.list_qa_history()[:10]
    provider_options = ["<option value=''>Default provider</option>"]
    for provider in providers:
        provider_options.append(
            f"<option value='{escape(provider.id)}'>{escape(provider.name)} - {escape(provider.model)}</option>"
        )
    history_html = "".join(
        f"""
        <section class='card'>
          <h2>{escape(item['question'])}</h2>
          <div class='stack muted'>{_render_text_rows(_build_ask_metadata_rows(item, include_status=True))}</div>
          <div class='pre'>{escape(_truncate_text(item['answer'], limit=220))}</div>
        </section>
        """
        for item in history
    ) or "<div class='card'>No Q&amp;A history yet.</div>"
    body = f"""
    <div class="grid cols-2">
      <section class="card">
        <h2>Ask from Local Knowledge</h2>
        <form method="post" action="/web/ask">
          <textarea name="question" placeholder="What changed in AI coding tools this week?" required></textarea>
          <select name="provider_id">{''.join(provider_options)}</select>
          <button>Ask</button>
        </form>
        <p class="muted">Retrieval-first flow: local knowledge is searched first. External AI is optional and may only reason over the retrieved local evidence.</p>
      </section>
      <section class="stack">{history_html}</section>
    </div>
    """
    return _layout("Ask / Q&A", body, message=message)


@router.post("/web/ask")
async def ask_submit(request: Request) -> HTMLResponse:
    form = await _read_form(request)
    result = service.ask_question(question=form.get("question", ""), provider_id=form.get("provider_id", ""))
    status_label, status_message = _build_ask_status(result)
    status_class = "ask-status"
    if status_label == "fallback warning":
        status_class = "ask-status warning"
    elif status_label == "incomplete":
        status_class = "ask-status incomplete"
    run_metadata_html = _render_text_rows(_build_ask_metadata_rows(result, include_status=True))
    error_html = ""
    if str(result.get("error") or "").strip():
        error_html = f"""
        <section class="ask-section">
          <h2>Error State</h2>
          <div class="pre">{escape(str(result.get("error") or ""))}</div>
        </section>
        """
    body = f"""
    <div class="grid cols-2">
      <section class="card">
        <div class="{status_class}" style="margin-bottom:14px;">
          <strong>Status: {escape(status_label)}</strong>
          <div class="muted">{escape(status_message)}</div>
        </div>
        <section class="ask-section">
          <h2>Question</h2>
          <div class="pre">{escape(result['question'])}</div>
        </section>
        <section class="ask-section">
          <h2>Answer</h2>
          <div class="pre">{escape(result['answer'])}</div>
        </section>
        <section class="ask-section">
          <h2>Run Details</h2>
          <div class="stack">{run_metadata_html}</div>
        </section>
        {error_html}
      </section>
      <div class="stack">
        <section class="card">
          <h2>Evidence</h2>
          <div class="compact-list">{_render_ask_evidence(result.get("evidence"))}</div>
        </section>
        <section class="card">
          <h2>Opportunities</h2>
          {_render_structured_list(result.get("opportunities"), empty_message="No reviewed opportunities were extracted for this answer.")}
        </section>
        <section class="card">
          <h2>Risks</h2>
          {_render_structured_list(result.get("risks"), empty_message="No reviewed risks were extracted for this answer.")}
        </section>
        <section class="card">
          <h2>Uncertainties</h2>
          {_render_structured_list(result.get("uncertainties"), empty_message="No reviewed uncertainties were extracted for this answer.")}
        </section>
        <section class="card">
          <h2>Related Topics</h2>
          {_render_structured_list(result.get("related_topics"), empty_message="No related topics were extracted for this answer.")}
        </section>
        <section class="card">
          <h2>Meta</h2>
          {_render_meta_section(result.get("meta"))}
          <div class="inline"><a href="/web/ask">Back to Ask</a></div>
        </section>
      </div>
    </div>
    """
    return _layout("Ask Result", body)


@router.get("/web/ai-settings")
async def ai_settings_page(message: str | None = None) -> HTMLResponse:
    providers = service.list_ai_providers()
    task_values = service.list_ai_task_values()
    rows = "".join(
        f"<tr><td>{escape(provider.name)}</td><td>{escape(provider.provider_type)}</td><td>{escape(provider.base_url)}</td>"
        f"<td>{escape(provider.model)}</td><td>{escape(provider.masked_key)}</td><td>{escape(str(provider.is_default))}</td>"
        f"<td>{escape(str(provider.is_enabled))}</td><td>{escape(', '.join(provider.supported_tasks))}</td>"
        f"<td>{escape(provider.last_test_status or '-')}</td>"
        f"<td><a class='nav-link' href='/web/ai-settings/{provider.id}'>Edit</a> "
        f"<form class='inline' method='post' action='/web/ai-settings/{provider.id}/test'><button>Test</button></form></td></tr>"
        for provider in providers
    ) or "<tr><td colspan='10'>No AI provider configured.</td></tr>"
    task_inputs = "".join(
        f"<label><input type='checkbox' name='task_{escape(task)}' checked> {escape(task)}</label>"
        for task in task_values
    )
    body = f"""
    <div class="grid cols-2">
      <section class="card">
        <h2>Save Provider</h2>
        <p class="muted">Local configuration stays in this machine. Ask uses explicit provider selection first, otherwise the enabled default provider that supports Q&amp;A.</p>
        <form method="post" action="/web/ai-settings">
          <input name="name" placeholder="Provider name" required>
          <input name="provider_type" value="openai_compatible">
          <input name="base_url" value="https://api.openai.com/v1">
          <input name="model" placeholder="gpt-4o-mini / custom model" required>
          <input name="api_key" placeholder="API key" required>
          <div class="stack">
            <strong>Supported tasks</strong>
            <div class="chips">{task_inputs}</div>
          </div>
          <textarea name="notes" placeholder="Notes, fallback intent, cost preference"></textarea>
          <label><input type="checkbox" name="is_enabled" checked> enabled</label>
          <label><input type="checkbox" name="is_default"> default provider</label>
          <button>Save Provider</button>
        </form>
      </section>
      <section class="card">
        <h2>Configured Providers</h2>
        <table>
          <thead><tr><th>Name</th><th>Type</th><th>Base URL</th><th>Model</th><th>Key</th><th>Default</th><th>Enabled</th><th>Tasks</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </section>
    </div>
    """
    return _layout("AI Settings", body, message=message)


@router.post("/web/ai-settings")
async def save_ai_settings(request: Request) -> RedirectResponse:
    message = service.save_ai_provider(await _read_form(request))
    return _redirect("/web/ai-settings", message)


@router.get("/web/ai-settings/{provider_id}")
async def ai_provider_detail(provider_id: str, message: str | None = None) -> HTMLResponse:
    provider = service.get_ai_provider(provider_id)
    if provider is None:
        body = "<div class='card'>AI provider not found.</div>"
        return _layout("AI Provider Detail", body, message=message)

    task_inputs = "".join(
        f"<label><input type='checkbox' name='task_{escape(task)}' {'checked' if task in provider.supported_tasks else ''}> {escape(task)}</label>"
        for task in service.list_ai_task_values()
    )
    body = f"""
    <div class="grid cols-2">
      <section class="card">
        <h2>Edit Provider</h2>
        <form method="post" action="/web/ai-settings">
          <input type="hidden" name="provider_id" value="{escape(provider.id)}">
          <input name="name" value="{escape(provider.name)}" required>
          <input name="provider_type" value="{escape(provider.provider_type)}">
          <input name="base_url" value="{escape(provider.base_url)}">
          <input name="model" value="{escape(provider.model)}" required>
          <input name="api_key" placeholder="Leave blank to keep current saved key">
          <div class="stack">
            <strong>Supported tasks</strong>
            <div class="chips">{task_inputs}</div>
          </div>
          <textarea name="notes" placeholder="Notes">{escape(provider.notes)}</textarea>
          <label><input type="checkbox" name="is_enabled" {'checked' if provider.is_enabled else ''}> enabled</label>
          <label><input type="checkbox" name="is_default" {'checked' if provider.is_default else ''}> default provider</label>
          <button>Save Provider</button>
        </form>
      </section>
      <section class="card stack">
        <div><strong>Supported tasks:</strong> {escape(', '.join(provider.supported_tasks))}</div>
        <div><strong>Saved key:</strong> {escape(provider.masked_key or '-')}</div>
        <div><strong>Last test status:</strong> {escape(provider.last_test_status or '-')}</div>
        <div><strong>Last test message:</strong><div class="pre">{escape(provider.last_test_message or '-')}</div></div>
        <div><strong>Notes:</strong><div class="pre">{escape(provider.notes or '-')}</div></div>
        <div class="inline">
          <form class='inline' method='post' action='/web/ai-settings/{provider.id}/test'><button>Test Provider</button></form>
          <a href="/web/ai-settings">Back to AI Settings</a>
        </div>
      </section>
    </div>
    """
    return _layout("AI Provider Detail", body, message=message)


@router.post("/web/ai-settings/{provider_id}/test")
async def test_ai_provider(provider_id: str) -> RedirectResponse:
    message = service.test_ai_provider(provider_id)
    return _redirect(f"/web/ai-settings/{provider_id}", message)


@router.get("/web/system")
async def system_page(message: str | None = None) -> HTMLResponse:
    status = service.get_system_status()
    file_rows = "".join(
        f"<tr><td>{escape(item['path'])}</td><td>{escape(str(item['exists']))}</td><td>{item['size_bytes']}</td></tr>"
        for item in status["files"]
    )
    count_rows = "".join(
        f"<tr><td>{escape(name)}</td><td>{count}</td></tr>" for name, count in status["counts"].items()
    ) or "<tr><td colspan='2'>No database counts available.</td></tr>"
    body = f"""
    <div class="grid cols-2">
      <section class="card stack">
        <div><strong>DB env:</strong> {escape(status['database_environment'].detail)}</div>
        <div><strong>DB connection:</strong> {escape(status['database_connection'].detail)}</div>
        <div><strong>pgvector:</strong> {escape(status['pgvector'].detail)}</div>
      </section>
      <section class="card">
        <h2>Database Counts</h2>
        <table><tbody>{count_rows}</tbody></table>
      </section>
      <section class="card">
        <h2>Local Web Storage</h2>
        <table>
          <thead><tr><th>Path</th><th>Exists</th><th>Size (bytes)</th></tr></thead>
          <tbody>{file_rows}</tbody>
        </table>
      </section>
    </div>
    """
    return _layout("System / Storage", body, message=message)
