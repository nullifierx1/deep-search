from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Any

from .models import SearchRequest, SiteResult

CACHE_DIR = Path("python_deep_search/.cache")
RESULTS_FILE = CACHE_DIR / "results_cache.json"
SETTINGS_FILE = CACHE_DIR / "settings.json"
LOG_FILE = CACHE_DIR / "log_cache.json"

RESULTS_TTL = 30 * 24 * 3600
LOG_TTL = 24 * 3600
LOG_MAX_LINES = 500
CACHE_SCHEMA_VERSION = 10
_lock = RLock()


def _read_json(path: Path) -> dict:
    with _lock:
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (ValueError, OSError):
            return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict) -> None:
    temp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
            temp = Path(f.name)
            json.dump(data, f, ensure_ascii=False, indent=2)
        temp.replace(path)
    except OSError:
        if path != LOG_FILE:
            logging.getLogger(__name__).warning("Could not write cache file %s", path)
    finally:
        if temp is not None:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass


def _sites_hash(sites: dict) -> str:
    raw = json.dumps(sites, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _query_key(req: SearchRequest, sites: dict) -> str:
    h = _sites_hash(sites)
    request_data = {
        "schema": CACHE_SCHEMA_VERSION,
        "query": req.query,
        "regex_pattern": req.regex_pattern,
        "max_results": req.max_results,
        "max_links": req.max_links,
        "follow_links": req.follow_links,
        "follow_limit": req.follow_limit,
        "use_playwright": req.use_playwright,
        "follow_depth": req.follow_depth,
        "stop_after_empty": req.stop_after_empty,
        "timeout_sec": req.timeout_sec,
    }
    raw = json.dumps(request_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(f"{raw}:{h}".encode()).hexdigest()[:16]


def _prune_expired(data: dict, ttl: int) -> dict:
    now = time.time()
    return {k: v for k, v in data.items() if isinstance(v, dict) and now - v.get("ts", 0) < ttl}


def get_cached_results(req: SearchRequest, sites: dict) -> dict[str, Any] | None:
    cache = _read_json(RESULTS_FILE)
    key = _query_key(req, sites)
    entry = cache.get(key)
    if not isinstance(entry, dict) or time.time() - entry.get("ts", 0) > RESULTS_TTL:
        return None
    return entry.get("results")


def set_cached_results(req: SearchRequest, sites: dict, results: dict[str, SiteResult]) -> None:
    key = _query_key(req, sites)
    serializable: dict[str, Any] = {}
    for name, r in results.items():
        serializable[name] = {
            "search_url": r.search_url,
            "found": r.found,
            "urls": r.urls,
            "matches": [{"text": m.text, "score": m.score} for m in r.matches],
            "followed": [
                {
                    "source_url": f.source_url,
                    "urls": f.urls,
                    "matches": [{"text": m.text, "score": m.score} for m in f.matches],
                    "error": f.error,
                    "depth": f.depth,
                }
                for f in r.followed
            ],
            "status_code": r.status_code,
            "elapsed_sec": r.elapsed_sec,
            "error": r.error,
            "search_stop_reason": r.search_stop_reason,
            "follow_stop_reason": r.follow_stop_reason,
            "network_errors": r.network_errors,
        }
    with _lock:
        cache = _prune_expired(_read_json(RESULTS_FILE), RESULTS_TTL)
        cache[key] = {"ts": time.time(), "query": req.query, "results": serializable}
        _write_json(RESULTS_FILE, cache)


def get_setting(key: str, default: str = "") -> str:
    settings = _read_json(SETTINGS_FILE)
    return settings.get(key, default)


def set_setting(key: str, value: str) -> None:
    with _lock:
        settings = _read_json(SETTINGS_FILE)
        settings[key] = value
        _write_json(SETTINGS_FILE, settings)


def get_cached_logs() -> list[dict[str, Any]]:
    data = _read_json(LOG_FILE)
    entries = data.get("entries", [])
    now = time.time()
    return [e for e in entries if now - e.get("ts", 0) < LOG_TTL]


def append_log_entry(level: str, message: str) -> None:
    with _lock:
        data = _read_json(LOG_FILE)
        entries = data.get("entries", [])
        entries.append({"ts": time.time(), "level": level, "msg": message})
        _write_json(LOG_FILE, {"entries": entries[-LOG_MAX_LINES:]})


class LogCacheHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            append_log_entry(record.levelname[:4], record.getMessage())
        except Exception:
            pass
