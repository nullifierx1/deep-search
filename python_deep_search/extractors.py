from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript|iframe|svg)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)

_FILE_EXT_BLOCK = re.compile(r"\.(css|js|svg|png|ico|jpe?g|gif|webp|woff2?|ttf|eot|xml|rss|json|webmanifest)(\?|#|$)", re.IGNORECASE)

_WIKI_NON_CONTENT = re.compile(r"^/w/(load\.php|index\.php|api\.php)", re.IGNORECASE)


class _HrefCollector(HTMLParser):
    """Collect href values without relying on a fragile regular expression."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name.lower() == "href" and value:
                self.hrefs.append(value.strip())
                return


def clean_text(raw: str) -> str:
    text = SCRIPT_STYLE_RE.sub(" ", raw)
    text = html.unescape(text)
    text = TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_content_link(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()

    if _FILE_EXT_BLOCK.search(path):
        return False

    if _WIKI_NON_CONTENT.match(path):
        return False

    # A path such as /article-123, /?id=123, or /blog/article can be a
    # legitimate result.  Site navigation cannot be identified reliably from
    # the URL alone, so keep it instead of silently losing search results.

    return True


def extract_links(page_html: str, page_url: str, limit: int | None = None) -> list[str]:
    """Extract unique HTTP(S) links, prioritising the current site's links.

    ``page_url`` is the final page URL, rather than a site's home page, so
    relative links are resolved the same way a browser resolves them.
    """
    seen: set[str] = set()
    same_domain: list[str] = []
    other_domain: list[str] = []

    base_parsed = urlparse(page_url)
    base_netloc = base_parsed.netloc

    parser = _HrefCollector()
    try:
        parser.feed(page_html)
    except Exception:
        # HTMLParser is tolerant, but a malformed page must not abort search.
        pass

    for raw_url in parser.hrefs:
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
        if parsed.netloc == base_netloc:
            if _is_content_link(absolute_url):
                same_domain.append(absolute_url)
        else:
            lower_url = absolute_url.lower()
            if not any(x in lower_url for x in ("cdn.", "static.", "assets.", "avatars.", "gravatar.", "fonts.", "googleapis.", "gstatic.")):
                other_domain.append(absolute_url)

    result = same_domain + other_domain
    return result if limit is None else result[:limit]


def extract_regex_matches(page_html: str, regex_pattern: str, max_results: int = 10) -> list[str]:
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
