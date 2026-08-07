from __future__ import annotations

import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from typing import Callable
import re as _re
from urllib.parse import quote_plus, urljoin as _urljoin_imp, urlparse as _urlparse_imp

import requests

from .extractors import clean_text, extract_links, extract_query_snippets, extract_regex_matches
from .models import SearchMatch, SearchRequest, SiteResult
from . import cache

logger = logging.getLogger(__name__)

RETRY_MAX = 3
RETRY_DELAYS = [1, 3, 5]
MIN_MEANINGFUL_LENGTH = 1500
MIN_CONTENT_LINKS = 5

_LINK_BODY_RE = _re.compile(r'href=["\']([^"\']+)["\']', _re.IGNORECASE)

_log_setup_done = False


def setup_logging(verbose: bool = False, gui_queue: Queue | None = None) -> None:
    global _log_setup_done
    if _log_setup_done:
        return
    _log_setup_done = True

    root = logging.getLogger("python_deep_search")
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    stderr_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(message)s", datefmt="%H:%M:%S"
    ))
    root.addHandler(stderr_handler)

    if gui_queue is not None:
        from logging.handlers import QueueHandler
        qh = QueueHandler(gui_queue)
        qh.setLevel(logging.INFO)
        root.addHandler(qh)

    root.addHandler(cache.LogCacheHandler())


def _build_search_url(base_url: str, template: str, query: str) -> str:
    return template.format(base=base_url.rstrip("/"), query=quote_plus(query))


def _expand_query(raw: str) -> list[str]:
    alternatives = [a.strip() for a in raw.split("|")]
    results: list[str] = []
    for alt in alternatives:
        results.extend(_expand_alternative(alt))
    return results


def _expand_alternative(alt: str) -> list[str]:
    alt = alt.strip()
    if not alt:
        return []
    parts = _re.split(r"(\[[^\]]*\])", alt)
    results = [""]
    for part in parts:
        if part.startswith("[") and part.endswith("]"):
            chars = list(part[1:-1])
            if not chars:
                continue
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

    if use_playwright:
        logger.info("Пробуем Playwright для %s (контент скудный или JS-скелет)", url)
        pw_html = _fetch_html_playwright(url, timeout)
        if pw_html and _page_has_meaningful_content(pw_html, url):
            return pw_html

    return html


def _extract_from_page(
    body: str, page_url: str, req: SearchRequest
) -> tuple[list[str], list[SearchMatch]]:
    links = extract_links(body, page_url, limit=req.max_links)

    matches: list[SearchMatch] = []
    seen: set[str] = set()

    for txt in extract_regex_matches(body, req.regex_pattern, req.max_results):
        if txt not in seen:
            seen.add(txt)
            matches.append(SearchMatch(text=txt, score=100))

    for txt in extract_query_snippets(body, req.query, req.max_results):
        if txt not in seen:
            seen.add(txt)
            matches.append(SearchMatch(text=txt, score=60))

    matches.sort(key=lambda x: x.score, reverse=True)
    return links, matches[: req.max_results]


def _crawl_path_builder(
    site_name: str,
    base_url: str,
    path_builder: dict,
    query: str,
    req: SearchRequest,
    sess: requests.Session,
    headers: dict[str, str],
) -> tuple[list[str], list[SearchMatch], str]:
    pattern = path_builder["pattern"]
    start = path_builder["start"]
    end = path_builder["end"]
    step = path_builder["step"]

    all_links: list[str] = []
    all_matches: list[SearchMatch] = []
    first_url = ""
    visited_urls: set[str] = set()

    for n in range(start, end + 1, step):
        try:
            url = pattern.format(n=n, query=quote_plus(query))
        except KeyError:
            url = pattern.format(n=n)

        if not url.startswith("http"):
            url = base_url.rstrip("/") + "/" + url.lstrip("/")

        if not first_url:
            first_url = url

        if url in visited_urls:
            continue
        visited_urls.add(url)

        logger.info("%s: [%d/%d] проверка «%s» → %s", site_name, n, end, query, url)

        body = _fetch_page(url, sess, headers, req.timeout_sec, req.use_playwright)
        if body is None:
            logger.info("%s: пропуск %s (нет ответа или не 200)", site_name, url)
            continue

        logger.info("%s: загружено (%d символов)", site_name, len(body))

        links, matches = _extract_from_page(body, url, req)

        for link in links:
            if link not in visited_urls:
                all_links.append(link)

        existing = {m.text for m in all_matches}
        for m in matches:
            if m.text not in existing:
                existing.add(m.text)
                all_matches.append(m)

        time.sleep(0.5)

    all_matches.sort(key=lambda x: x.score, reverse=True)
    all_matches = all_matches[: req.max_results]
    all_links = all_links[: req.max_links]

    return all_links, all_matches, first_url


def search_site(
    site_name: str,
    site_config: dict,
    req: SearchRequest,
    session: requests.Session | None = None,
) -> SiteResult:
    started = time.perf_counter()
    base_url = site_config.get("base_url", "")
    search_url = ""
    sess = session or requests.Session()
    own_session = session is None

    try:
        queries = _expand_query(req.query)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Referer": base_url + "/",
        }

        path_builder = site_config.get("path_builder")

        if path_builder:
            links, matches, search_url = _crawl_path_builder(
                site_name, base_url, path_builder, queries[0], req, sess, headers
            )
            all_urls = list(links[: req.max_links])
            elapsed = time.perf_counter() - started

            found = bool(matches or all_urls)
            logger.info(
                "%s: завершено (%s, страниц пройдено: %d, совпадений: %d)",
                site_name,
                "найдено" if found else "пусто",
                sum(1 for _ in range(path_builder["start"], path_builder["end"] + 1, path_builder["step"])),
                len(matches),
            )
            return SiteResult(
                site_name=site_name,
                base_url=base_url,
                search_url=search_url,
                found=found,
                matches=matches,
                urls=all_urls,
                status_code=200,
                elapsed_sec=elapsed,
            )

        all_matches: list[SearchMatch] = []
        all_links: list[str] = []
        seen_links: set[str] = set()
        search_urls: list[str] = []

        for q in queries:
            q_url = _resolve_search_url(site_config, q)
            search_urls.append(q_url)
            if not search_url:
                search_url = q_url

            logger.info("%s: запрос «%s» → %s", site_name, q, q_url)

            body = _fetch_page(q_url, sess, headers, req.timeout_sec, req.use_playwright)
            if body is None:
                logger.warning("%s: не удалось загрузить «%s»", site_name, q)
                continue

            logger.info("%s: загружено «%s» (%d символов)", site_name, q, len(body))

            q_links, q_matches = _extract_from_page(body, q_url, req)

            existing_texts = {m.text for m in all_matches}
            for m in q_matches:
                if m.text not in existing_texts:
                    existing_texts.add(m.text)
                    all_matches.append(m)

            for link in q_links:
                if link not in seen_links:
                    seen_links.add(link)
                    all_links.append(link)

            time.sleep(0.5)

        elapsed = time.perf_counter() - started

        visited_follow: set[str] = set(search_urls)
        if req.follow_links and all_links:
            for target_url in all_links[: req.follow_limit]:
                if target_url in visited_follow:
                    continue
                visited_follow.add(target_url)
                time.sleep(0.5)
                logger.info("%s: переход по ссылке %s", site_name, target_url)
                target_body = _fetch_page(
                    target_url, sess, headers, req.timeout_sec, req.use_playwright
                )
                if target_body:
                    logger.info("%s: загружена ссылка %s (%d символов)", site_name, target_url, len(target_body))
                    _, target_matches = _extract_from_page(target_body, target_url, req)
                    existing = {m.text for m in all_matches}
                    for m in target_matches:
                        if m.text not in existing:
                            existing.add(m.text)
                            all_matches.append(m)

        all_matches.sort(key=lambda x: x.score, reverse=True)
        all_matches = all_matches[: req.max_results]
        all_urls = all_links[: req.max_links]

        found = bool(all_matches or all_urls)
        logger.info(
            "%s: завершено (%s, запросов: %d, совпадений: %d, ссылок: %d)",
            site_name,
            "найдено" if found else "пусто",
            len(queries),
            len(all_matches),
            len(all_urls),
        )

        return SiteResult(
            site_name=site_name,
            base_url=base_url,
            search_url=" | ".join(search_urls) if len(search_urls) > 1 else search_url,
            found=found,
            matches=all_matches,
            urls=all_urls,
            status_code=200,
            elapsed_sec=elapsed,
        )

    except requests.RequestException as e:
        elapsed = time.perf_counter() - started
        logger.warning("%s: ошибка запроса: %s", site_name, e)
        return SiteResult(
            site_name=site_name,
            base_url=base_url,
            search_url=search_url,
            found=False,
            elapsed_sec=elapsed,
            error=str(e),
        )
    finally:
        if own_session:
            sess.close()


def deep_search(
    sites: dict[str, dict],
    req: SearchRequest,
    max_workers: int = 6,
    progress_callback: Callable[[str], None] | None = None,
    use_cache: bool = True,
) -> dict[str, SiteResult]:
    if use_cache:
        cached = cache.get_cached_results(req, sites)
        if cached is not None:
            logger.info("Результаты найдены в кэше (запрос: «%s»)", req.query)
            results: dict[str, SiteResult] = {}
            for name, entry in cached.items():
                matches = [SearchMatch(text=m["text"], score=m["score"]) for m in entry.get("matches", [])]
                results[name] = SiteResult(
                    site_name=name,
                    base_url=sites.get(name, {}).get("base_url", ""),
                    search_url="(cached)",
                    found=entry.get("found", False),
                    matches=matches,
                    urls=entry.get("urls", []),
                    status_code=entry.get("status_code"),
                    elapsed_sec=entry.get("elapsed_sec", 0),
                    error=entry.get("error"),
                )
            if progress_callback:
                progress_callback("загружено из кэша")
            return results

    results = {}
    workers = max(1, min(max_workers, len(sites) or 1))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(search_site, site_name, site_cfg, req): site_name
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

            results[site_name] = result
            if progress_callback:
                state = "найдено" if result.found else "пусто"
                progress_callback(f"{site_name}: {state}")

    if use_cache and results:
        cache.set_cached_results(req, sites, results)

    return results


def filter_candidates(results: dict[str, SiteResult]) -> dict[str, SiteResult]:
    return {name: res for name, res in results.items() if res.found}
