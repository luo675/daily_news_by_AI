"""Minimal URL-based article import helpers for RawDocumentInput."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from src.ingestion.adapters import BlogAdapter
from src.ingestion.schemas import RawDocumentInput

DEFAULT_USER_AGENT = "daily-news-url-importer/0.1"
SUPPORTED_URL_LIST_SUFFIXES = {".txt", ".json"}


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


@dataclass
class FetchedArticle:
    url: str
    final_url: str
    content_type: str | None
    title: str
    author: str | None
    published_at: datetime | None
    language: str | None
    content_text: str


class ArticleHTMLParser(HTMLParser):
    """Extract a minimal article payload from generic HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page_title: str = ""
        self.og_title: str | None = None
        self.author: str | None = None
        self.published_at: str | None = None
        self.language: str | None = None
        self._capture_title = False
        self._skip_depth = 0
        self._in_paragraph = False
        self._paragraph_buffer: list[str] = []
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value for key, value in attrs}
        lowered_tag = tag.lower()

        if lowered_tag == "html" and attr_map.get("lang"):
            self.language = attr_map["lang"]

        if lowered_tag == "title":
            self._capture_title = True
            return

        if lowered_tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return

        if lowered_tag == "meta":
            self._handle_meta_tag(attr_map)
            return

        if lowered_tag == "p":
            self._in_paragraph = True
            self._paragraph_buffer = []
            return

        if self._in_paragraph and lowered_tag == "br":
            self._paragraph_buffer.append(" ")

    def handle_endtag(self, tag: str) -> None:
        lowered_tag = tag.lower()
        if lowered_tag == "title":
            self._capture_title = False
            return
        if lowered_tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if lowered_tag == "p" and self._in_paragraph:
            paragraph = _normalize_whitespace(unescape("".join(self._paragraph_buffer)))
            if paragraph:
                self.paragraphs.append(paragraph)
            self._paragraph_buffer = []
            self._in_paragraph = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._capture_title:
            self.page_title += data
        if self._in_paragraph:
            self._paragraph_buffer.append(data)

    def _handle_meta_tag(self, attrs: dict[str, str | None]) -> None:
        key = (attrs.get("property") or attrs.get("name") or "").strip().lower()
        content = (attrs.get("content") or "").strip()
        if not key or not content:
            return

        if key in {"og:title", "twitter:title"} and not self.og_title:
            self.og_title = content
        elif key in {"author", "article:author"} and not self.author:
            self.author = content
        elif key in {
            "article:published_time",
            "published_time",
            "pubdate",
            "date",
            "dc.date",
        } and not self.published_at:
            self.published_at = content


def fetch_article(url: str, *, timeout: int = 20) -> FetchedArticle:
    request = Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get_content_type()
        charset = response.headers.get_content_charset() or "utf-8"
        html = response.read().decode(charset, errors="replace")
        final_url = response.geturl()

    parser = ArticleHTMLParser()
    parser.feed(html)

    title = _normalize_whitespace(parser.og_title or parser.page_title or "")
    if not title:
        parsed = urlparse(final_url)
        title = parsed.path.rstrip("/").split("/")[-1] or parsed.netloc

    paragraphs = parser.paragraphs
    content_text = "\n\n".join(paragraphs)
    if not content_text:
        raise ValueError(f"No paragraph content extracted from URL: {final_url}")

    language = parser.language.strip().lower() if parser.language else None
    if language:
        language = language.split("-", 1)[0]

    return FetchedArticle(
        url=url,
        final_url=final_url,
        content_type=content_type,
        title=title,
        author=parser.author,
        published_at=_parse_datetime(parser.published_at),
        language=language,
        content_text=content_text,
    )


def import_url_as_raw_document(url: str, *, timeout: int = 20) -> RawDocumentInput:
    article = fetch_article(url, timeout=timeout)
    adapter = BlogAdapter()
    return adapter.map_to_document(
        title=article.title,
        content_text=article.content_text,
        url=article.final_url,
        author=article.author,
        published_at=article.published_at,
        language=article.language or "en",
        metadata={
            "blog_platform": urlparse(article.final_url).netloc,
            "original_format": "html",
            "extra": {
                "import_method": "single_url",
                "requested_url": article.url,
                "resolved_url": article.final_url,
                "content_type": article.content_type,
            },
        },
    )


def _deduplicate_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduplicated.append(url)
    return deduplicated


def _load_url_list_file(path: Path) -> list[str]:
    """Load URL entries from one plain-text or JSON file."""
    try:
        raw_text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise ValueError(f"URL list file not found: {path}") from exc

    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON URL list: {exc}") from exc
        if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
            raise ValueError("JSON URL list must be an array of URL strings.")
        return [item.strip() for item in payload if item.strip()]

    urls = []
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        urls.append(stripped)
    return urls


def _load_url_list_directory(path: Path) -> list[str]:
    """Load and merge URL entries from a seed directory."""
    candidate_files = sorted(
        child for child in path.iterdir() if child.is_file() and child.suffix.lower() in SUPPORTED_URL_LIST_SUFFIXES
    )
    if not candidate_files:
        supported = ", ".join(sorted(SUPPORTED_URL_LIST_SUFFIXES))
        raise ValueError(f"URL seed directory must contain at least one {supported} file: {path}")

    urls: list[str] = []
    for child in candidate_files:
        urls.extend(_load_url_list_file(child))
    return _deduplicate_urls(urls)


def load_url_list(path: Path) -> list[str]:
    """Load a minimal URL list from a file or a seed directory."""
    if path.is_dir():
        urls = _load_url_list_directory(path)
    else:
        urls = _load_url_list_file(path)

    if not urls:
        raise ValueError("URL list input must contain at least one URL.")
    return urls
