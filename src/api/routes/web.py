"""Server-rendered Web MVP routes."""

from __future__ import annotations

from html import escape
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.web.i18n import WebI18nContext
from src.web.service import WebMvpService

router = APIRouter(include_in_schema=False)
service = WebMvpService()


def _i18n(request: Request) -> WebI18nContext:
    return request.state.web_i18n


def _text(request: Request, key: str, default: str | None = None) -> str:
    return _i18n(request).text(key, default)


def _dashboard_redirect_url(request: Request) -> str:
    return f"/web/dashboard?{urlencode({'lang': _i18n(request).lang})}"


def _review_query_type(request: Request) -> str:
    value = str(request.query_params.get("type") or "all").strip().lower()
    if value in {"all", "summary", "opportunity", "risk", "uncertainty"}:
        return value
    return "all"


def _review_filter_url(request: Request, review_type: str) -> str:
    query: list[tuple[str, str]] = [("lang", _i18n(request).lang)]
    if review_type != "all":
        query.append(("type", review_type))
    return f"/web/review?{urlencode(query)}"


def _review_filter_label(request: Request, review_type: str) -> str:
    return {
        "all": _text(request, "page.review.filter.all"),
        "summary": _text(request, "page.review.filter.summary"),
        "opportunity": _text(request, "page.review.filter.opportunity"),
        "risk": _text(request, "page.review.filter.risk"),
        "uncertainty": _text(request, "page.review.filter.uncertainty"),
    }.get(review_type, _text(request, "page.review.filter.all"))


def _review_empty_message(request: Request, review_type: str) -> str:
    return {
        "summary": _text(request, "page.review.empty.summary"),
        "opportunity": _text(request, "page.review.empty.opportunity"),
        "risk": _text(request, "page.review.empty.risk"),
        "uncertainty": _text(request, "page.review.empty.uncertainty"),
    }.get(review_type, _text(request, "page.review.empty"))


def _review_filter_separator(request: Request) -> str:
    return "：" if _i18n(request).lang == "zh" else ": "


def _review_context_query(request: Request) -> list[tuple[str, str]]:
    review_type = _review_query_type(request)
    query: list[tuple[str, str]] = [("lang", _i18n(request).lang)]
    if review_type != "all":
        query.append(("type", review_type))
    return query


def _review_form_action(request: Request, target: str) -> str:
    return f"{target}?{urlencode(_review_context_query(request))}"


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


def _render_meta_section(request: Request, meta: object) -> str:
    if not isinstance(meta, dict) or not any(value is not None and str(value).strip() for value in meta.values()):
        return f"<div class='muted'>{escape(_text(request, 'shared.no_metadata'))}</div>"
    return _render_definition_rows([(str(key), value) for key, value in meta.items()])


def _render_database_note(request: Request, detail: str | None) -> str:
    text = str(detail or "").strip()
    if not text:
        return ""
    return (
        f"<div class='card'><strong>{escape(_text(request, 'shared.database_note'))}:</strong> "
        f"{escape(_text(request, 'shared.database_note_detail'))} "
        f"{escape(text)}</div>"
    )


def _empty_table_row(message: str, *, colspan: int) -> str:
    return f"<tr><td colspan='{colspan}'>{escape(message)}</td></tr>"


def _as_non_negative_int(value: object) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _render_document_signal_chips(request: Request, document: dict[str, object]) -> str:
    signals = [
        ("page.documents.signal.opportunities", document.get("opportunity_count")),
        ("page.documents.signal.risks", document.get("risk_count")),
        ("page.documents.signal.uncertainties", document.get("uncertainty_count")),
    ]
    return "".join(
        f"<span class='chip'>{escape(_text(request, key))}: {escape(str(_as_non_negative_int(value)))}</span>"
        for key, value in signals
    )


def _render_source_metadata(request: Request, source: dict[str, object]) -> str:
    rows: list[tuple[str, object]] = [
        (_text(request, "page.sources.col.fetch"), source.get("fetch_strategy")),
        (_text(request, "page.sources.maintenance_status"), source.get("maintenance_status")),
        (_text(request, "page.sources.col.last_import"), source.get("last_import_at")),
        (_text(request, "page.sources.col.last_result"), source.get("last_result")),
    ]
    web_metadata = source.get("web_metadata")
    if isinstance(web_metadata, dict):
        rows.extend((str(key), value) for key, value in web_metadata.items())
    rendered = _render_text_rows(rows)
    return rendered or "-"


def _document_time_value(document: dict[str, object]) -> str:
    def _valid_time(value: object) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        return "" if text == "-" else text

    published_at = _valid_time(document.get("published_at"))
    if published_at:
        return published_at
    created_at = _valid_time(document.get("created_at"))
    return created_at or "-"


def _system_storage_text(request: Request, key: object, default: str = "-") -> str:
    text = str(key or "").strip()
    if not text:
        return default
    return _text(request, text, text)


def _empty_list_item(message: str) -> str:
    return f"<li>{escape(message)}</li>"


def _format_ask_provider_name(request: Request, value: object) -> str:
    text = str(value or "").strip()
    return text or _text(request, "page.ask.provider_default_local_only")


def _format_count_label(request: Request, count: int, singular: str, plural: str | None = None) -> str:
    if _i18n(request).lang == "zh":
        return f"{count} {_text(request, 'shared.count.item_many')}"
    word = singular if count == 1 else (plural or f"{singular}s")
    return f"{count} {word}"


def _build_ask_metadata_rows(request: Request, result: dict[str, object], *, include_status: bool) -> list[tuple[str, object]]:
    status_label, _ = _build_ask_status(request, result)
    evidence_items = _coerce_items(result.get("evidence"))
    first_match_basis = ""
    for item in evidence_items:
        if isinstance(item, dict) and str(item.get("match_basis") or "").strip():
            first_match_basis = str(item.get("match_basis")).strip()
            break

    rows: list[tuple[str, object]] = []
    if include_status:
        rows.append((_text(request, "page.ask.meta.status"), status_label))
    rows.extend(
        [
            (_text(request, "page.ask.meta.mode"), str(result.get("answer_mode") or "local_only")),
            (_text(request, "page.ask.meta.provider"), _format_ask_provider_name(request, result.get("provider_name"))),
            (_text(request, "page.ask.meta.created"), str(result.get("created_at") or "").strip() or "-"),
            (_text(request, "page.ask.meta.evidence"), _format_count_label(request, len(evidence_items), "item")),
        ]
    )
    if first_match_basis:
        rows.append((_text(request, "page.ask.meta.match"), first_match_basis))
    note = str(result.get("note") or "").strip()
    if note:
        rows.append((_text(request, "page.ask.meta.note"), note))
    return rows


def _build_ask_status(request: Request, result: dict[str, object]) -> tuple[str, str]:
    answer_mode = str(result.get("answer_mode") or "local_only")
    if answer_mode == "insufficient_local_evidence":
        return _text(request, "page.ask.status.incomplete"), _text(request, "page.ask.status.incomplete_detail")
    if answer_mode == "local_fallback":
        return _text(request, "page.ask.status.fallback_warning"), _text(request, "page.ask.status.fallback_warning_detail")
    if answer_mode == "local_with_external_reasoning":
        return _text(request, "page.ask.status.bounded_external_reasoning"), _text(request, "page.ask.status.bounded_external_reasoning_detail")
    return _text(request, "page.ask.status.local_answer"), _text(request, "page.ask.status.local_answer_detail")


def _ask_status_class(result: dict[str, object]) -> str:
    answer_mode = str(result.get("answer_mode") or "local_only")
    if answer_mode == "local_fallback":
        return "ask-status warning"
    if answer_mode == "insufficient_local_evidence":
        return "ask-status incomplete"
    return "ask-status"


def _render_ask_evidence(request: Request, items: object) -> str:
    evidence_items = _coerce_items(items)
    if not evidence_items:
        return f"<div class='muted'>{escape(_text(request, 'page.ask.empty.evidence'))}</div>"
    cards: list[str] = []
    for raw_item in evidence_items:
        item = raw_item if isinstance(raw_item, dict) else {"title": str(raw_item)}
        title = str(item.get("title") or _text(request, "page.ask.fallback.untitled_evidence"))
        summary = str(item.get("summary") or "").strip()
        snippet = str(item.get("snippet") or "").strip() or summary or _text(request, "page.ask.fallback.no_snippet")
        source_type = str(item.get("evidence_type") or ("document" if item.get("document_id") else "brief"))
        match_basis = str(item.get("match_basis") or "").strip()
        if item.get("document_id"):
            title_html = f"<a href='/web/documents/{escape(str(item['document_id']))}'>{escape(title)}</a>"
        else:
            title_html = escape(title)
        meta_rows = [(_text(request, "page.ask.meta.source"), source_type)]
        if match_basis:
            meta_rows.append((_text(request, "page.ask.meta.match"), match_basis))
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


def _layout(request: Request, title: str, body: str, message: str | None = None) -> HTMLResponse:
    i18n = _i18n(request)
    nav_items = [
        ("/web/dashboard", i18n.text("nav.dashboard")),
        ("/web/documents", i18n.text("nav.documents")),
        ("/web/review", i18n.text("nav.review")),
        ("/web/watchlist", i18n.text("nav.watchlist")),
        ("/web/ask", i18n.text("nav.ask")),
        ("/web/sources", i18n.text("nav.sources")),
        ("/web/ai-settings", i18n.text("nav.ai_settings")),
        ("/web/system", i18n.text("nav.system")),
    ]
    nav_html = "".join(
        f'<a class="nav-link" href="{href}">{escape(label)}</a>' for href, label in nav_items
    )
    lang_switch_html = (
        f'<div class="inline">'
        f'<a class="nav-link" href="{escape(i18n.switch_url("zh"))}">{escape(i18n.text("layout.lang.zh"))}</a>'
        f'<a class="nav-link" href="{escape(i18n.switch_url("en"))}">{escape(i18n.text("layout.lang.en"))}</a>'
        f"</div>"
    )
    message_html = f'<div class="message">{escape(message)}</div>' if message else ""
    html = f"""
    <!doctype html>
    <html lang="{escape(i18n.lang)}">
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
            <div class="sub">{escape(i18n.text("layout.subtitle"))}</div>
          </div>
          {lang_switch_html}
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


def _review_redirect(request: Request, message: str) -> RedirectResponse:
    query = _review_context_query(request)
    query.append(("message", message))
    return RedirectResponse(f"/web/review?{urlencode(query)}", status_code=303)


@router.get("/web")
async def web_index(request: Request) -> RedirectResponse:
    return RedirectResponse(_dashboard_redirect_url(request), status_code=303)


@router.get("/web/dashboard")
async def dashboard(request: Request, message: str | None = None) -> HTMLResponse:
    data = service.get_dashboard_data()
    counts = data["counts"]
    system_status = data.get("system_status") or {}
    docs_html = "".join(
        f"<tr><td><a href='/web/documents/{escape(str(doc['id']))}'>{escape(str(doc['title']))}</a></td>"
        f"<td>{escape(str(doc['source_name']))}</td>"
        f"<td>{escape(str(doc.get('status', '-')))}</td>"
        f"<td>{escape(_document_time_value(doc))}</td>"
        f"<td>{escape(str(doc.get('summary_text', '-')))}</td>"
        f"<td>{_render_document_signal_chips(request, doc)}</td></tr>"
        for doc in data["recent_documents"]
    ) or _empty_table_row(_text(request, "shared.no_recent_documents"), colspan=6)
    topics_html = "".join(
        f"<li>{escape(name)} ({count})</li>" for name, count in data["top_topics"]
    ) or _empty_list_item(_text(request, "shared.no_topics"))
    qa_html = "".join(
        f"<li><strong>{escape(item['question'])}</strong> <span class='muted'>[{escape(item['answer_mode'])}]</span></li>"
        for item in data["qa_history"]
    ) or _empty_list_item(_text(request, "shared.no_recent_qa"))
    provider_html = "".join(
        f"<li>{escape(provider.name)} - {escape(provider.model)}"
        f" <span class='muted'>(default={_bool_label(provider.is_default)}, enabled={_bool_label(provider.is_enabled)})</span></li>"
        for provider in data["providers"]
    ) or _empty_list_item(_text(request, "shared.no_providers"))
    db_note = _render_database_note(request, data["db_error"])
    quick_actions_html = f"""
      <section class="card">
        <h2>{escape(_text(request, "page.dashboard.quick_actions"))}</h2>
        <div class="chips">
          <a class="nav-link" href="/web/documents">{escape(_text(request, "page.dashboard.action.documents"))}</a>
          <a class="nav-link" href="/web/ask">{escape(_text(request, "page.dashboard.action.ask"))}</a>
          <a class="nav-link" href="/web/review">{escape(_text(request, "page.dashboard.action.review"))}</a>
        </div>
      </section>
    """
    body = f"""
    <div class="grid cols-3">
      <div class="card"><div class="muted">{escape(_text(request, "page.dashboard.sources"))}</div><div class="metric">{counts['sources']}</div></div>
      <div class="card"><div class="muted">{escape(_text(request, "page.dashboard.documents"))}</div><div class="metric">{counts['documents']}</div></div>
      <div class="card"><div class="muted">{escape(_text(request, "page.dashboard.watchlist"))}</div><div class="metric">{counts['watchlist']}</div></div>
      <div class="card"><div class="muted">{escape(_text(request, "page.dashboard.review_edits"))}</div><div class="metric">{counts['reviews']}</div></div>
    </div>
    {db_note}
    <div class="grid cols-2" style="margin-top:16px;">
      <section class="card">
        <h2>{escape(_text(request, "page.dashboard.system_status"))}</h2>
        <div><strong>{escape(_text(request, "page.dashboard.label.database"))}:</strong> {escape(str(system_status.get('database_label') or 'unknown'))}</div>
        <div class="muted">{escape(str(system_status.get('database_detail') or _text(request, 'page.dashboard.fallback.database_detail')))}</div>
        <div style="margin-top:10px;"><strong>{escape(_text(request, "page.dashboard.label.providers"))}:</strong> {escape(str(system_status.get('provider_label') or _text(request, 'page.dashboard.fallback.provider_status')))}</div>
        <div><strong>{escape(_text(request, "page.dashboard.label.knowledge"))}:</strong> {escape(str(system_status.get('knowledge_label') or _text(request, 'page.dashboard.fallback.knowledge_status')))}</div>
      </section>
      {quick_actions_html}
      <section class="card">
        <h2>{escape(_text(request, "page.dashboard.recent_documents"))}</h2>
        <table>
          <thead><tr><th>{escape(_text(request, "page.dashboard.col.title"))}</th><th>{escape(_text(request, "page.dashboard.col.source"))}</th><th>{escape(_text(request, "page.dashboard.col.status"))}</th><th>{escape(_text(request, "page.dashboard.col.time"))}</th><th>{escape(_text(request, "page.dashboard.col.summary"))}</th><th>{escape(_text(request, "page.dashboard.col.signals"))}</th></tr></thead>
          <tbody>{docs_html}</tbody>
        </table>
      </section>
      <section class="card">
        <h2>{escape(_text(request, "page.dashboard.top_topics"))}</h2>
        <ul>{topics_html}</ul>
        <h3>{escape(_text(request, "page.dashboard.ai_providers"))}</h3>
        <ul>{provider_html}</ul>
        <h3>{escape(_text(request, "page.dashboard.recent_qa"))}</h3>
        <ul>{qa_html}</ul>
      </section>
    </div>
    """
    return _layout(request, _text(request, "page.dashboard.title"), body, message=message)


@router.get("/web/sources")
async def sources_page(request: Request, message: str | None = None) -> HTMLResponse:
    sources, error = service.list_source_page_views()
    rows = "".join(
        f"<tr>"
        f"<td><a href='/web/sources/{escape(str(source['id']))}'><strong>{escape(str(source['name']))}</strong></a>"
        f"<div class='muted'>{escape(_text(request, 'page.sources.label.notes'))}: {escape(str(source.get('notes') or '-'))}</div></td>"
        f"<td><span class='chip'>{escape(str(source['source_type']))}</span></td>"
        f"<td>{escape(str(source['url']))}</td>"
        f"<td><span class='chip'>{escape(str(source['credibility_level']))}</span></td>"
        f"<td><span class='chip'>{escape(str(source['activity_label']))}</span></td>"
        f"<td>{_render_source_metadata(request, source)}</td>"
        f"<td>"
        f"<a class='nav-link' href='/web/sources/{escape(str(source['id']))}'>{escape(_text(request, 'page.sources.action.edit'))}</a> "
        f"<form class='inline' method='post' action='/web/sources/{escape(str(source['id']))}/toggle'><button>{escape(_text(request, 'page.sources.action.toggle'))}</button></form> "
        f"<form class='inline' method='post' action='/web/sources/{escape(str(source['id']))}/import'><button>{escape(_text(request, 'page.sources.action.import'))}</button></form>"
        f"</td>"
        f"</tr>"
        for source in sources
    ) or _empty_table_row(_text(request, "page.sources.empty"), colspan=7)
    error_html = _render_database_note(request, error)
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
        <h2>{escape(_text(request, "page.sources.add"))}</h2>
        <p class="muted">{escape(_text(request, "page.sources.intro"))}</p>
        <form method="post" action="/web/sources">
          <input name="name" placeholder="{escape(_text(request, 'page.sources.placeholder.name'))}" required>
          <select name="source_type">{source_type_options}</select>
          <input name="url" placeholder="{escape(_text(request, 'page.sources.placeholder.url'))}">
          <select name="credibility_level">{credibility_options}</select>
          <input name="fetch_strategy" value="manual" placeholder="{escape(_text(request, 'page.sources.placeholder.fetch_strategy'))}">
          <select name="maintenance_status">{maintenance_status_options}</select>
          <textarea name="notes" placeholder="{escape(_text(request, 'page.sources.placeholder.notes'))}"></textarea>
          <textarea name="config_json" placeholder="{escape(_text(request, 'page.sources.placeholder.config_json'))}"></textarea>
          <label><input type="checkbox" name="is_active" checked> {escape(_text(request, 'page.sources.active'))}</label>
          <button>{escape(_text(request, "page.sources.create"))}</button>
        </form>
      </section>
      <section class="card">
        <h2>{escape(_text(request, "page.sources.registry"))}</h2>
        <table>
          <thead><tr><th>{escape(_text(request, 'page.sources.col.name'))}</th><th>{escape(_text(request, 'page.sources.col.type'))}</th><th>{escape(_text(request, 'page.sources.col.url'))}</th><th>{escape(_text(request, 'page.sources.col.cred'))}</th><th>{escape(_text(request, 'page.sources.col.status'))}</th><th>{escape(_text(request, 'page.sources.col.web_metadata'))}</th><th>{escape(_text(request, 'page.sources.col.actions'))}</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </section>
    </div>
    """
    return _layout(request, _text(request, "page.sources.title"), body, message=message)


@router.post("/web/sources")
async def create_source(request: Request) -> RedirectResponse:
    message = service.create_source(await _read_form(request))
    return _redirect("/web/sources", message)


@router.get("/web/sources/{source_id}")
async def source_detail(request: Request, source_id: str, message: str | None = None) -> HTMLResponse:
    source_view, error = service.get_source_page_view(source_id)
    if source_view is None:
        body = f"<div class='card'>{escape(_text(request, 'page.sources.not_found'))} {escape(error or '')}</div>"
        return _layout(request, _text(request, "page.sources.edit"), body, message=message)
    source_type_options = "".join(
        f"<option value='{escape(value)}'{' selected' if value == source_view['source_type'] else ''}>{escape(value)}</option>"
        for value in service.list_source_type_values()
    )
    credibility_options = "".join(
        f"<option value='{escape(value)}'{' selected' if value == source_view['credibility_level'] else ''}>{escape(value)}</option>"
        for value in service.list_credibility_values()
    )
    if source_view["maintenance_status"] == "formal_seed":
        maintenance_status_input = (
            f"<div class='pre'>formal_seed</div>"
            f"<input type='hidden' name='maintenance_status' value='formal_seed'>"
            f"<div class='muted'>{escape(_text(request, 'page.sources.detail.formal_seed_visible'))}</div>"
        )
    else:
        maintenance_status_options = "".join(
            f"<option value='{escape(value)}'{' selected' if value == source_view['maintenance_status'] else ''}>{escape(value)}</option>"
            for value in service.list_web_assignable_maintenance_status_values()
        )
        maintenance_status_input = (
            f"<select name='maintenance_status'>{maintenance_status_options}</select>"
            f"<div class='muted'>{escape(_text(request, 'page.sources.detail.formal_seed_not_handled'))}</div>"
        )
    body = f"""
    <div class="grid cols-2">
      <section class="card">
        <h2>{escape(_text(request, "page.sources.edit"))}</h2>
        <p class="muted">{escape(_text(request, "page.sources.detail_intro"))}</p>
        <form method="post" action="/web/sources/{escape(str(source_view['id']))}">
          <input name="name" value="{escape(str(source_view.get('editable_name', '')))}" required>
          <select name="source_type">{source_type_options}</select>
          <input name="url" value="{escape('' if source_view['url'] == '-' else str(source_view['url']))}" placeholder="{escape(_text(request, 'page.sources.placeholder.url'))}">
          <select name="credibility_level">{credibility_options}</select>
          <input name="fetch_strategy" value="{escape('' if source_view['fetch_strategy'] == '-' else str(source_view['fetch_strategy']))}">
          {maintenance_status_input}
          <textarea name="notes" placeholder="{escape(_text(request, 'page.sources.placeholder.notes'))}">{escape(str(source_view['notes']))}</textarea>
          <textarea name="config_json" placeholder="{escape(_text(request, 'page.sources.placeholder.config_json'))}">{escape(str(source_view['raw_config_json']))}</textarea>
          <label><input type="checkbox" name="is_active" {'checked' if source_view['is_active'] else ''}> {escape(_text(request, 'page.sources.active'))}</label>
          <button>{escape(_text(request, "page.sources.save"))}</button>
        </form>
      </section>
      <section class="card stack">
        <div><strong>{escape(_text(request, 'page.sources.label.source'))}:</strong> {escape(str(source_view['name']))}</div>
        <div><strong>{escape(_text(request, 'page.sources.label.status'))}:</strong> {escape(str(source_view['activity_label']))}</div>
        <div><strong>{escape(_text(request, "page.sources.maintenance_status"))}：</strong> {escape(str(source_view['maintenance_status']))}</div>
        <div><strong>{escape(_text(request, 'page.sources.label.last_import'))}:</strong> {escape(str(source_view['last_import_at']))}</div>
        <div><strong>{escape(_text(request, 'page.sources.label.last_result'))}:</strong> {escape(str(source_view['last_result']))}</div>
        <div><strong>{escape(_text(request, 'page.sources.label.notes'))}:</strong><div class="pre">{escape(str(source_view['notes'] or '-'))}</div></div>
        <div class="inline">
          <form class='inline' method='post' action='/web/sources/{escape(str(source_view['id']))}/toggle'><button>{escape(_text(request, 'page.sources.action.toggle_active'))}</button></form>
          <form class='inline' method='post' action='/web/sources/{escape(str(source_view['id']))}/import'><button>{escape(_text(request, 'page.sources.action.import_now'))}</button></form>
          <a href="/web/sources">{escape(_text(request, 'page.sources.action.back'))}</a>
        </div>
      </section>
    </div>
    """
    return _layout(request, _text(request, "page.sources.edit"), body, message=message)


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
    request: Request,
    message: str | None = None,
    q: str = "",
    source_id: str = "",
) -> HTMLResponse:
    documents, error = service.list_document_views(query=q, source_id=source_id)
    sources, _ = service.list_sources()
    source_options = [f"<option value=''>{escape(_text(request, 'page.documents.source_all'))}</option>"]
    selected_source_name = _text(request, "page.documents.source_all") if not source_id.strip() else _text(request, "page.documents.source_unknown")
    for source in sources:
        selected = " selected" if source_id == str(source.id) else ""
        if selected:
            selected_source_name = source.name
        source_options.append(f"<option value='{source.id}'{selected}>{escape(source.name)}</option>")
    has_filters = bool(q.strip() or source_id.strip())
    empty_message = _text(request, "page.documents.empty.filtered") if has_filters else _text(request, "page.documents.empty.all")
    rows = "".join(
        f"<tr>"
        f"<td><a href='/web/documents/{escape(str(doc['id']))}'>{escape(str(doc['title']))}</a></td>"
        f"<td>{escape(str(doc['source_name']))}</td>"
        f"<td>{escape(str(doc['status']))}</td>"
        f"<td>{escape(str(doc['language']))}</td>"
        f"<td>{escape(_document_time_value(doc))}</td>"
        f"<td>{escape(str(doc['summary_text']))}</td>"
        f"<td>{_render_document_signal_chips(request, doc)}</td>"
        f"<td><a href='/web/documents/{escape(str(doc['id']))}'>{escape(_text(request, 'page.documents.detail'))}</a></td>"
        f"</tr>"
        for doc in documents
    ) or _empty_table_row(empty_message, colspan=8)
    error_html = _render_database_note(request, error)
    filters_html = f"""
      <section class="card">
        <h2>{escape(_text(request, "page.documents.filters"))}</h2>
        <div><strong>{escape(_text(request, "page.documents.query"))}:</strong> {escape(q.strip() or _text(request, "page.documents.query_none"))}</div>
        <div><strong>{escape(_text(request, "page.documents.source"))}:</strong> {escape(selected_source_name)}</div>
      </section>
    """
    body = f"""
    {error_html}
    <div class="grid cols-2">
      <section class="card">
        <h2>{escape(_text(request, "page.documents.search"))}</h2>
        <form method="get" action="/web/documents">
          <input name="q" value="{escape(q)}" placeholder="{escape(_text(request, 'page.documents.placeholder.search'))}">
          <select name="source_id">{''.join(source_options)}</select>
          <button>{escape(_text(request, "page.documents.apply"))}</button>
        </form>
      </section>
      {filters_html}
    </div>
    <div class="grid" style="margin-top:16px;">
      <section class="card">
        <h2>{escape(_text(request, "page.documents.list"))}</h2>
        <table>
          <thead><tr><th>{escape(_text(request, "page.documents.col.title"))}</th><th>{escape(_text(request, "page.documents.col.source"))}</th><th>{escape(_text(request, "page.documents.col.status"))}</th><th>{escape(_text(request, "page.documents.col.language"))}</th><th>{escape(_text(request, "page.documents.col.time"))}</th><th>{escape(_text(request, "page.documents.col.summary"))}</th><th>{escape(_text(request, "page.documents.col.signals"))}</th><th>{escape(_text(request, "page.documents.col.detail"))}</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </section>
    </div>
    """
    return _layout(request, _text(request, "page.documents.title"), body, message=message)


@router.get("/web/documents/{document_id}")
async def document_detail(request: Request, document_id: str, message: str | None = None) -> HTMLResponse:
    document, error = service.get_document_view(document_id)
    if document is None:
        body = f"<div class='card'>{escape(_text(request, 'page.document_detail.not_found'))} {escape(error or '')}</div>"
        return _layout(request, _text(request, "page.document_detail.title"), body, message=message)
    entity_html = "".join(f"<span class='chip'>{escape(str(label))}</span>" for label in document["entities"])
    topic_html = "".join(f"<span class='chip'>{escape(str(label))}</span>" for label in document["topics"])
    key_points = "<br>".join(escape(str(point)) for point in document["key_points"])
    url_value = str(document["url"]).strip()
    url_html = f"<a href=\"{escape(url_value)}\">{escape(url_value)}</a>" if url_value else "-"
    entities_block = entity_html or f"<span class='muted'>{escape(_text(request, 'page.document_detail.no_entities'))}</span>"
    topics_block = topic_html or f"<span class='muted'>{escape(_text(request, 'page.document_detail.no_topics'))}</span>"
    body = f"""
    <div class="grid cols-2">
      <section class="card stack">
        <div><strong>{escape(_text(request, "page.document_detail.label.title"))}:</strong> {escape(str(document['title']))}</div>
        <div><strong>{escape(_text(request, "page.document_detail.label.source"))}:</strong> {escape(str(document['source_name']))}</div>
        <div><strong>{escape(_text(request, "page.document_detail.label.url"))}:</strong> {url_html}</div>
        <div><strong>{escape(_text(request, "page.document_detail.label.status"))}:</strong> {escape(str(document['status']))}</div>
        <div><strong>{escape(_text(request, "page.document_detail.label.language"))}:</strong> {escape(str(document['language']))}</div>
        <div><strong>{escape(_text(request, "page.document_detail.label.published"))}:</strong> {escape(str(document['published_at']))}</div>
        <div><strong>{escape(_text(request, "page.document_detail.label.summary_en"))}：</strong><div class="pre">{escape(str(document['summary_en'] or '-'))}</div></div>
        <div><strong>{escape(_text(request, "page.document_detail.label.summary_zh"))}：</strong><div class="pre">{escape(str(document['summary_zh'] or '-'))}</div></div>
        <div><strong>{escape(_text(request, "page.document_detail.label.key_points"))}：</strong><div class="pre">{key_points or '-'}</div></div>
      </section>
      <section class="card stack">
        <div><strong>{escape(_text(request, "page.document_detail.entities"))}</strong><div class="chips">{entities_block}</div></div>
        <div><strong>{escape(_text(request, "page.document_detail.topics"))}</strong><div class="chips">{topics_block}</div></div>
        <div><strong>{escape(_text(request, "page.document_detail.content_preview"))}</strong><div class="pre">{escape(str(document['content_preview'] or '-'))}</div></div>
        <div class="inline">
          <a href="/web/review">{escape(_text(request, "page.document_detail.go_review"))}</a>
          <a href="/web/ask">{escape(_text(request, "page.document_detail.ask"))}</a>
        </div>
      </section>
    </div>
    """
    if error:
        body = f"{_render_database_note(request, error)}{body}"
    return _layout(request, _text(request, "page.document_detail.title"), body, message=message)


@router.get("/web/review")
async def review_page(request: Request, message: str | None = None) -> HTMLResponse:
    review_type = _review_query_type(request)
    uncertainties = []
    risks = []
    opportunities = []
    documents = []
    uncertainty_error: str | None = None
    risk_error: str | None = None
    opportunity_error: str | None = None
    error: str | None = None

    if review_type in {"all", "uncertainty"}:
        uncertainties, uncertainty_error = service.list_review_uncertainties()
    if review_type in {"all", "risk"}:
        risks, risk_error = service.list_review_risks()
    if review_type in {"all", "opportunity"}:
        opportunities, opportunity_error = service.list_review_opportunities()
    if review_type in {"all", "summary"}:
        documents, error = service.list_review_documents()

    filter_html = "".join(
        f'<a class="nav-link" href="{escape(_review_filter_url(request, value))}">{escape(_text(request, key))}</a>'
        for value, key in (
            ("all", "page.review.filter.all"),
            ("summary", "page.review.filter.summary"),
            ("opportunity", "page.review.filter.opportunity"),
            ("risk", "page.review.filter.risk"),
            ("uncertainty", "page.review.filter.uncertainty"),
        )
    )
    filter_bar = f'<div class="inline">{filter_html}</div>'
    current_filter = (
        f'<div class="muted">{escape(_text(request, "page.review.current_filter"))}{escape(_review_filter_separator(request))}'
        f"{escape(_review_filter_label(request, review_type))}</div>"
    )
    sections = []
    uncertainty_sections = []
    risk_sections = []
    opportunity_sections = []
    for item in uncertainties:
        history_html = "".join(
            f"<li>{escape(edit.field_name)} -> {escape(str(edit.new_value))} <span class='muted'>{escape(str(edit.created_at))}</span></li>"
            for edit in item.history
        ) or _empty_list_item(_text(request, "page.review.no_history_item"))
        current_uncertainty_status = item.effective_values.get("uncertainty_status")
        uncertainty_status_options = []
        if current_uncertainty_status is None:
            uncertainty_status_options.append(
                f'<option value="__UNCHANGED__" selected>{escape(_text(request, "page.review.keep_auto_option"))}</option>'
            )
        for value in ("open", "watching", "resolved"):
            selected = " selected" if current_uncertainty_status == value else ""
            uncertainty_status_options.append(
                f'<option value="{escape(value)}"{selected}>{escape(value)}</option>'
            )
        uncertainty_sections.append(
            f"""
            <section class="card">
              <h2>{escape(_text(request, "page.review.uncertainty"))}</h2>
              <div><strong>{escape(item.uncertainty_item)}</strong></div>
              <div class="muted">{escape(_text(request, "page.review.label.brief_id"))}: {item.brief.id}</div>
              <div class="muted">{escape(_text(request, "page.review.label.uncertainty_item_id"))}: {escape(item.item_id)}</div>
                <div class="grid cols-2" style="margin-top:12px;">
                  <div>
                    <h3>{escape(_text(request, "page.review.automatic"))}</h3>
                    <div class="pre">uncertainty_note={escape(str(item.auto_values.get("uncertainty_note") or ""))}
uncertainty_status={escape(str(item.auto_values.get("uncertainty_status") or ""))}</div>
                  </div>
                  <div>
                    <h3>{escape(_text(request, "page.review.effective"))}</h3>
                    <form method="post" action="{escape(_review_form_action(request, f'/web/review/uncertainties/{item.brief.id}/{item.route_id}'))}">
                      <textarea name="uncertainty_note" placeholder="uncertainty_note">{escape(str(item.effective_values.get("uncertainty_note") or ""))}</textarea>
                      <label><input type="checkbox" name="reset_uncertainty_note"> {escape(_text(request, "page.review.reset_to_auto"))}</label>
                      <select name="uncertainty_status">{"".join(uncertainty_status_options)}</select>
                      <label><input type="checkbox" name="reset_uncertainty_status"> {escape(_text(request, "page.review.reset_to_auto"))}</label>
                      <input name="reason" placeholder="{escape(_text(request, 'page.review.reason.uncertainty'))}">
                      <button>{escape(_text(request, "page.review.save_uncertainty"))}</button>
                    </form>
                  </div>
                </div>
                <h3>{escape(_text(request, "page.review.history"))}</h3>
                <ul>{history_html}</ul>
              </section>
              """
        )
    for item in risks:
        history_html = "".join(
            f"<li>{escape(edit.field_name)} -> {escape(str(edit.new_value))} <span class='muted'>{escape(str(edit.created_at))}</span></li>"
            for edit in item.history
        ) or _empty_list_item(_text(request, "page.review.no_history_item"))
        severity_options = "".join(
            f"<option value='{escape(value)}'{' selected' if item.effective_values.get('severity') == value else ''}>{escape(value)}</option>"
            for value in ("high", "medium", "low")
        )
        risk_sections.append(
            f"""
            <section class="card">
              <h2>{escape(_text(request, "page.review.risk"))}</h2>
              <div><strong>{escape(str(item.risk_item.get("title") or _text(request, "page.review.untitled_risk")))}</strong></div>
              <div class="muted">{escape(_text(request, "page.review.label.brief_id"))}: {item.brief.id}</div>
              <div class="muted">{escape(_text(request, "page.review.label.risk_item_id"))}: {escape(item.item_id)}</div>
                <div class="grid cols-2" style="margin-top:12px;">
                  <div>
                    <h3>{escape(_text(request, "page.review.automatic"))}</h3>
                    <div class="pre">severity={escape(str(item.auto_values.get("severity") or ""))}
description={escape(str(item.auto_values.get("description") or ""))}</div>
                  </div>
                  <div>
                    <h3>{escape(_text(request, "page.review.effective"))}</h3>
                    <form method="post" action="{escape(_review_form_action(request, f'/web/review/risks/{item.brief.id}/{item.route_id}'))}">
                      <select name="severity">{severity_options}</select>
                      <label><input type="checkbox" name="reset_severity"> {escape(_text(request, "page.review.reset_to_auto"))}</label>
                      <textarea name="description" placeholder="description">{escape(str(item.effective_values.get("description") or ""))}</textarea>
                      <label><input type="checkbox" name="reset_description"> {escape(_text(request, "page.review.reset_to_auto"))}</label>
                      <input name="reason" placeholder="{escape(_text(request, 'page.review.reason.risk'))}">
                      <button>{escape(_text(request, "page.review.save_risk"))}</button>
                    </form>
                  </div>
                </div>
                <h3>{escape(_text(request, "page.review.history"))}</h3>
                <ul>{history_html}</ul>
              </section>
              """
        )
    for item in opportunities:
        opportunity = item.opportunity
        history_html = "".join(
            f"<li>{escape(edit.field_name)} -> {escape(str(edit.new_value))} <span class='muted'>{escape(str(edit.created_at))}</span></li>"
            for edit in item.history
        ) or _empty_list_item(_text(request, "page.review.no_history_item"))
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
              <h2>{escape(_text(request, "page.review.opportunity"))}</h2>
              <div><strong>{escape(opportunity.title_en or opportunity.title_zh or _text(request, "page.review.untitled_opportunity"))}</strong></div>
              <div class="muted">{escape(_text(request, "page.review.label.opportunity_target_id"))}: {opportunity.id}</div>
              <div class="muted">{escape(_text(request, "page.review.label.source_document"))}: {escape(item.source_document_title or '-')}</div>
                <div class="grid cols-2" style="margin-top:12px;">
                  <div>
                    <h3>{escape(_text(request, "page.review.automatic"))}</h3>
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
                    <h3>{escape(_text(request, "page.review.effective"))}</h3>
                    <form method="post" action="{escape(_review_form_action(request, f'/web/review/opportunities/{opportunity.id}'))}">
                    <input name="need_realness" type="number" min="1" max="10" value="{escape(str(item.effective_values.get("need_realness") or ""))}" placeholder="need_realness">
                    <label><input type="checkbox" name="reset_need_realness"> {escape(_text(request, "page.review.reset_to_auto"))}</label>
                    <input name="market_gap" type="number" min="1" max="10" value="{escape(str(item.effective_values.get("market_gap") or ""))}" placeholder="market_gap">
                    <label><input type="checkbox" name="reset_market_gap"> {escape(_text(request, "page.review.reset_to_auto"))}</label>
                    <input name="feasibility" type="number" min="1" max="10" value="{escape(str(item.effective_values.get("feasibility") or ""))}" placeholder="feasibility">
                    <label><input type="checkbox" name="reset_feasibility"> {escape(_text(request, "page.review.reset_to_auto"))}</label>
                    <input name="priority_score" type="number" min="1" max="10" value="{escape(str(item.effective_values.get("priority_score") or ""))}" placeholder="priority_score">
                    <label><input type="checkbox" name="reset_priority_score"> {escape(_text(request, "page.review.reset_to_auto"))}</label>
                    <input name="evidence_score" type="number" min="1" max="10" value="{escape(str(item.effective_values.get("evidence_score") or ""))}" placeholder="evidence_score">
                    <label><input type="checkbox" name="reset_evidence_score"> {escape(_text(request, "page.review.reset_to_auto"))}</label>
                    <input name="total_score" type="number" step="0.1" value="{escape(str(item.effective_values.get("total_score") or ""))}" placeholder="total_score">
                    <label><input type="checkbox" name="reset_total_score"> {escape(_text(request, "page.review.reset_to_auto"))}</label>
                    <select name="uncertainty">{uncertainty_options}</select>
                    <label><input type="checkbox" name="reset_uncertainty"> {escape(_text(request, "page.review.reset_to_auto"))}</label>
                    <input name="uncertainty_reason" value="{escape(str(item.effective_values.get("uncertainty_reason") or ""))}" placeholder="uncertainty_reason">
                    <label><input type="checkbox" name="reset_uncertainty_reason"> {escape(_text(request, "page.review.reset_to_auto"))}</label>
                    <select name="status">{status_options}</select>
                    <label><input type="checkbox" name="reset_status"> {escape(_text(request, "page.review.reset_to_auto"))}</label>
                      <input name="reason" placeholder="{escape(_text(request, 'page.review.reason.opportunity'))}">
                      <button>{escape(_text(request, "page.review.save_opportunity"))}</button>
                    </form>
                  </div>
                </div>
                <h3>{escape(_text(request, "page.review.history"))}</h3>
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
        ) or _empty_list_item(_text(request, "page.review.no_history_item"))
        auto_key_points_text = "\n".join(str(point) for point in item.auto_values.get("key_points") or [])
        effective_key_points_text = "\n".join(str(point) for point in item.effective_values.get("key_points") or [])
        sections.append(
            f"""
            <section class="card">
              <h2>{escape(_text(request, "page.review.summary"))}</h2>
              <div><strong>{escape(document.title)}</strong></div>
              <div class="muted">{escape(_text(request, "page.review.label.summary_target_id"))}: {summary.id}</div>
                <div class="grid cols-2" style="margin-top:12px;">
                  <div>
                    <h3>{escape(_text(request, "page.review.automatic"))}</h3>
                    <div class="pre">summary_zh={escape(str(item.auto_values.get("summary_zh") or ""))}
summary_en={escape(str(item.auto_values.get("summary_en") or ""))}
key_points={escape(auto_key_points_text)}</div>
                  </div>
                  <div>
                    <h3>{escape(_text(request, "page.review.effective"))}</h3>
                    <form method="post" action="{escape(_review_form_action(request, f'/web/review/{summary.id}'))}">
                    <textarea name="summary_zh" placeholder="summary_zh">{escape(str(item.effective_values.get("summary_zh") or ""))}</textarea>
                    <label><input type="checkbox" name="reset_summary_zh"> {escape(_text(request, "page.review.reset_to_auto"))}</label>
                    <textarea name="summary_en" placeholder="summary_en">{escape(str(item.effective_values.get("summary_en") or ""))}</textarea>
                    <label><input type="checkbox" name="reset_summary_en"> {escape(_text(request, "page.review.reset_to_auto"))}</label>
                    <textarea name="key_points" placeholder="{escape(_text(request, 'page.review.placeholder.key_points'))}">{escape(effective_key_points_text)}</textarea>
                    <label><input type="checkbox" name="reset_key_points"> {escape(_text(request, "page.review.reset_to_auto"))}</label>
                      <input name="reason" placeholder="{escape(_text(request, 'page.review.reason.summary'))}">
                      <button>{escape(_text(request, "page.review.save_summary"))}</button>
                    </form>
                  </div>
                </div>
                <h3>{escape(_text(request, "page.review.history"))}</h3>
                <ul>{history_html}</ul>
              </section>
              """
        )
    content = "".join(uncertainty_sections + risk_sections + opportunity_sections + sections)
    if not content:
        content = f"<div class='card'>{escape(_review_empty_message(request, review_type))}</div>"
    notes = []
    if uncertainty_error:
        notes.append(_render_database_note(request, uncertainty_error))
    if risk_error:
        notes.append(_render_database_note(request, risk_error))
    if opportunity_error:
        notes.append(_render_database_note(request, opportunity_error))
    if error:
        notes.append(_render_database_note(request, error))
    if notes:
        content = "".join(notes) + content
    content = f"{filter_bar}{current_filter}{content}"
    return _layout(request, _text(request, "page.review.title"), content, message=message)


@router.post("/web/review/{summary_id}")
async def save_review(summary_id: str, request: Request) -> RedirectResponse:
    message = service.save_summary_review(summary_id, await _read_form(request))
    return _review_redirect(request, message)


@router.post("/web/review/opportunities/{opportunity_id}")
async def save_opportunity_review(opportunity_id: str, request: Request) -> RedirectResponse:
    message = service.save_opportunity_review(opportunity_id, await _read_form(request))
    return _review_redirect(request, message)


@router.post("/web/review/risks/{brief_id}/{route_id}")
async def save_risk_review(brief_id: str, route_id: str, request: Request) -> RedirectResponse:
    message = service.save_risk_review(brief_id, route_id, await _read_form(request))
    return _review_redirect(request, message)


@router.post("/web/review/uncertainties/{brief_id}/{route_id}")
async def save_uncertainty_review(brief_id: str, route_id: str, request: Request) -> RedirectResponse:
    message = service.save_uncertainty_review(brief_id, route_id, await _read_form(request))
    return _review_redirect(request, message)


@router.get("/web/watchlist")
async def watchlist_page(request: Request, message: str | None = None) -> HTMLResponse:
    items, error = service.list_watchlist_page_views()
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
        related_documents = item.get("related_documents") if isinstance(item.get("related_documents"), list) else []
        related_html = "".join(
            f"<li><a href='/web/documents/{escape(str(doc.get('id', '')))}'>{escape(str(doc.get('title', '-')))}</a>"
            f"<div class='muted'>{escape(_text(request, 'page.watchlist.field.source'))}: {escape(str(doc.get('source_name', '-')))}"
            f" / {escape(_text(request, 'page.watchlist.field.time'))}: {escape(str(doc.get('published_at') or doc.get('created_at') or '-'))}</div></li>"
            for doc in related_documents
        ) or _empty_list_item(_text(request, "page.watchlist.no_related_documents"))
        detail_html = _render_text_rows(
            [
                (_text(request, "page.watchlist.field.type"), item.get("item_type")),
                (_text(request, "page.watchlist.field.priority"), item.get("priority_level")),
                (_text(request, "page.watchlist.field.status"), item.get("status")),
                (_text(request, "page.watchlist.field.group"), item.get("group_name")),
                (_text(request, "page.watchlist.field.notes"), item.get("notes")),
                (_text(request, "page.watchlist.field.linked_entity"), item.get("linked_entity")),
                (_text(request, "page.watchlist.field.updated"), item.get("updated_at")),
                (_text(request, "page.watchlist.field.created"), item.get("created_at")),
            ]
        )
        item_id = escape(str(item.get("id", "")))
        rows.append(
            f"""
            <section class="card">
              <h2>{escape(str(item.get("item_value", "-")))}</h2>
              <div class="stack">{detail_html}</div>
              <h3>{escape(_text(request, "page.watchlist.related_documents"))}</h3>
              <ul>{related_html}</ul>
              <div class="inline">
                <form class='inline' method='post' action='/web/watchlist/{item_id}/status'><input type='hidden' name='status' value='active'><button>{escape(_text(request, "page.watchlist.action.active"))}</button></form>
                <form class='inline' method='post' action='/web/watchlist/{item_id}/status'><input type='hidden' name='status' value='paused'><button>{escape(_text(request, "page.watchlist.action.pause"))}</button></form>
                <form class='inline' method='post' action='/web/watchlist/{item_id}/status'><input type='hidden' name='status' value='removed'><button>{escape(_text(request, "page.watchlist.action.remove"))}</button></form>
              </div>
            </section>
            """
        )
    error_html = _render_database_note(request, error)
    body = f"""
    {error_html}
    <div class="grid cols-2">
      <section class="card">
        <h2>{escape(_text(request, "page.watchlist.add"))}</h2>
        <form method="post" action="/web/watchlist">
          <select name="item_type">{type_options}</select>
          <input name="item_value" placeholder="{escape(_text(request, 'page.watchlist.placeholder.value'))}" required>
          <select name="priority_level">{priority_options}</select>
          <input name="group_name" placeholder="{escape(_text(request, 'page.watchlist.placeholder.group'))}">
          <textarea name="notes" placeholder="{escape(_text(request, 'page.watchlist.placeholder.notes'))}"></textarea>
          <button>{escape(_text(request, "page.watchlist.create"))}</button>
        </form>
      </section>
      <section class="stack">{''.join(rows) or f"<div class='card'>{escape(_text(request, 'page.watchlist.empty'))}</div>"}</section>
    </div>
    """
    return _layout(request, _text(request, "page.watchlist.title"), body, message=message)


@router.post("/web/watchlist")
async def create_watchlist(request: Request) -> RedirectResponse:
    message = service.create_watchlist_item(await _read_form(request))
    return _redirect("/web/watchlist", message)


@router.post("/web/watchlist/{item_id}/status")
async def set_watchlist_status(item_id: str, request: Request) -> RedirectResponse:
    form = await _read_form(request)
    return _redirect("/web/watchlist", service.update_watchlist_status(item_id, form.get("status", "")))


@router.get("/web/ask")
async def ask_page(request: Request, message: str | None = None) -> HTMLResponse:
    providers = [
        provider
        for provider in service.list_ai_providers()
        if provider.is_enabled and "qa" in provider.supported_tasks
    ]
    history = service.list_qa_history()[:10]
    provider_options = [f"<option value=''>{escape(_text(request, 'page.ask.default_provider'))}</option>"]
    for provider in providers:
        provider_options.append(
            f"<option value='{escape(provider.id)}'>{escape(provider.name)} - {escape(provider.model)}</option>"
        )
    history_html = "".join(
        f"""
        <section class='card'>
          <h2>{escape(item['question'])}</h2>
          <div class='stack muted'>{_render_text_rows(_build_ask_metadata_rows(request, item, include_status=True))}</div>
          <div class='pre'>{escape(_truncate_text(item['answer'], limit=220))}</div>
        </section>
        """
        for item in history
    ) or f"<div class='card'>{escape(_text(request, 'shared.no_recent_qa'))}</div>"
    body = f"""
    <div class="grid cols-2">
      <section class="card">
        <h2>{escape(_text(request, "page.ask.form_title"))}</h2>
        <form method="post" action="/web/ask">
          <textarea name="question" placeholder="{escape(_text(request, 'page.ask.placeholder.question'))}" required></textarea>
          <select name="provider_id">{''.join(provider_options)}</select>
          <button>{escape(_text(request, "page.ask.ask_button"))}</button>
        </form>
        <p class="muted">{escape(_text(request, "page.ask.retrieval_note"))}</p>
      </section>
      <section class="stack">{history_html}</section>
    </div>
    """
    return _layout(request, _text(request, "page.ask.title"), body, message=message)


@router.post("/web/ask")
async def ask_submit(request: Request) -> HTMLResponse:
    form = await _read_form(request)
    result = service.ask_question(question=form.get("question", ""), provider_id=form.get("provider_id", ""))
    status_label, status_message = _build_ask_status(request, result)
    status_class = _ask_status_class(result)
    run_metadata_html = _render_text_rows(_build_ask_metadata_rows(request, result, include_status=True))
    error_html = ""
    if str(result.get("error") or "").strip():
        error_html = f"""
        <section class="ask-section">
          <h2>{escape(_text(request, "page.ask.error_state"))}</h2>
          <div class="pre">{escape(str(result.get("error") or ""))}</div>
        </section>
        """
    body = f"""
    <div class="grid cols-2">
      <section class="card">
        <div class="{status_class}" style="margin-bottom:14px;">
          <strong>{escape(_text(request, "page.ask.status"))}: {escape(status_label)}</strong>
          <div class="muted">{escape(status_message)}</div>
        </div>
        <section class="ask-section">
          <h2>{escape(_text(request, "page.ask.question"))}</h2>
          <div class="pre">{escape(result['question'])}</div>
        </section>
        <section class="ask-section">
          <h2>{escape(_text(request, "page.ask.answer"))}</h2>
          <div class="pre">{escape(result['answer'])}</div>
        </section>
        <section class="ask-section">
          <h2>{escape(_text(request, "page.ask.run_details"))}</h2>
          <div class="stack">{run_metadata_html}</div>
        </section>
        {error_html}
      </section>
      <div class="stack">
        <section class="card">
          <h2>{escape(_text(request, "page.ask.evidence"))}</h2>
          <div class="compact-list">{_render_ask_evidence(request, result.get("evidence"))}</div>
        </section>
        <section class="card">
          <h2>{escape(_text(request, "page.ask.opportunities"))}</h2>
          {_render_structured_list(result.get("opportunities"), empty_message=_text(request, "page.ask.empty.opportunities"))}
        </section>
        <section class="card">
          <h2>{escape(_text(request, "page.ask.risks"))}</h2>
          {_render_structured_list(result.get("risks"), empty_message=_text(request, "page.ask.empty.risks"))}
        </section>
        <section class="card">
          <h2>{escape(_text(request, "page.ask.uncertainties"))}</h2>
          {_render_structured_list(result.get("uncertainties"), empty_message=_text(request, "page.ask.empty.uncertainties"))}
        </section>
        <section class="card">
          <h2>{escape(_text(request, "page.ask.related_topics"))}</h2>
          {_render_structured_list(result.get("related_topics"), empty_message=_text(request, "page.ask.empty.related_topics"))}
        </section>
        <section class="card">
          <h2>{escape(_text(request, "page.ask.meta"))}</h2>
          {_render_meta_section(request, result.get("meta"))}
          <div class="inline"><a href="/web/ask">{escape(_text(request, "page.ask.back"))}</a></div>
        </section>
      </div>
    </div>
    """
    return _layout(request, _text(request, "page.ask.title"), body)


@router.get("/web/ai-settings")
async def ai_settings_page(request: Request, message: str | None = None) -> HTMLResponse:
    providers = service.list_ai_providers()
    task_values = service.list_ai_task_values()
    rows = "".join(
        f"<tr><td>{escape(provider.name)}</td><td>{escape(provider.provider_type)}</td><td>{escape(provider.base_url)}</td>"
        f"<td>{escape(provider.model)}</td><td>{escape(provider.masked_key)}</td><td>{escape(str(provider.is_default))}</td>"
        f"<td>{escape(str(provider.is_enabled))}</td><td>{escape(', '.join(provider.supported_tasks))}</td>"
        f"<td>{escape(provider.last_test_status or '-')}</td>"
        f"<td><a class='nav-link' href='/web/ai-settings/{provider.id}'>{escape(_text(request, 'page.ai_settings.action.edit'))}</a> "
        f"<form class='inline' method='post' action='/web/ai-settings/{provider.id}/test'><button>{escape(_text(request, 'page.ai_settings.action.test'))}</button></form></td></tr>"
        for provider in providers
    ) or _empty_table_row(_text(request, "page.ai_settings.no_providers"), colspan=10)
    task_inputs = "".join(
        f"<label><input type='checkbox' name='task_{escape(task)}' checked> {escape(task)}</label>"
        for task in task_values
    )
    body = f"""
    <div class="grid cols-2">
      <section class="card">
        <h2>{escape(_text(request, "page.ai_settings.save_provider"))}</h2>
        <p class="muted">{escape(_text(request, "page.ai_settings.intro"))}</p>
        <form method="post" action="/web/ai-settings">
          <input name="name" placeholder="{escape(_text(request, 'page.ai_settings.placeholder.name'))}" required>
          <input name="provider_type" value="openai_compatible">
          <input name="base_url" value="https://api.openai.com/v1">
          <input name="model" placeholder="{escape(_text(request, 'page.ai_settings.placeholder.model'))}" required>
          <input name="api_key" placeholder="{escape(_text(request, 'page.ai_settings.placeholder.api_key'))}" required>
          <div class="stack">
            <strong>{escape(_text(request, "page.ai_settings.supported_tasks"))}</strong>
            <div class="chips">{task_inputs}</div>
          </div>
          <textarea name="notes" placeholder="{escape(_text(request, 'page.ai_settings.placeholder.notes'))}"></textarea>
          <label><input type="checkbox" name="is_enabled" checked> {escape(_text(request, "page.ai_settings.enabled"))}</label>
          <label><input type="checkbox" name="is_default"> {escape(_text(request, "page.ai_settings.default_provider"))}</label>
          <button>{escape(_text(request, "page.ai_settings.save_provider"))}</button>
        </form>
      </section>
      <section class="card">
        <h2>{escape(_text(request, "page.ai_settings.configured_providers"))}</h2>
        <table>
          <thead><tr><th>{escape(_text(request, "page.ai_settings.col.name"))}</th><th>{escape(_text(request, "page.ai_settings.col.type"))}</th><th>{escape(_text(request, "page.ai_settings.col.base_url"))}</th><th>{escape(_text(request, "page.ai_settings.col.model"))}</th><th>{escape(_text(request, "page.ai_settings.col.key"))}</th><th>{escape(_text(request, "page.ai_settings.col.default"))}</th><th>{escape(_text(request, "page.ai_settings.col.enabled"))}</th><th>{escape(_text(request, "page.ai_settings.col.tasks"))}</th><th>{escape(_text(request, "page.ai_settings.col.status"))}</th><th>{escape(_text(request, "page.ai_settings.col.actions"))}</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </section>
    </div>
    """
    return _layout(request, _text(request, "page.ai_settings.title"), body, message=message)


@router.post("/web/ai-settings")
async def save_ai_settings(request: Request) -> RedirectResponse:
    message = service.save_ai_provider(await _read_form(request))
    return _redirect("/web/ai-settings", message)


@router.get("/web/ai-settings/{provider_id}")
async def ai_provider_detail(request: Request, provider_id: str, message: str | None = None) -> HTMLResponse:
    provider = service.get_ai_provider(provider_id)
    if provider is None:
        body = f"<div class='card'>{escape(_text(request, 'page.ai_settings.not_found'))}</div>"
        return _layout(request, _text(request, "page.ai_settings.title"), body, message=message)

    task_inputs = "".join(
        f"<label><input type='checkbox' name='task_{escape(task)}' {'checked' if task in provider.supported_tasks else ''}> {escape(task)}</label>"
        for task in service.list_ai_task_values()
    )
    body = f"""
    <div class="grid cols-2">
      <section class="card">
        <h2>{escape(_text(request, "page.ai_settings.edit_provider"))}</h2>
        <form method="post" action="/web/ai-settings">
          <input type="hidden" name="provider_id" value="{escape(provider.id)}">
          <input name="name" value="{escape(provider.name)}" required>
          <input name="provider_type" value="{escape(provider.provider_type)}">
          <input name="base_url" value="{escape(provider.base_url)}">
          <input name="model" value="{escape(provider.model)}" required>
          <input name="api_key" placeholder="{escape(_text(request, 'page.ai_settings.placeholder.keep_key'))}">
          <div class="stack">
            <strong>{escape(_text(request, "page.ai_settings.supported_tasks"))}</strong>
            <div class="chips">{task_inputs}</div>
          </div>
          <textarea name="notes" placeholder="{escape(_text(request, 'page.ai_settings.label.notes'))}">{escape(provider.notes)}</textarea>
          <label><input type="checkbox" name="is_enabled" {'checked' if provider.is_enabled else ''}> {escape(_text(request, "page.ai_settings.enabled"))}</label>
          <label><input type="checkbox" name="is_default" {'checked' if provider.is_default else ''}> {escape(_text(request, "page.ai_settings.default_provider"))}</label>
          <button>{escape(_text(request, "page.ai_settings.save_provider"))}</button>
        </form>
      </section>
      <section class="card stack">
        <div><strong>{escape(_text(request, "page.ai_settings.label.supported_tasks"))}:</strong> {escape(', '.join(provider.supported_tasks))}</div>
        <div><strong>{escape(_text(request, "page.ai_settings.label.saved_key"))}:</strong> {escape(provider.masked_key or '-')}</div>
        <div><strong>{escape(_text(request, "page.ai_settings.label.last_test_status"))}:</strong> {escape(provider.last_test_status or '-')}</div>
        <div><strong>{escape(_text(request, "page.ai_settings.label.last_test_message"))}:</strong><div class="pre">{escape(provider.last_test_message or '-')}</div></div>
        <div><strong>{escape(_text(request, "page.ai_settings.label.notes"))}:</strong><div class="pre">{escape(provider.notes or '-')}</div></div>
        <div class="inline">
          <form class='inline' method='post' action='/web/ai-settings/{provider.id}/test'><button>{escape(_text(request, "page.ai_settings.action.test_provider"))}</button></form>
          <a href="/web/ai-settings">{escape(_text(request, "page.ai_settings.action.back"))}</a>
        </div>
      </section>
    </div>
    """
    return _layout(request, _text(request, "page.ai_settings.title"), body, message=message)


@router.post("/web/ai-settings/{provider_id}/test")
async def test_ai_provider(provider_id: str) -> RedirectResponse:
    message = service.test_ai_provider(provider_id)
    return _redirect(f"/web/ai-settings/{provider_id}", message)


@router.get("/web/system")
async def system_page(request: Request, message: str | None = None) -> HTMLResponse:
    status = service.get_system_page_data()
    checks_html = "".join(
        f"<div><strong>{escape(item['label'])}:</strong> {escape(item['status'])}</div>"
        f"<div class='muted'>{escape(item['detail'])}</div>"
        for item in status["checks"]
    ) or f"<div class='muted'>{escape(_text(request, 'page.system.no_checks'))}</div>"
    file_rows = "".join(
        f"<tr><td>{escape(item['path'])}</td><td>{escape(item['exists_label'])}</td><td>{item['size_bytes']}</td></tr>"
        for item in status["storage_files"]
    )
    storage_overview_rows = "".join(
        f"<tr>"
        f"<td>{escape(_system_storage_text(request, item.get('area_key')))}</td>"
        f"<td>{escape(_system_storage_text(request, item.get('primary_key')))}</td>"
        f"<td>{escape(_system_storage_text(request, item.get('fallback_key')))}</td>"
        f"<td>{escape(_system_storage_text(request, item.get('detail_key')))}</td>"
        f"<td>{escape(str(item.get('path') or '-'))}</td>"
        f"</tr>"
        for item in status.get("storage_overview", [])
    ) or f"<tr><td colspan='5'>{escape(_text(request, 'page.system.storage.empty'))}</td></tr>"
    count_rows = "".join(
        f"<tr><td>{escape(item['name'])}</td><td>{item['count']}</td></tr>" for item in status["database_counts"]
    ) or f"<tr><td colspan='2'>{escape(_text(request, 'shared.no_database_counts'))}</td></tr>"
    file_rows = file_rows or f"<tr><td colspan='3'>{escape(_text(request, 'shared.no_storage_files'))}</td></tr>"
    note_html = _render_database_note(request, status.get("counts_error"))
    body = f"""
    {note_html}
    <div class="grid cols-2">
      <section class="card">
        <h2>{escape(_text(request, "page.system.storage_overview"))}</h2>
        <div class="muted">{escape(_text(request, "page.system.storage.group.main_knowledge"))} / {escape(_text(request, "page.system.storage.group.web_config"))}</div>
        <table>
          <thead><tr><th>{escape(_text(request, "page.system.col.area"))}</th><th>{escape(_text(request, "page.system.col.primary"))}</th><th>{escape(_text(request, "page.system.col.fallback"))}</th><th>{escape(_text(request, "page.system.col.detail"))}</th><th>{escape(_text(request, "page.system.col.path"))}</th></tr></thead>
          <tbody>{storage_overview_rows}</tbody>
        </table>
      </section>
      <section class="card stack">
        <h2>{escape(_text(request, "page.system.checks"))}</h2>
        {checks_html}
      </section>
      <section class="card">
        <h2>{escape(_text(request, "page.system.database_counts"))}</h2>
        <table><tbody>{count_rows}</tbody></table>
      </section>
      <section class="card">
        <h2>{escape(_text(request, "page.system.storage_files"))}</h2>
        <table>
          <thead><tr><th>{escape(_text(request, "page.system.col.path"))}</th><th>{escape(_text(request, "page.system.col.exists"))}</th><th>{escape(_text(request, "page.system.col.size_bytes"))}</th></tr></thead>
          <tbody>{file_rows}</tbody>
        </table>
      </section>
    </div>
    """
    return _layout(request, _text(request, "page.system.title"), body, message=message)
