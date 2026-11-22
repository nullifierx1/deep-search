from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from time import monotonic, sleep

import requests

from python_deep_search import api
from python_deep_search.models import SiteResult


def test_http_catalog_search_progress_and_cancellation(monkeypatch):
    catalog = {"example": {"base_url": "https://example.test"}}
    started = Event()

    def search(sites, request, *, cancel, result_callback, use_cache):
        assert sites["example"]["path_builder"]["paths"] == ["/", "/mail"]
        assert request.follow_depth == 3
        result = SiteResult("example", catalog["example"]["base_url"], "https://example.test/mail", False)
        result_callback(result)
        started.set()
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
            assert requests.get(base + "/api/sites", headers={"Host": "outside.test"}, timeout=3).status_code == 403
            start = base + "/api/searches"
            payload = {"sites": ["example"], "query": "needle", "paths": {"example": ["/", "/mail"]},
                       "options": {"follow_depth": 3}}
            assert requests.post(start, json={**payload, "sites": ["unknown"]}, timeout=3).status_code == 400
            assert requests.post(start, json={**payload, "query": "[ab]" * 20}, timeout=3).status_code == 400
            assert requests.post(start, json={**payload, "paths": {"example": ["//outside.test"]}}, timeout=3).status_code == 400
            response = requests.post(start, json=payload, timeout=3)
            assert response.status_code == 202
            assert started.wait(3)
            assert requests.post(start, json=payload, timeout=3).status_code == 409
            job = start + "/" + response.json()["id"]
            assert requests.get(job, timeout=3).json()["finished_sites"] == 1
            assert requests.post(job + "/cancel", timeout=3).json()["status"] == "cancelling"
            deadline = monotonic() + 3
            while monotonic() < deadline:
                snapshot = requests.get(job, timeout=3).json()
                if snapshot["status"] == "cancelled":
                    break
                sleep(0.02)
            assert snapshot["status"] == "cancelled"
            assert snapshot["results"]["example"]["search_url"] == "https://example.test/mail"
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
