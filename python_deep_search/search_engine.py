from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable
import re as _re
from urllib.parse import quote_plus, urljoin as _urljoin_imp, urlparse as _urlparse_imp

import requests

from .extractors import clean_text, extract_links, extract_query_snippets, extract_regex_matches
from .models import SearchMatch, SearchRequest, SiteResult

logger = logging.getLogger(__name__)

RETRY_MAX = 3
RETRY_DELAYS = [1, 3, 5]
MIN_MEANINGFUL_LENGTH = 1500
MIN_CONTENT_LINKS = 5

_LINK_BODY_RE = _re.compile(r'href=["\']([^"\']+)["\']', _re.IGNORECASE)


def _build_search_url(base_url: str, template: str, query: str) -> str:
    return template.format(base=base_url.rstrip("/"), query=quote_plus(query))


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
                logger.debug("HTTP %d для %s — не ретраим", response.status_code, url)
                return None
        except (requests.ConnectionError, requests.Timeout) as e:
            last_error = e
        except requests.RequestException as e:
            last_error = e
            break

        if attempt < RETRY_MAX - 1:
            delay = RETRY_DELAYS[attempt]
            logger.debug("Ретрай #%d через %ds: %s", attempt + 1, delay, url)
            time.sleep(delay)

    if last_error:
        logger.debug("Не удалось загрузить %s: %s", url, last_error)
    return None


def _fetch_html_playwright(url: str, timeout: int) -> str | None:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("Playwright не установлен, пропускаем JS-рендеринг")
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
        logger.debug("Playwright ошибка для %s: %s", url, e)
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
        logger.debug("Пробуем Playwright для %s (контент скудный или JS-скелет)", url)
        pw_html = _fetch_html_playwright(url, timeout)
        if pw_html and _page_has_meaningful_content(pw_html, url):
            return pw_html

    return html


def _extract_from_page(
    body: str, base_url: str, req: SearchRequest
) -> tuple[list[str], list[SearchMatch]]:
    links = extract_links(body, base_url, limit=25)

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
        template = site_config.get("search_template", "")
        if not template:
            raise ValueError(f"Не указан search_template для {site_name}")
        use_full_path = site_config.get("use_full_path", False)
        if use_full_path:
            search_url = template.format(query=quote_plus(req.query))
        else:
            search_url = _build_search_url(base_url, template, req.query)
        search_url = _append_params(search_url, site_config.get("params"))

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

        body = _fetch_page(search_url, sess, headers, req.timeout_sec, req.use_playwright)
        elapsed = time.perf_counter() - started

        if body is None:
            return SiteResult(
                site_name=site_name,
                base_url=base_url,
                search_url=search_url,
                found=False,
                elapsed_sec=elapsed,
                error="Не удалось загрузить страницу",
            )

        links, matches = _extract_from_page(body, base_url, req)
        all_urls = list(links[:10])

        if req.follow_links and links:
            visited: set[str] = {search_url}
            for target_url in links[: req.follow_limit]:
                if target_url in visited:
                    continue
                visited.add(target_url)
                time.sleep(0.5)
                target_body = _fetch_page(
                    target_url, sess, headers, req.timeout_sec, req.use_playwright
                )
                if target_body:
                    _, target_matches = _extract_from_page(target_body, base_url, req)
                    existing = {m.text for m in matches}
                    for m in target_matches:
                        if m.text not in existing:
                            existing.add(m.text)
                            matches.append(m)

            matches.sort(key=lambda x: x.score, reverse=True)
            matches = matches[: req.max_results]

        found = len(matches) > 0

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

    except requests.RequestException as e:
        elapsed = time.perf_counter() - started
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
) -> dict[str, SiteResult]:
    results: dict[str, SiteResult] = {}
    workers = max(1, min(max_workers, len(sites) or 1))

    with requests.Session() as session:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(search_site, site_name, site_cfg, req, session): site_name
                for site_name, site_cfg in sites.items()
            }

            for future in as_completed(futures):
                site_name = futures[future]
                try:
                    result = future.result()
                except Exception as e:
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

    return results


def filter_candidates(results: dict[str, SiteResult]) -> dict[str, SiteResult]:
    return {name: res for name, res in results.items() if res.found}
