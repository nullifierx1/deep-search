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


def test_access_denial_is_reported_without_retry_or_browser_fallback(monkeypatch):
    site = load_sites_config("python_deep_search/json-sites-examples/lk-sites.json")["asmrfree"]
    assert 403 not in site["network"]["retry_on_status"]
    site["path_builder"] = {"paths": ["/"]}
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
