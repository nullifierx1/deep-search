from __future__ import annotations

import html
import re
from urllib.parse import urljoin, urlparse

LINK_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript|iframe|svg)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)

_SAME_DOMAIN_LIMIT = 30
_OTHER_DOMAIN_LIMIT = 3

_NON_CONTENT_PATH_PREFIXES = (
    "/login", "/signup", "/register", "/signin", "/logout",
    "/search", "/account", "/settings", "/preferences",
    "/about", "/contact", "/privacy", "/terms", "/legal", "/policy",
    "/careers", "/press", "/pricing", "/products",
    "/features", "/download", "/api", "/feed", "/rss",
    "/blog", "/news", "/events", "/community", "/tour",
    "/teams", "/enterprise", "/marketplace", "/explore",
    "/topics", "/tags", "/users", "/jobs", "/advertising",
    "/cookie", "/cookies", "/consent", "/security",
    "/opensearch", "/manifest", "/robots",
    "/cdn-cgi", "/load.php", "/static/",
)

_NON_CONTENT_SEGMENTS = (
    "search", "feed", "rss", "login", "signup", "signin", "register",
    "account", "settings", "about", "contact", "privacy", "terms",
    "legal", "policy", "careers", "press", "pricing",
    "features", "download", "api", "blog", "news", "events",
    "community", "tour", "teams", "enterprise", "marketplace",
    "explore", "topics", "tags", "users", "jobs", "advertising",
    "solutions", "use-case", "industry", "sandbox", "hubs", "auth",
    "articles", "start", "resources", "open-source", "sponsors",
    "accelerator", "stargazers", "companies", "docs",
    "feedback", "help", "beta",
)

_FILE_EXT_BLOCK = re.compile(r"\.(css|js|svg|png|ico|jpe?g|gif|webp|woff2?|ttf|eot|xml|rss|json|webmanifest)(\?|#|$)", re.IGNORECASE)

_WIKI_NON_CONTENT = re.compile(r"^/w/(load\.php|index\.php|api\.php)", re.IGNORECASE)


def clean_text(raw: str) -> str:
    text = SCRIPT_STYLE_RE.sub(" ", raw)
    text = html.unescape(text)
    text = TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_content_link(url: str, base_netloc: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()

    if _FILE_EXT_BLOCK.search(path):
        return False

    if _WIKI_NON_CONTENT.match(path):
        return False

    if parsed.netloc != base_netloc:
        return False

    segments = [s for s in path.split("/") if s]
    if not segments:
        return False

    for seg in segments:
        if seg in _NON_CONTENT_SEGMENTS:
            return False

    if len(segments) < 2:
        return False

    if path in _NON_CONTENT_PATH_PREFIXES or any(
        path.startswith(p + "/") or path.startswith(p + "?") for p in _NON_CONTENT_PATH_PREFIXES
    ):
        return False

    return True


def extract_links(page_html: str, base_url: str, limit: int = 20) -> list[str]:
    seen: set[str] = set()
    same_domain: list[str] = []
    other_domain: list[str] = []

    base_parsed = urlparse(base_url)
    base_netloc = base_parsed.netloc

    for raw_url in LINK_RE.findall(page_html):
        if raw_url.startswith(("javascript:", "mailto:", "#", "data:")):
            continue

        absolute_url = urljoin(base_url + "/", raw_url)
        if absolute_url in seen:
            continue
        seen.add(absolute_url)

        if not absolute_url.startswith(("http://", "https://")):
            continue

        parsed = urlparse(absolute_url)
        if parsed.netloc == base_netloc:
            if _is_content_link(absolute_url, base_netloc):
                same_domain.append(absolute_url)
        elif len(other_domain) < _OTHER_DOMAIN_LIMIT:
            lower_url = absolute_url.lower()
            if not any(x in lower_url for x in ("cdn.", "static.", "assets.", "avatars.", "gravatar.", "fonts.", "googleapis.", "gstatic.")):
                other_domain.append(absolute_url)

    result = same_domain[:limit]
    result.extend(other_domain[: limit - len(result)])
    return result


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
