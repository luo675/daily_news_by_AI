from __future__ import annotations

from fastapi import Request

from src.web.i18n import build_lang_switch_url, resolve_lang, t


def _request(path: str, query_string: bytes = b"", cookie_header: str = "") -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if cookie_header:
        headers.append((b"cookie", cookie_header.encode("utf-8")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query_string,
        "headers": headers,
    }
    return Request(scope)


def test_resolve_lang_prefers_query_then_cookie_then_default() -> None:
    assert resolve_lang(_request("/web/dashboard", b"lang=en", "daily_news_lang=zh")) == "en"
    assert resolve_lang(_request("/web/dashboard", b"", "daily_news_lang=en")) == "en"
    assert resolve_lang(_request("/web/dashboard")) == "zh"


def test_resolve_lang_ignores_invalid_values() -> None:
    assert resolve_lang(_request("/web/dashboard", b"lang=fr", "daily_news_lang=en")) == "en"
    assert resolve_lang(_request("/web/dashboard", b"lang=fr", "daily_news_lang=fr")) == "zh"


def test_t_falls_back_to_default_language_then_identifiable_marker() -> None:
    assert t("en", "page.dashboard.title") == "Dashboard"
    assert t("en", "page.ask.only_zh_fallback") == "仅中文回退"
    assert t("en", "page.only_zh_example", default=None) == "[page.only_zh_example]"
    assert t("en", "page.dashboard.title", default="fallback") == "Dashboard"


def test_build_lang_switch_url_preserves_path_and_query() -> None:
    request = _request("/web/documents", b"q=ai+tools&source_id=123&lang=zh")

    assert build_lang_switch_url(request, "en") == "/web/documents?q=ai+tools&source_id=123&lang=en"
