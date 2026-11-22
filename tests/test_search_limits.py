from threading import Event

from python_deep_search.models import SearchRequest
from python_deep_search.search_engine import deep_search, search_site


def _mock_pages(monkeypatch, pages):
    fetched = []

    def fetch(url, *_):
        fetched.append(url)
        return pages[url]

    monkeypatch.setattr("python_deep_search.search_engine._fetch_page", fetch)
    monkeypatch.setattr(Event, "wait", lambda self, timeout=None: self.is_set())
    return fetched


def test_pagination_stops_after_consecutive_empty_pages(monkeypatch):
    base = "https://example.test"
    fetched = _mock_pages(monkeypatch, {base + "/1": "<p>empty</p>", base + "/2": "<p>empty</p>"})
    result = search_site(
        "example", {"base_url": base, "path_builder": {"pattern": "/{n}", "start": 1, "end": 5, "step": 1}},
        SearchRequest("needle", "", stop_after_empty=2),
    )
    assert fetched == [base + "/1", base + "/2"]
    assert result.search_stop_reason == "empty_limit"
    assert not result.found


def test_repeated_pagination_results_do_not_reset_empty_streak(monkeypatch):
    base = "https://example.test"
    body = '<a href="/thread">The same result</a>'
    fetched = _mock_pages(monkeypatch, {base + "/1": body, base + "/2": body})
    result = search_site(
        "example", {"base_url": base, "path_builder": {"paths": ["/1", "/2", "/3"]}},
        SearchRequest("needle", "", follow_links=False, stop_after_empty=1),
    )
    assert fetched == [base + "/1", base + "/2"]
    assert result.urls == [base + "/thread"]
    assert result.search_stop_reason == "empty_limit"


def test_canonical_duplicates_across_seed_pages_are_fetched_once(monkeypatch):
    base = "https://example.test"
    fetched = _mock_pages(monkeypatch, {
        base + "/1": '<a href="/thread?tracking=one">Result</a>',
        base + "/2": '<a href="/thread?tracking=two">Result</a>',
        base + "/thread?tracking=one": "<p>needle evidence on this page</p>",
    })
    result = search_site(
        "example", {"base_url": base, "path_builder": {"paths": ["/1", "/2#section"]},
                    "dedupe": {"ignore_query": True}},
        SearchRequest("needle", "", follow_depth=2),
    )
    assert fetched == [base + "/1", base + "/2", base + "/thread?tracking=one"]
    assert result.urls == [base + "/thread?tracking=one"]


def test_deep_follow_uses_breadth_first_order_and_stops_on_empty_pages(monkeypatch):
    base = "https://example.test"
    fetched = _mock_pages(monkeypatch, {
        base + "/": '<a href="/first">needle</a><a href="/second">needle</a>',
        base + "/first": '<p>needle</p><a href="/nested">read next</a>',
        base + "/second": "<p>empty</p>",
        base + "/nested": '<a href="/first">cycle</a><a href="/skip">skip</a>',
    })
    result = search_site(
        "example", {"base_url": base, "path_builder": {"paths": ["/"]}},
        SearchRequest("needle", "", follow_depth=3, stop_after_empty=2, use_playwright=False),
    )
    assert fetched == [base + "/", base + "/first", base + "/second", base + "/nested"]
    assert [page.depth for page in result.followed] == [1, 1, 2]
    assert result.follow_stop_reason == "empty_limit"


def test_cancellation_keeps_partial_results_without_caching(monkeypatch):
    base = "https://example.test"
    cancel = Event()

    def fetch(url, *_):
        assert url == base + "/"
        cancel.set()
        return "<p>needle</p>"

    monkeypatch.setattr("python_deep_search.search_engine._fetch_page", fetch)
    monkeypatch.setattr("python_deep_search.cache.get_cached_results", lambda *args: None)

    def unexpected_cache_write(*_):
        raise AssertionError("partial result was cached")

    monkeypatch.setattr("python_deep_search.cache.set_cached_results", unexpected_cache_write)
    sites = {"example": {"base_url": base, "path_builder": {"paths": ["/", "/later"]}}}
    results = deep_search(sites, SearchRequest("needle", "needle"), cancel=cancel)
    assert results["example"].found
    assert results["example"].search_stop_reason == "cancelled"
