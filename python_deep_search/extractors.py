from __future__ import annotations

import html
import json
import re
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript|iframe|svg)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)

_FILE_EXT_BLOCK = re.compile(r"\.(css|js|svg|png|ico|jpe?g|gif|webp|woff2?|ttf|eot|xml|rss|json|webmanifest)(\?|#|$)", re.IGNORECASE)

_WIKI_NON_CONTENT = re.compile(r"^/w/(load\.php|index\.php|api\.php)", re.IGNORECASE)
_NAVIGATION_NOISE_FILE = Path(__file__).with_name("navigation_noise.json")
_DEFAULT_NAVIGATION_PATHS = {
    "",
    "/",
}


class _HrefCollector(HTMLParser):
    """Collect href values without relying on a fragile regular expression."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._current_href: str | None = None
        self._current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        if tag_name == "img" and self._current_href is not None:
            for name, value in attrs:
                if name.lower() in {"alt", "title", "aria-label"} and value:
                    self._current_text.append(value)
            return
        if tag_name != "a":
            return
        href = None
        label_parts: list[str] = []
        for name, value in attrs:
            lower_name = name.lower()
            if lower_name == "href" and value:
                href = value.strip()
            elif lower_name in {"title", "aria-label"} and value:
                label_parts.append(value)
        if href:
            self._current_href = href
            self._current_text = label_parts

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._current_href is not None:
            link_text = " ".join(part.strip() for part in self._current_text if part.strip())
            self.hrefs.append(self._current_href)
            self.links.append((self._current_href, link_text))
            self._current_href = None
            self._current_text = []

    def close(self) -> None:
        super().close()
        if self._current_href is not None:
            link_text = " ".join(part.strip() for part in self._current_text if part.strip())
            self.hrefs.append(self._current_href)
            self.links.append((self._current_href, link_text))
            self._current_href = None
            self._current_text = []


def clean_text(raw: str) -> str:
    text = SCRIPT_STYLE_RE.sub(" ", raw)
    text = html.unescape(text)
    text = TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_noise_path(path: str) -> str:
    normalized = path.strip().lower()
    if not normalized:
        return ""
    if not normalized.startswith("/"):
        normalized = "/" + normalized
    return normalized.rstrip("/") or "/"


@lru_cache(maxsize=1)
def _navigation_noise_paths() -> set[str]:
    paths = set(_DEFAULT_NAVIGATION_PATHS)
    try:
        with _NAVIGATION_NOISE_FILE.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return paths

    if isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict):
        entries = raw.get("paths", [])
    else:
        entries = []

    for entry in entries:
        if isinstance(entry, str):
            paths.add(_normalize_noise_path(entry))
    return paths


def _is_content_link(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower().rstrip("/") or "/"

    if _FILE_EXT_BLOCK.search(path):
        return False

    if _WIKI_NON_CONTENT.match(path):
        return False

    if path in _navigation_noise_paths():
        return False

    # A path such as /article-123, /?id=123, or /blog/article can be a
    # legitimate result.  Site navigation cannot be identified reliably from
    # the URL alone, so keep it instead of silently losing search results.

    return True


def _query_terms(query: str | None) -> list[str]:
    if not query:
        return []
    terms: list[str] = []
    for group in query.split("|"):
        cleaned = re.sub(r"[\[\]]", "", group.lower())
        for term in re.findall(r"[\w-]{3,}", cleaned):
            if term not in terms:
                terms.append(term)
    return terms


def _is_query_relevant(url: str, link_text: str, terms: list[str]) -> bool:
    if not terms:
        return False
    parsed = urlparse(url)
    haystack = " ".join(
        [
            unquote(parsed.path).lower(),
            unquote(parsed.query).lower(),
            link_text.lower(),
        ]
    )
    return any(term in haystack for term in terms)


def extract_links(
    page_html: str,
    page_url: str,
    limit: int | None = None,
    *,
    query: str | None = None,
    prefer_query_matches: bool = False,
) -> list[str]:
    """Extract unique HTTP(S) links, prioritising the current site's links.

    ``page_url`` is the final page URL, rather than a site's home page, so
    relative links are resolved the same way a browser resolves them.
    """
    seen: set[str] = set()
    same_domain: list[str] = []
    other_domain: list[str] = []
    relevant_same_domain: list[str] = []
    relevant_other_domain: list[str] = []
    terms = _query_terms(query)

    base_parsed = urlparse(page_url)
    base_netloc = base_parsed.netloc

    parser = _HrefCollector()
    try:
        parser.feed(page_html)
        parser.close()
    except Exception:
        # HTMLParser is tolerant, but a malformed page must not abort search.
        pass

    for raw_url, link_text in parser.links:
        if raw_url.startswith(("javascript:", "mailto:", "#", "data:")):
            continue

        absolute_url = urljoin(page_url, raw_url)
        absolute_url = absolute_url.split("#", 1)[0]
        if absolute_url in seen:
            continue
        seen.add(absolute_url)

        if not absolute_url.startswith(("http://", "https://")):
            continue

        parsed = urlparse(absolute_url)
        relevant = _is_query_relevant(absolute_url, link_text, terms)
        if parsed.netloc == base_netloc:
            if _is_content_link(absolute_url):
                if relevant:
                    relevant_same_domain.append(absolute_url)
                else:
                    same_domain.append(absolute_url)
        else:
            lower_url = absolute_url.lower()
            if not any(x in lower_url for x in ("cdn.", "static.", "assets.", "avatars.", "gravatar.", "fonts.", "googleapis.", "gstatic.")):
                if relevant:
                    relevant_other_domain.append(absolute_url)
                else:
                    other_domain.append(absolute_url)

    relevant_result = relevant_same_domain + relevant_other_domain
    if prefer_query_matches:
        result = relevant_result
    else:
        result = relevant_result + same_domain + other_domain
    return result if limit is None else result[:limit]


def extract_regex_matches(page_html: str, regex_pattern: str, max_results: int = 10) -> list[str]:
    if not regex_pattern:
        return []

    try:
        compiled = re.compile(regex_pattern, re.IGNORECASE | re.DOTALL)
    except re.error as e:
        raise ValueError(f"Некорректный regex: {e}") from e

    clean = clean_text(page_html)
    found = compiled.findall(clean)
    if not found:
        return []

    cleaned: list[str] = []
    seen: set[str] = set()

    for item in found:
        if isinstance(item, tuple):
            text = " ".join(str(x) for x in item if x)
        else:
            text = str(item)
        text = text.strip()
        if len(text) < 3:
            continue
        if text in seen:
            continue
        seen.add(text)
        cleaned.append(text[:350])
        if len(cleaned) >= max_results:
            break

    return cleaned


_QUERY_META_RE = re.compile(r"\[")


def _query_word_to_pattern(word: str) -> str:
    escaped = re.escape(word)
    escaped = escaped.replace(r"\|", "|")
    escaped = re.sub(
        r"\\\[(.*?)\\\]",
        lambda m: "[" + m.group(1).replace(r"\-", "-") + "]",
        escaped,
    )
    return escaped


def extract_query_snippets(page_html: str, query: str, max_results: int = 10) -> list[str]:
    groups = [g.strip() for g in query.split("|")]
    groups = [g for g in groups if g]
    if not groups:
        return []

    text = clean_text(page_html)
    low = text.lower()

    snippets: list[str] = []
    seen: set[str] = set()

    for group in groups:
        words = [w for w in re.split(r"\s+", group) if w]
        if not words:
            continue

        for word in words:
            lw = word.lower()
            has_meta = _QUERY_META_RE.search(lw)

            if has_meta:
                pattern = re.compile(_query_word_to_pattern(lw), re.IGNORECASE)
                for m in pattern.finditer(text):
                    idx = m.start()
                    left = max(0, idx - 80)
                    right = min(len(text), idx + max(m.end() - m.start(), 1) + 120)
                    snippet = text[left:right].strip()
                    snippet = re.sub(r"\s+", " ", snippet)
                    if len(snippet) > 15 and snippet not in seen:
                        seen.add(snippet)
                        snippets.append(snippet)
                        if len(snippets) >= max_results:
                            return snippets
            else:
                start = 0
                while True:
                    idx = low.find(lw, start)
                    if idx == -1:
                        break
                    left = max(0, idx - 80)
                    right = min(len(text), idx + max(len(word), 1) + 120)
                    snippet = text[left:right].strip()
                    snippet = re.sub(r"\s+", " ", snippet)
                    if len(snippet) > 15 and snippet not in seen:
                        seen.add(snippet)
                        snippets.append(snippet)
                        if len(snippets) >= max_results:
                            return snippets
                    start = idx + len(word)

    return snippets
