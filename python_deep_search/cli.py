from __future__ import annotations

import argparse
import re
import sys
import webbrowser

from .config import load_sites_config
from .models import SearchRequest
from .output import save_results_json
from .search_engine import deep_search, filter_candidates, setup_logging
from . import cache


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Deep Search CLI")
    p.add_argument("query", help="Поисковый запрос")
    p.add_argument("--regex", default=r"\b\w+\b", help="Regex для извлечения совпадений")
    p.add_argument("--sites", default="python_deep_search/sites.json", help="Путь к JSON сайтов")
    p.add_argument("--max-results", type=int, default=10, help="Макс. результатов на сайт")
    p.add_argument("--workers", type=int, default=6, help="Число потоков")
    p.add_argument("--timeout", type=int, default=15, help="Timeout запроса в секундах")
    p.add_argument("--open", action="store_true", help="Открыть найденные ссылки в браузере")
    p.add_argument("--out", default="python_deep_search/results.json", help="Куда сохранить JSON")
    p.add_argument("--no-follow", action="store_true", help="Не переходить по ссылкам с результатов поиска")
    p.add_argument("--follow-limit", type=int, default=5, help="Сколько ссылок обходить (по умолчанию 5)")
    p.add_argument("--no-playwright", action="store_true", help="Отключить Playwright для JS-сайтов")
    p.add_argument("--verbose", "-v", action="store_true", help="Подробный вывод (DEBUG)")
    return p


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def print_results(results):
    for site, data in results.items():
        _safe_print("\n" + "=" * 70)
        _safe_print(f"{site.upper()} | status={data.status_code} | {data.elapsed_sec:.2f}s")
        if data.error:
            _safe_print(f"Ошибка: {data.error}")
            continue
        if not data.found:
            _safe_print("Ничего релевантного не найдено")
            continue

        _safe_print(f"Найдено совпадений: {len(data.matches)}")
        for i, m in enumerate(data.matches[:5], 1):
            _safe_print(f"  {i}. ({m.score}) {m.text}")

        if data.urls:
            _safe_print("Ссылки:")
            for i, u in enumerate(data.urls[:5], 1):
                _safe_print(f"  {i}. {u}")


def maybe_open_links(results):
    for site, data in results.items():
        if not data.found:
            continue
        for u in data.urls[:3]:
            webbrowser.open(u)
            _safe_print(f"Открыто [{site}]: {u}")


def run_cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        re.compile(args.regex)
    except re.error as e:
        print(f"Ошибка regex: {e}")
        return 2

    setup_logging(verbose=args.verbose)

    sites_path = args.sites
    if sites_path == "python_deep_search/sites.json":
        last = cache.get_setting("last_sites")
        if last:
            sites_path = last

    sites = load_sites_config(sites_path)
    cache.set_setting("last_sites", sites_path)

    req = SearchRequest(
        query=args.query,
        regex_pattern=args.regex,
        max_results=max(1, args.max_results),
        timeout_sec=max(3, args.timeout),
        follow_links=not args.no_follow,
        follow_limit=max(1, args.follow_limit),
        use_playwright=not args.no_playwright,
        verbose=args.verbose,
    )

    print(f"Старт поиска: '{req.query}' | regex={req.regex_pattern} | сайтов={len(sites)}")

    def progress(msg: str):
        print(f"[done] {msg}")

    all_results = deep_search(sites, req, max_workers=args.workers, progress_callback=progress)
    candidates = filter_candidates(all_results)

    print_results(all_results)

    print("\n" + "-" * 70)
    print(f"Кандидатов после фильтрации: {len(candidates)} из {len(all_results)}")

    saved = save_results_json(all_results, args.out)
    print(f"Результаты сохранены: {saved}")

    if args.open:
        maybe_open_links(candidates)

    return 0


if __name__ == "__main__":
    sys.exit(run_cli())
