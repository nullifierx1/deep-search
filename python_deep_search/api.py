from __future__ import annotations

import argparse
import json
import re
import threading
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .config import load_sites_config, normalize_page_paths
from .models import SearchRequest, SiteResult
from .output import to_serializable
from .search_engine import _expand_query, deep_search

_EXAMPLES = Path(__file__).with_name("json-sites-examples")
_CATALOG = [_EXAMPLES / name for name in ("sites.json", "cppreference.json", "lk-sites.json")]
_JOB_ROUTE = re.compile(r"/api/searches/([a-f0-9]{32})(/cancel)?")
_LIMITS = {
    "max_results": (1, 100), "max_links": (1, 500), "timeout_sec": (3, 60),
    "follow_limit": (1, 100), "follow_depth": (1, 5), "stop_after_empty": (0, 100),
}


def _request(raw: object, catalog: dict) -> tuple[dict, SearchRequest, bool]:
    if not isinstance(raw, dict):
        raise ValueError("Expected a JSON object")
    names = raw.get("sites")
    if not isinstance(names, list) or not names or any(not isinstance(n, str) or n not in catalog for n in names):
        raise ValueError("Select at least one catalog site")
    sites = {name: dict(catalog[name]) for name in names}
    pages = raw.get("paths", {})
    if not isinstance(pages, dict) or any(name not in sites for name in pages):
        raise ValueError("Paths can only be set for selected sites")
    for name, paths in pages.items():
        if not isinstance(paths, list) or len(paths) > 100:
            raise ValueError("Each site accepts up to 100 paths")
        builder = sites[name].get("path_builder") or {}
        sites[name]["path_builder"] = {
            "paths": normalize_page_paths(paths), "prefer_query_links": builder.get("prefer_query_links", True),
        }

    query = raw.get("query")
    pattern = raw.get("regex_pattern", "")
    if not isinstance(query, str) or not query.strip() or len(query) > 200 or not _expand_query(query):
        raise ValueError("Enter a query of 1 to 200 characters")
    if not isinstance(pattern, str) or len(pattern) > 500:
        raise ValueError("Invalid regular expression")
    try:
        re.compile(pattern)
    except re.error as error:
        raise ValueError(f"Invalid regular expression: {error}") from error
    options = raw.get("options", {})
    allowed_flags = {"follow_links", "use_playwright", "use_cache"}
    if not isinstance(options, dict) or options.keys() - (_LIMITS.keys() | allowed_flags):
        raise ValueError("Unknown search options")
    for name, value in options.items():
        if name in _LIMITS:
            low, high = _LIMITS[name]
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be between {low} and {high}")
        elif type(value) is not bool:
            raise ValueError(f"{name} must be a boolean")
    options = dict(options)
    use_cache = options.pop("use_cache", True)
    options.setdefault("stop_after_empty", 5)
    return sites, SearchRequest(query.strip(), pattern, **options), use_cache


@dataclass
class SearchJob:
    total: int
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "running"
    cancel: threading.Event = field(default_factory=threading.Event)
    results: dict[str, SiteResult] = field(default_factory=dict)
    error: str | None = None


class SearchJobs:
    def __init__(self, catalog: dict):
        self.catalog = catalog
        self._jobs: dict[str, SearchJob] = {}
        self._lock = threading.Lock()

    def start(self, raw: object) -> dict | None:
        sites, request, use_cache = _request(raw, self.catalog)
        with self._lock:
            if any(job.status in {"running", "cancelling"} for job in self._jobs.values()):
                return None
            if len(self._jobs) >= 32:
                del self._jobs[next(iter(self._jobs))]
            job = SearchJob(total=len(sites))
            self._jobs[job.id] = job
            threading.Thread(target=self._run, args=(job, sites, request, use_cache), daemon=True).start()
            return self._snapshot(job)

    def _run(self, job: SearchJob, sites: dict, request: SearchRequest, use_cache: bool) -> None:
        def publish(result: SiteResult) -> None:
            with self._lock:
                job.results[result.site_name] = result

        try:
            results = deep_search(sites, request, cancel=job.cancel, result_callback=publish, use_cache=use_cache)
            with self._lock:
                job.results = results
                job.status = "cancelled" if job.cancel.is_set() else "completed"
        except Exception as error:
            with self._lock:
                job.error = str(error)
                job.status = "failed"

    def get(self, job_id: str, cancel: bool = False) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if cancel and job.status == "running":
                job.cancel.set()
                job.status = "cancelling"
            return self._snapshot(job)

    @staticmethod
    def _snapshot(job: SearchJob) -> dict:
        return {
            "id": job.id, "status": job.status, "total_sites": job.total,
            "finished_sites": len(job.results), "results": to_serializable(job.results), "error": job.error,
        }


def make_server(port: int, catalog: dict, frontend_origin: str | None = None) -> ThreadingHTTPServer:
    jobs = SearchJobs(catalog)

    class Handler(BaseHTTPRequestHandler):
        def _respond(self, status: int, payload: dict | None = None) -> None:
            body = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            if body:
                self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            origin = self.headers.get("Origin")
            if frontend_origin and origin == frontend_origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Vary", "Origin")
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _dispatch(self) -> None:
            port = self.server.server_port
            hosts = {f"localhost:{port}", f"127.0.0.1:{port}"}
            origin = self.headers.get("Origin")
            if self.headers.get("Host") not in hosts or (
                origin is not None and origin not in {*("http://" + host for host in hosts), frontend_origin}
            ):
                self._respond(403, {"error": "Unexpected host or origin"})
                return
            if self.command == "OPTIONS":
                self._respond(204)
                return
            path = urlsplit(self.path).path
            if self.command == "GET" and path == "/api/sites":
                self._respond(200, {"sites": [
                    {"id": name, "base_url": cfg["base_url"],
                     "paths": (cfg.get("path_builder") or {}).get("paths", [])}
                    for name, cfg in catalog.items()
                ]})
                return
            if self.command == "POST" and path == "/api/searches":
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 65536 or self.headers.get_content_type() != "application/json":
                        raise ValueError("Expected a JSON body up to 64 KiB")
                    snapshot = jobs.start(json.loads(self.rfile.read(length)))
                except ValueError as error:
                    self._respond(400, {"error": str(error)})
                    return
                self._respond(202, snapshot) if snapshot else self._respond(409, {"error": "A search is already running"})
                return
            match = _JOB_ROUTE.fullmatch(path)
            if match and (self.command, bool(match[2])) in {("GET", False), ("POST", True)}:
                snapshot = jobs.get(match[1], cancel=bool(match[2]))
                if snapshot is not None:
                    self._respond(200, snapshot)
                    return
            self._respond(404, {"error": "Not found"})

        do_GET = do_POST = do_OPTIONS = _dispatch

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Deep Search localhost API.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--catalog", type=Path, action="append", help="Use the given catalog file(s).")
    parser.add_argument("--frontend-origin", help="Exact origin of the local frontend, e.g. http://localhost:5173")
    args = parser.parse_args()
    catalog = {}
    for path in args.catalog or _CATALOG:
        catalog.update(load_sites_config(path))
    if not args.catalog:
        catalog.pop("example_path_builder", None)
    with make_server(args.port, catalog, args.frontend_origin) as server:
        print(f"Deep Search API listening on http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
