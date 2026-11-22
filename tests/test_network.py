import json
from threading import Event

import pytest
import requests

from python_deep_search.config import load_sites_config
from python_deep_search.models import SearchRequest
from python_deep_search.network import SearchSession
from python_deep_search.search_engine import search_site


def _response(status, body=b"", **headers):
    response = requests.Response()
    response.status_code = status
    response._content = body
    response.headers.update(headers)
    return response


@pytest.mark.parametrize("use_cookies", [True, False])
def test_cookie_policy_applies_across_redirects(monkeypatch, use_cookies):
    with SearchSession(Event(), {"min_delay_sec": 0, "use_cookies": use_cookies}) as session:
        cookies_sent = []

        def get(url, **kwargs):
            assert kwargs["allow_redirects"] is False
            cookies_sent.append(session.cookies.get("session"))
            if url.endswith("/"):
                session.cookies.set("session", "value", domain="example.test")
                return _response(302, Location="/page")
            return _response(200, b"page")

        monkeypatch.setattr(session, "get", get)
        assert session.fetch("https://example.test/", {}, 3) == "page"
        assert cookies_sent == [None, "value" if use_cookies else None]


def test_retry_after_is_observed(monkeypatch):
    cancel = Event()
    waits = []
    monkeypatch.setattr(cancel, "wait", lambda seconds: waits.append(seconds) or False)
    with SearchSession(cancel, {"max_retries": 1, "min_delay_sec": 0}) as session:
        responses = iter([_response(429, **{"Retry-After": "7"}), _response(200, b"ok")])
        monkeypatch.setattr(session, "get", lambda *args, **kwargs: next(responses))
        assert session.fetch("https://example.test/", {}, 3) == "ok"
        assert waits == [0, 7, 0]


def test_access_denial_is_reported_without_retry_or_browser_fallback(monkeypatch, tmp_path):
    catalog = tmp_path / "sites.json"
    catalog.write_text(json.dumps({"example": {
        "base_url": "https://example.test",
        "path_builder": {"paths": ["/"]},
        "anti_block": {"retry_on_status": [403, 429]},
    }}), encoding="utf-8")
    site = load_sites_config(catalog)["example"]
    assert 403 not in site["network"]["retry_on_status"]
    urls = []

    def get(_session, url, **_kwargs):
        urls.append(url)
        return _response(403)

    def unexpected_browser(*_):
        pytest.fail("access denial reached browser fallback")

    monkeypatch.setattr(SearchSession, "get", get)
    monkeypatch.setattr("python_deep_search.search_engine._fetch_html_playwright", unexpected_browser)
    result = search_site("example", site, SearchRequest("needle", ""))
    assert urls == [site["base_url"] + "/"]
    assert result.status_code == 403
    assert result.network_errors == {urls[0]: "access_denied"}
    assert not result.found


def test_proxy_failure_has_specific_diagnostic(monkeypatch):
    def get(*_, **__):
        raise requests.exceptions.ProxyError("proxy unavailable")

    monkeypatch.setattr(SearchSession, "get", get)
    result = search_site("example", {"base_url": "https://example.test", "path_builder": {"paths": ["/"]}},
                         SearchRequest("needle", ""))
    assert result.network_errors == {"https://example.test/": "proxy_error"}


@pytest.mark.parametrize("response", [
    _response(200, b"<title>Just a moment...</title>"),
    _response(503, **{"cf-mitigated": "challenge"}),
])
def test_bot_challenge_stops_source_without_more_requests(monkeypatch, response):
    calls = []
    monkeypatch.setattr(SearchSession, "get", lambda _, url, **kwargs: calls.append(url) or response)
    site = {"base_url": "https://example.test", "path_builder": {"paths": ["/", "/later"]}}
    result = search_site("example", site, SearchRequest("needle", ""))
    assert calls == ["https://example.test/"]
    assert result.search_stop_reason == "bot_challenge"
    assert result.http_requests == 1
    assert result.browser_renders == 0


def test_request_budget_counts_redirects(monkeypatch):
    calls = []
    monkeypatch.setattr(
        SearchSession, "get", lambda _, url, **kwargs: calls.append(url) or _response(302, Location="/next"),
    )
    site = {"base_url": "https://example.test", "path_builder": {"paths": ["/", "/later"]}}
    result = search_site("example", site, SearchRequest("needle", "", max_requests_per_site=1))
    assert calls == ["https://example.test/"]
    assert result.search_stop_reason == "request_budget"


def test_search_launches_browser_at_most_once_for_one_page(monkeypatch):
    monkeypatch.setattr(SearchSession, "get", lambda *args, **kwargs: _response(200, b"<p>small shell</p>"))
    renders = []
    monkeypatch.setattr(
        "python_deep_search.search_engine._fetch_html_playwright",
        lambda url, _: renders.append(url) or "<p>another small shell</p>",
    )
    site = {"base_url": "https://example.test", "search_template": "{base}/search?q={query}"}
    result = search_site("example", site, SearchRequest("needle", ""))
    assert len(renders) == result.browser_renders == 1


def test_adaptive_pacing_does_not_speed_up_after_quick_errors():
    with SearchSession(Event(), {"min_delay_sec": 0.5, "max_delay_sec": 2}) as session:
        session._pace(elapsed=3, successful=True)
        assert session._delay == 1.25
        session._pace(elapsed=0.01, successful=False)
        assert session._delay == 1.25
        session._pace(elapsed=0.1, successful=True)
        assert session._delay == 0.875
