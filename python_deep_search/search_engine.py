from __future__ import annotations

import logging
import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from queue import Queue
from threading import Event
from typing import Callable, Iterator
import re as _re
from urllib.parse import quote_plus, urljoin as _urljoin_imp, urlparse as _urlparse_imp

import requests

from .extractors import clean_text, extract_links, extract_query_snippets, extract_regex_matches
from .models import FollowResult, SearchMatch, SearchRequest, SiteResult
from .network import SOURCE_STOP, SearchSession, is_challenge
from . import cache

logger = logging.getLogger(__name__)

RETRY_MAX = 3
RETRY_DELAYS = [1, 3, 5]
MIN_MEANINGFUL_LENGTH = 1500
MIN_CONTENT_LINKS = 5
MAX_QUERY_VARIANTS = 32

_LINK_BODY_RE = _re.compile(r'href=["\']([^"\']+)["\']', _re.IGNORECASE)

_log_setup_done = False
_gui_log_queues: set[int] = set()


def setup_logging(verbose: bool = False, gui_queue: Queue | None = None) -> None:
    global _log_setup_done

    root = logging.getLogger("python_deep_search")
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    stderr_level = logging.DEBUG if verbose else logging.INFO
    for handler in root.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setLevel(stderr_level)
        elif handler.__class__.__name__ == "QueueHandler":
            handler.setLevel(stderr_level)

    if not _log_setup_done:
        _log_setup_done = True

        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(stderr_level)
        stderr_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)-5s] %(message)s", datefmt="%H:%M:%S"
        ))
        root.addHandler(stderr_handler)

        root.addHandler(cache.LogCacheHandler())

    if gui_queue is not None:
        from logging.handlers import QueueHandler
        queue_id = id(gui_queue)
        if queue_id not in _gui_log_queues:
            _gui_log_queues.add(queue_id)
            qh = QueueHandler(gui_queue)
            qh.setLevel(stderr_level)
            root.addHandler(qh)


def _build_search_url(base_url: str, template: str, query: str) -> str:
    return template.format(base=base_url.rstrip("/"), query=quote_plus(query))


def _expand_query(raw: str) -> list[str]:
    alternatives = [a.strip() for a in raw.split("|")]
    results: dict[str, None] = {}
    for alt in alternatives:
        results.update(dict.fromkeys(_expand_alternative(alt)))
        if len(results) > MAX_QUERY_VARIANTS:
            raise ValueError(f"Search query expands to more than {MAX_QUERY_VARIANTS} variants")
    return list(results)


def _expand_alternative(alt: str) -> list[str]:
    alt = alt.strip()
    if not alt:
        return []
    parts = _re.split(r"(\[[^\]]*\])", alt)
    results = [""]
    for part in parts:
        if part.startswith("[") and part.endswith("]"):
            chars = list(dict.fromkeys(part[1:-1]))
            if not chars:
                continue
            if len(results) * len(chars) > MAX_QUERY_VARIANTS:
                raise ValueError(f"Search query expands to more than {MAX_QUERY_VARIANTS} variants")
            new_results: list[str] = []
            for r in results:
                for c in chars:
                    new_results.append(r + c)
            results = new_results
        else:
            results = [r + part for r in results]
    return results


def _resolve_search_url(site_config: dict, query: str) -> str:
    template = site_config.get("search_template", "")
    base_url = site_config.get("base_url", "")
    use_full_path = site_config.get("use_full_path", False)

    if not template:
        raise ValueError("Не указан search_template")

    if use_full_path:
        search_url = template.format(query=quote_plus(query))
    else:
        search_url = _build_search_url(base_url, template, query)

    return _append_params(search_url, site_config.get("params"))


def _append_params(url: str, params: dict[str, str] | None) -> str:
    if not params:
        return url
    extra = "&".join(f"{quote_plus(k)}={quote_plus(v)}" for k, v in params.items())
    connector = "&" if "?" in url else "?"
    return url + connector + extra


def _fetch_html_requests(
    url: str,
    session: requests.Session,
    headers: dict[str, str],
    timeout: int,
) -> str | None:
    if isinstance(session, SearchSession):
        return session.fetch(url, headers, timeout)
    last_error: Exception | None = None
    for attempt in range(RETRY_MAX):
        try:
            response = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if response.status_code == 200:
                return response.text
            if 400 <= response.status_code < 500 and response.status_code != 429:
                logger.info("HTTP %d для %s (не ретраим)", response.status_code, url)
                return None
        except (requests.ConnectionError, requests.Timeout) as e:
            last_error = e
        except requests.RequestException as e:
            last_error = e
            break

        if attempt < RETRY_MAX - 1:
            delay = RETRY_DELAYS[attempt]
            logger.info("Ретрай #%d через %ds: %s", attempt + 1, delay, url)
            time.sleep(delay)

    if last_error:
        logger.info("Не удалось загрузить %s: %s", url, last_error)
    return None


def _fetch_html_playwright(url: str, timeout: int) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.info("Playwright не установлен, пропускаем JS-рендеринг")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
                ),
                locale="ru-RU",
            )
            page = context.new_page()
            page.goto(url, timeout=min(timeout * 1000, 30000), wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=min(timeout * 1000, 15000))
            except Exception:
                pass
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        logger.info("Playwright ошибка для %s: %s", url, e)
        return None


def _count_deep_links(html: str, base_url: str) -> int:
    base_netloc = _urlparse_imp(base_url).netloc
    count = 0
    for raw in _LINK_BODY_RE.findall(html):
        if raw.startswith(("javascript:", "mailto:", "#", "data:")):
            continue
        absolute = _urljoin_imp(base_url + "/", raw)
        try:
            parsed = _urlparse_imp(absolute)
            if parsed.netloc == base_netloc:
                segs = [s for s in parsed.path.split("/") if s]
                if len(segs) >= 2:
                    count += 1
        except Exception:
            pass
    return count


def _page_has_meaningful_content(html: str, base_url: str = "") -> bool:
    text_len = len(clean_text(html))
    if text_len < MIN_MEANINGFUL_LENGTH:
        return False
    if base_url and _count_deep_links(html, base_url) < MIN_CONTENT_LINKS:
        return False
    return True


def _page_mentions_query(html: str, query: str) -> bool:
    terms = _re.findall(r"[\w-]{3,}", query.lower())
    if not terms:
        return True
    text = clean_text(html).lower()
    return any(term in text for term in terms)


def _render_page(url: str, timeout: int, session: requests.Session) -> str | None:
    managed = isinstance(session, SearchSession)
    if managed and not session.begin_render():
        return None
    html = _fetch_html_playwright(url, timeout)
    if html and is_challenge(html):
        if managed:
            session.failure = "bot_challenge"
        return None
    return html


def _fetch_page(
    url: str,
    session: requests.Session,
    headers: dict[str, str],
    timeout: int,
    use_playwright: bool = True,
) -> str | None:
    html = _fetch_html_requests(url, session, headers, timeout)

    if html and _page_has_meaningful_content(html, url):
        return html

    if use_playwright and (not isinstance(session, SearchSession) or session.can_render):
        logger.info("Пробуем Playwright для %s (контент скудный или JS-скелет)", url)
        pw_html = _render_page(url, timeout, session)
        if isinstance(session, SearchSession) and session.failure == "bot_challenge":
            return None
        if pw_html and _page_has_meaningful_content(pw_html, url):
            return pw_html

    return html


def _fetch_search_page(
    url: str,
    query: str,
    session: requests.Session,
    headers: dict[str, str],
    timeout: int,
    use_playwright: bool = True,
) -> str | None:
    html = _fetch_page(url, session, headers, timeout, use_playwright)
    if (
        not html or not use_playwright or _page_mentions_query(html, query)
        or (isinstance(session, SearchSession) and not session.can_render)
    ):
        return html

    logger.info("%s: response does not mention query %r; retrying with Playwright", url, query)
    rendered = _render_page(url, timeout, session)
    if isinstance(session, SearchSession) and session.failure == "bot_challenge":
        return None
    if rendered:
        return rendered
    return html


def _extract_from_page(
    body: str,
    page_url: str,
    req: SearchRequest,
    *,
    include_query_snippets: bool = True,
    prefer_query_links: bool = False,
    link_rules: dict | None = None,
    dedupe: dict | None = None,
) -> tuple[list[str], list[SearchMatch]]:
    links = extract_links(
        body,
        page_url,
        limit=req.max_links,
        query=req.query if prefer_query_links else None,
        prefer_query_matches=prefer_query_links,
        link_rules=link_rules,
        dedupe=dedupe,
    )

    matches: list[SearchMatch] = []
    seen: set[str] = set()

    for txt in extract_regex_matches(body, req.regex_pattern, req.max_results):
        if txt not in seen:
            seen.add(txt)
            matches.append(SearchMatch(text=txt, score=100))

    if include_query_snippets:
        for txt in extract_query_snippets(body, req.query, req.max_results):
            if txt not in seen:
                seen.add(txt)
                matches.append(SearchMatch(text=txt, score=60))

    matches.sort(key=lambda x: x.score, reverse=True)
    return links, matches[: req.max_results]


def _filter_child_links(links: list[str], parent_links: list[str], max_links: int) -> list[str]:
    parent_set = set(parent_links)
    filtered: list[str] = []
    seen: set[str] = set()
    for link in links:
        if link in parent_set or link in seen:
            continue
        seen.add(link)
        filtered.append(link)
        if len(filtered) >= max_links:
            break
    return filtered


def _seed_urls(site_config: dict, query: str) -> Iterator[str]:
    builder = site_config.get("path_builder")
    if not builder:
        yield _resolve_search_url(site_config, query)
        return

    paths = builder.get("paths")
    if paths is None:
        pages = range(builder["start"], builder["end"] + 1, builder["step"])
        paths = (builder["pattern"].format(n=n, query=quote_plus(query)) for n in pages)
    base = site_config["base_url"].rstrip("/")
    for path in paths:
        yield path if path.startswith(("http://", "https://")) else f"{base}/{path.lstrip('/')}"


def _origin(url: str) -> tuple[str, str]:
    parsed = _urlparse_imp(url)
    return parsed.scheme, parsed.netloc.lower()


def _follow_pages(
    seeds: list[str],
    checked: set[str],
    site_config: dict,
    req: SearchRequest,
    session: requests.Session,
    headers: dict[str, str],
    cancel: Event,
) -> tuple[list[FollowResult], str | None]:
    follow = site_config.get("follow") or {}
    results: list[FollowResult] = []
    if not req.follow_links or not follow.get("enabled", True):
        return results, None

    queue = deque((url, 1) for url in seeds if url not in checked)
    seen = checked | set(seeds)
    allowed_origin = _origin(site_config["base_url"])
    empty = 0
    seen_matches: set[str] = set()
    while queue:
        if cancel.is_set():
            return results, "cancelled"
        if len(results) >= req.follow_limit:
            return results, "page_limit"
        url, depth = queue.popleft()
        if req.follow_depth > 1 and _origin(url) != allowed_origin:
            continue
        if not isinstance(session, SearchSession) and cancel.wait(0.5):
            return results, "cancelled"

        body = _fetch_page(url, session, headers, req.timeout_sec, req.use_playwright)
        result = FollowResult(source_url=url, depth=depth)
        if body is None:
            result.error = (session.failure if isinstance(session, SearchSession) else None) or "page_unavailable"
        else:
            links, result.matches = _extract_from_page(
                body, url, req, link_rules=site_config.get("link_rules"), dedupe=site_config.get("dedupe"),
            )
            if follow.get("collect_child_links", True):
                result.urls = _filter_child_links(links, seeds, req.max_links)
                if depth < req.follow_depth:
                    for link in result.urls:
                        if link not in seen and _origin(link) == allowed_origin:
                            seen.add(link)
                            queue.append((link, depth + 1))
            texts = {match.text for match in result.matches}
            empty = 0 if texts - seen_matches else empty + 1
            seen_matches.update(texts)
        results.append(result)
        if result.error in SOURCE_STOP:
            return results, result.error
        if req.stop_after_empty and empty >= req.stop_after_empty:
            return results, "empty_limit"

    return results, "cancelled" if cancel.is_set() else None


def search_site(
    site_name: str,
    site_config: dict,
    req: SearchRequest,
    session: requests.Session | None = None,
    *,
    cancel: Event | None = None,
) -> SiteResult:
    started = time.perf_counter()
    cancel = cancel if cancel is not None else Event()
    base_url = site_config["base_url"]
    result = SiteResult(site_name, base_url, "", found=False)
    sess = session if session is not None else SearchSession(cancel, site_config.get("network"), req.max_requests_per_site)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru,en;q=0.9",
        "Referer": base_url + "/",
    }
    builder = site_config.get("path_builder")
    checked: dict[str, str | None] = {}
    all_matches: dict[str, SearchMatch] = {}
    all_links: dict[str, None] = {}
    try:
        for query in _expand_query(req.query):
            query_req = replace(req, query=query)
            empty = 0
            query_pages: set[str] = set()
            for url in _seed_urls(site_config, query):
                if cancel.is_set():
                    result.search_stop_reason = "cancelled"
                    break
                if url in query_pages:
                    continue
                query_pages.add(url)
                first_visit = url not in checked
                if first_visit:
                    logger.info("%s: searching %r at %s", site_name, query, url)
                    checked[url] = (
                        _fetch_page(url, sess, headers, req.timeout_sec, req.use_playwright)
                        if builder
                        else _fetch_search_page(url, query, sess, headers, req.timeout_sec, req.use_playwright)
                    )
                body = checked[url]
                if body is None:
                    if first_visit and isinstance(sess, SearchSession):
                        if result.status_code is None:
                            result.status_code = sess.status
                        if sess.failure and sess.failure != "cancelled":
                            result.network_errors[url] = sess.failure
                        if sess.failure in SOURCE_STOP:
                            result.search_stop_reason = sess.failure
                            break
                    continue
                result.status_code = 200
                links, matches = _extract_from_page(
                    body, url, query_req,
                    include_query_snippets=bool(builder and builder.get("paths")),
                    prefer_query_links=builder.get("prefer_query_links", False) if builder else True,
                    link_rules=site_config.get("link_rules"),
                    dedupe=site_config.get("dedupe"),
                )
                links = [link for link in links if link != url]
                discovered = any(link not in all_links for link in links) or any(
                    match.text not in all_matches for match in matches
                )
                empty = 0 if discovered else empty + 1
                for link in links:
                    all_links[link] = None
                for match in matches:
                    all_matches.setdefault(match.text, match)
                if req.stop_after_empty and empty >= req.stop_after_empty:
                    result.search_stop_reason = "empty_limit"
                    break
                if first_visit and not isinstance(sess, SearchSession):
                    cancel.wait(0.5)

            if cancel.is_set() or result.search_stop_reason in SOURCE_STOP:
                break

        if cancel.is_set():
            result.search_stop_reason = "cancelled"
        result.search_url = " | ".join(checked)
        result.urls = [url for url in all_links if url not in checked][:req.max_links]
        if result.search_stop_reason not in SOURCE_STOP:
            result.followed, result.follow_stop_reason = _follow_pages(
                result.urls, set(checked), site_config, req, sess, headers, cancel,
            )
        for page in result.followed:
            for match in page.matches:
                all_matches.setdefault(match.text, match)
        result.matches = sorted(all_matches.values(), key=lambda match: -match.score)[:req.max_results]
        result.found = bool(result.matches or result.urls)
        if checked and not any(body is not None for body in checked.values()) and not cancel.is_set():
            result.error = "No search page could be loaded"
    finally:
        if isinstance(sess, SearchSession):
            result.http_requests = sess.http_requests
            result.browser_renders = sess.browser_renders
        if session is None:
            sess.close()
    result.elapsed_sec = time.perf_counter() - started
    return result


def deep_search(
    sites: dict[str, dict],
    req: SearchRequest,
    max_workers: int = 6,
    progress_callback: Callable[[str], None] | None = None,
    use_cache: bool = True,
    cancel: Event | None = None,
    result_callback: Callable[[SiteResult], None] | None = None,
) -> dict[str, SiteResult]:
    if cancel is not None and cancel.is_set():
        return {}
    if not _expand_query(req.query):
        raise ValueError("Enter a search query")
    if use_cache:
        cached = cache.get_cached_results(req, sites)
        if cached is not None:
            logger.info("Результаты найдены в кэше (запрос: «%s»)", req.query)
            results: dict[str, SiteResult] = {}
            for name, entry in cached.items():
                matches = [SearchMatch(text=m["text"], score=m["score"]) for m in entry.get("matches", [])]
                followed = [
                    FollowResult(
                        source_url=f.get("source_url", ""),
                        matches=[
                            SearchMatch(text=m["text"], score=m["score"])
                            for m in f.get("matches", [])
                        ],
                        urls=f.get("urls", []),
                        error=f.get("error"),
                        depth=f.get("depth", 1),
                    )
                    for f in entry.get("followed", [])
                ]
                results[name] = SiteResult(
                    site_name=name,
                    base_url=sites.get(name, {}).get("base_url", ""),
                    search_url=entry.get("search_url", ""),
                    found=entry.get("found", False),
                    matches=matches,
                    urls=entry.get("urls", []),
                    followed=followed,
                    status_code=entry.get("status_code"),
                    elapsed_sec=entry.get("elapsed_sec", 0),
                    error=entry.get("error"),
                    search_stop_reason=entry.get("search_stop_reason"),
                    follow_stop_reason=entry.get("follow_stop_reason"),
                    network_errors=entry.get("network_errors", {}),
                )
            if result_callback:
                for result in results.values():
                    result_callback(result)
            if progress_callback:
                progress_callback("загружено из кэша")
            return results

    results = {}
    workers = max(1, min(max_workers, len(sites) or 1))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(search_site, site_name, site_cfg, req, cancel=cancel): site_name
            for site_name, site_cfg in sites.items()
        }

        for future in as_completed(futures):
            site_name = futures[future]
            try:
                result = future.result()
            except Exception as e:
                logger.error("%s: неожиданная ошибка: %s", site_name, e)
                result = SiteResult(
                    site_name=site_name,
                    base_url=sites[site_name]["base_url"],
                    search_url="",
                    found=False,
                    error=f"Неожиданная ошибка: {e}",
                )

            if result.search_stop_reason == "cancelled" and not result.search_url:
                continue
            results[site_name] = result
            if result_callback:
                result_callback(result)
            if progress_callback:
                state = "найдено" if result.found else "пусто"
                progress_callback(f"{site_name}: {state}")

    if (
        use_cache and results and (cancel is None or not cancel.is_set())
        and not any(r.error or r.network_errors or any(p.error for p in r.followed) for r in results.values())
    ):
        cache.set_cached_results(req, sites, results)

    return results


def filter_candidates(results: dict[str, SiteResult]) -> dict[str, SiteResult]:
    return {name: res for name, res in results.items() if res.urls}
