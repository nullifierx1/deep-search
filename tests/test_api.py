from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from time import monotonic, sleep, time
import json

import requests

from python_deep_search import api
from python_deep_search import cache
from python_deep_search.history import SearchHistory
from python_deep_search.models import SiteResult


def test_cache_endpoint_reports_and_clears_results_only(tmp_path, monkeypatch):
    results = tmp_path / "results.json"
    settings = tmp_path / "settings.json"
    monkeypatch.setattr(cache, "RESULTS_FILE", results)
    monkeypatch.setattr(cache, "SETTINGS_FILE", settings)
    cache.set_setting("view", "results")
    results.write_text(json.dumps({"fresh": {"ts": time()}, "old": {"ts": time() - cache.RESULTS_TTL - 1}}))
    with api.make_server(0, {}) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        endpoint = f"http://127.0.0.1:{server.server_port}/api/v1/cache"
        try:
            assert requests.get(endpoint, timeout=3).json()["expired"] == 1
            assert requests.post(endpoint, json={"action": "expired"}, timeout=3).json()["removed"] == 1
            assert set(json.loads(results.read_text())) == {"fresh"}
            assert requests.post(endpoint, json={"action": "all"}, timeout=3).json()["removed"] == 1
            assert json.loads(results.read_text()) == {}
            assert cache.get_setting("view") == "results"
        finally:
            server.shutdown()
            thread.join()


def test_http_catalog_search_progress_and_cancellation(monkeypatch):
    catalog = {"example": {"base_url": "https://example.test"}}
    started = Event()
    following = Event()

    def search(sites, request, *, cancel, result_callback, stage_callback, use_cache):
        assert sites["example"]["path_builder"]["paths"] == ["/", "/mail"]
        assert request.follow_depth == 3
        stage_callback("example", "following")
        following.set()
        assert started.wait(3)
        result = SiteResult("example", catalog["example"]["base_url"], "https://example.test/mail", False)
        result_callback(result)
        assert cancel.wait(3)
        return {"example": result}

    monkeypatch.setattr(api, "deep_search", search)
    with api.make_server(0, catalog, "http://localhost:5173") as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            response = requests.get(base + "/api/sites", headers={"Origin": "http://localhost:5173"}, timeout=3)
            assert response.json() == {"sites": [{"id": "example", "base_url": "https://example.test", "paths": []}]}
            assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
            assert requests.get(base + "/api/v1/sites", timeout=3).json()["sites"][0]["group"] == "default"
            assert requests.get(base + "/api/sites", headers={"Host": "outside.test"}, timeout=3).status_code == 403
            start = base + "/api/searches"
            payload = {"sites": ["example"], "query": "needle", "paths": {"example": ["/", "/mail"]},
                       "options": {"follow_depth": 3}}
            assert requests.post(start, json={**payload, "sites": ["unknown"]}, timeout=3).status_code == 400
            assert requests.post(start, json={**payload, "query": "[ab]" * 20}, timeout=3).status_code == 400
            assert requests.post(start, json={**payload, "paths": {"example": ["//outside.test"]}}, timeout=3).status_code == 400
            response = requests.post(start, json=payload, timeout=3)
            assert response.status_code == 202
            assert following.wait(3)
            assert requests.post(start, json=payload, timeout=3).status_code == 409
            job = start + "/" + response.json()["id"]
            v1_job = job.replace("/api/", "/api/v1/")
            assert requests.get(v1_job, timeout=3).json()["site_progress"]["example"] == {
                "stage": "following", "reason": None,
            }
            started.set()
            assert requests.post(job + "/cancel", timeout=3).json()["status"] == "cancelling"
            deadline = monotonic() + 3
            while monotonic() < deadline:
                snapshot = requests.get(job, timeout=3).json()
                if snapshot["status"] == "cancelled":
                    break
                sleep(0.02)
            assert snapshot["status"] == "cancelled"
            assert snapshot["results"]["example"]["search_url"] == "https://example.test/mail"
            v1 = requests.get(v1_job, timeout=3).json()
            assert v1["results"]["example"]["checked_pages"] == ["https://example.test/mail"]
            assert "search_url" not in v1["results"]["example"]
        finally:
            server.shutdown()
            thread.join()


def test_http_search_crawls_a_local_site_to_the_requested_depth():
    pages = {
        "/mail": '<a href="/thread">needle thread</a>',
        "/thread": '<p>Thread text</p><a href="/reply">Read reply</a>',
        "/reply": "<p>needle evidence</p>",
    }

    class LocalSite(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(pages[self.path].encode())

    with ThreadingHTTPServer(("127.0.0.1", 0), LocalSite) as source:
        site_url = f"http://127.0.0.1:{source.server_port}"
        catalog = {"example": {"base_url": site_url, "network": {"min_delay_sec": 0}}}
        with api.make_server(0, catalog) as server:
            threads = [Thread(target=s.serve_forever, daemon=True) for s in (source, server)]
            for thread in threads:
                thread.start()
            try:
                endpoint = f"http://127.0.0.1:{server.server_port}/api/searches"
                started = requests.post(endpoint, json={
                    "sites": ["example"], "query": "needle", "regex_pattern": "needle evidence",
                    "paths": {"example": ["/mail"]},
                    "options": {"follow_depth": 2, "use_playwright": False, "use_cache": False},
                }, timeout=3)
                assert started.status_code == 202
                deadline = monotonic() + 3
                while monotonic() < deadline:
                    status = requests.get(endpoint + "/" + started.json()["id"], timeout=3).json()
                    if status["status"] != "running":
                        break
                    sleep(0.02)
                assert status["status"] == "completed"
                result = status["results"]["example"]
                assert result["search_url"] == site_url + "/mail"
                assert [page["depth"] for page in result["followed"]] == [1, 2]
                assert result["matches"][0]["text"] == "needle evidence"
            finally:
                source.shutdown()
                server.shutdown()
                for thread in threads:
                    thread.join()


def test_history_and_retry_survive_api_restart(tmp_path, monkeypatch):
    catalog = {name: {"base_url": f"https://{name}.test"} for name in ("first", "second")}
    path = tmp_path / "searches.sqlite3"
    calls = []

    def search(sites, request, *, cancel, result_callback, stage_callback, use_cache):
        calls.append((sites, use_cache))
        results = {}
        for name, config in sites.items():
            result = SiteResult(name, config["base_url"], config["base_url"] + "/page", False)
            results[name] = result
            result_callback(result)
        return results

    monkeypatch.setattr(api, "deep_search", search)

    def wait_for_job(endpoint):
        deadline = monotonic() + 3
        while monotonic() < deadline:
            result = requests.get(endpoint, timeout=3).json()
            if result["status"] == "completed":
                return result
            sleep(0.02)
        raise AssertionError("Search did not complete")

    for restart in (False, True):
        with api.make_server(0, catalog, history_path=path) as server:
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            endpoint = f"http://127.0.0.1:{server.server_port}/api/v1/searches"
            try:
                if not restart:
                    response = requests.post(endpoint, json={
                        "sites": ["first", "second"], "query": "needle", "paths": {"second": ["/page"]},
                    }, timeout=3)
                    assert response.status_code == 202
                    job_id = response.json()["id"]
                    wait_for_job(endpoint + "/" + job_id)
                else:
                    original = wait_for_job(endpoint + "/" + job_id)
                    assert original["finished_sites"] == 2
                    history = requests.get(endpoint + "?limit=1", timeout=3).json()
                    assert history["searches"][0]["id"] == job_id
                    retry = requests.post(endpoint + "/" + job_id + "/retry", json={"sites": ["second"]}, timeout=3)
                    assert retry.status_code == 202
                    repeated = wait_for_job(endpoint + "/" + retry.json()["id"])
                    assert list(repeated["results"]) == ["second"]
                    assert calls[-1][0]["second"]["path_builder"]["paths"] == ["/page"]
                    assert calls[-1][1] is False
            finally:
                server.shutdown()
                worker.join()


def test_unfinished_history_is_marked_interrupted_at_restart(tmp_path):
    path = tmp_path / "searches.sqlite3"
    history = SearchHistory(path)
    history.save({
        "id": "job", "created_at": 123, "status": "running", "total_sites": 2, "finished_sites": 1,
        "site_progress": {"ready": {"stage": "finished", "reason": "found"},
                          "waiting": {"stage": "queued", "reason": None}},
        "results": {"ready": {"search_url": "https://example.test/"}},
    })
    saved = SearchHistory(path).get("job")
    assert saved["status"] == "interrupted"
    assert saved["finished_sites"] == 2
    assert saved["site_progress"]["waiting"]["reason"] == "interrupted"
    assert "ready" in saved["results"]
