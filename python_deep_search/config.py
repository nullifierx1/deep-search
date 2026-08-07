from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


KNOWN_SEARCH_TEMPLATES: dict[str, str] = {
    "wikipedia.org": "{base}/w/index.php?search={query}",
    "github.com": "{base}/search?q={query}",
    "stackoverflow.com": "{base}/search?q={query}",
    "habr.com": "{base}/ru/search/?q={query}",
    "reddit.com": "{base}/search/?q={query}",
    "youtube.com": "{base}/results?search_query={query}",
    "duckduckgo.com": "{base}/?q={query}",
}

DEFAULT_SITES_PATH = "python_deep_search/json-sites-examples/sites.json"


def normalize_base_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url:
        raise ValueError("Пустой URL сайта")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if "?" in url:
        url = url.split("?")[0]
    return url


def _guess_search_template(base_url: str) -> str:
    host = base_url.replace("https://", "").replace("http://", "")
    host = host.lower().split("/")[0]

    for known_host, template in KNOWN_SEARCH_TEMPLATES.items():
        if host.endswith(known_host):
            return template

    # Универсальный fallback: часто встречается /search?q=
    return "{base}/search?q={query}"


def _normalize_params(raw_params) -> dict[str, str] | None:
    if raw_params is None:
        return None
    if isinstance(raw_params, dict):
        return {str(k): str(v) for k, v in raw_params.items() if v is not None}
    if isinstance(raw_params, str):
        result: dict[str, str] = {}
        for pair in raw_params.replace(",", "&").split("&"):
            pair = pair.strip()
            if not pair:
                continue
            if "=" in pair:
                k, v = pair.split("=", 1)
                result[k.strip()] = v.strip()
            else:
                result[pair] = ""
        return result or None
    return None


def _normalize_path_builder(raw) -> dict | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return {
            "pattern": str(raw.get("pattern", "")),
            "start": int(raw.get("start", 1)),
            "end": int(raw.get("end", 1)),
            "step": int(raw.get("step", 1)),
        }
    if isinstance(raw, str):
        return {"pattern": raw, "start": 1, "end": 1, "step": 1}
    return None


def _string_list(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(item) for item in raw if item is not None]
    return []


def _normalize_path_rewrites(raw) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    rewrites: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        pattern = item.get("from")
        replacement = item.get("to")
        if pattern is None or replacement is None:
            continue
        rewrites.append({"from": str(pattern), "to": str(replacement)})
    return rewrites


def _normalize_link_rules(raw) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    return {
        "search_strict_query": bool(raw.get("search_strict_query", True)),
        "include_url_patterns": _string_list(raw.get("include_url_patterns")),
        "exclude_url_patterns": _string_list(raw.get("exclude_url_patterns")),
    }


def _normalize_dedupe(raw) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    return {
        "strip_fragment": bool(raw.get("strip_fragment", True)),
        "strip_www": bool(raw.get("strip_www", False)),
        "strip_trailing_slash": bool(raw.get("strip_trailing_slash", False)),
        "strip_suffixes": _string_list(raw.get("strip_suffixes")),
        "path_rewrites": _normalize_path_rewrites(raw.get("path_rewrites")),
        "ignore_query": bool(raw.get("ignore_query", False)),
        "lowercase_host": bool(raw.get("lowercase_host", True)),
        "lowercase_path": bool(raw.get("lowercase_path", False)),
    }


def _normalize_follow(raw) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    return {
        "enabled": bool(raw.get("enabled", True)),
        "collect_child_links": bool(raw.get("collect_child_links", True)),
    }


def load_sites_config(path: str | Path) -> Dict[str, dict]:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Файл конфигурации не найден: {cfg_path}")

    with cfg_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict):
        raise ValueError("JSON должен быть объектом: { 'site_name': 'https://site.com' }")

    parsed: Dict[str, dict] = {}
    for site_name, value in raw.items():
        if isinstance(value, str):
            base_url = normalize_base_url(value)
            parsed[site_name] = {
                "base_url": base_url,
                "search_template": _guess_search_template(base_url),
                "use_full_path": False,
                "params": None,
                "path_builder": None,
                "link_rules": _normalize_link_rules(None),
                "dedupe": _normalize_dedupe(None),
                "follow": _normalize_follow(None),
            }
        elif isinstance(value, dict):
            base_url = normalize_base_url(value.get("base_url", ""))
            search_template = value.get("search_template") or _guess_search_template(base_url)
            use_full_path = bool(value.get("use_full_path", False))
            params = _normalize_params(value.get("params"))
            path_builder = _normalize_path_builder(value.get("path_builder"))
            link_rules = _normalize_link_rules(value.get("link_rules"))
            dedupe = _normalize_dedupe(value.get("dedupe"))
            follow = _normalize_follow(value.get("follow"))
            parsed[site_name] = {
                "base_url": base_url,
                "search_template": search_template,
                "use_full_path": use_full_path,
                "params": params,
                "path_builder": path_builder,
                "link_rules": link_rules,
                "dedupe": dedupe,
                "follow": follow,
            }
        else:
            raise ValueError(
                f"Неверный формат для '{site_name}'. Ожидается строка URL или объект."
            )

    return parsed
