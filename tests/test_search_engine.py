from python_deep_search.models import SearchMatch, SearchRequest, SiteResult
from python_deep_search.search_engine import (
    _extract_from_page,
    _filter_child_links,
    search_site,
    filter_candidates,
)


def test_search_page_query_echo_is_not_reported_as_a_match() -> None:
    page = '<h1>Search results for needle</h1><a href="/result-1">result</a>'
    req = SearchRequest(query="needle", regex_pattern="")

    links, matches = _extract_from_page(
        page, "https://example.test/search?q=needle", req, include_query_snippets=False
    )

    assert links == ["https://example.test/result-1"]
    assert matches == []


def test_child_links_exclude_search_level_links() -> None:
    assert _filter_child_links(
        [
            "https://example.test/result-1",
            "https://example.test/result-1",
            "https://example.test/child",
        ],
        ["https://example.test/result-1"],
        10,
    ) == ["https://example.test/child"]


def test_candidates_require_search_level_links() -> None:
    results = {
        "matches-only": SiteResult(
            site_name="matches-only",
            base_url="https://example.test",
            search_url="https://example.test/search?q=needle",
            found=True,
            matches=[SearchMatch("needle", 60)],
            urls=[],
        ),
        "with-links": SiteResult(
            site_name="with-links",
            base_url="https://example.test",
            search_url="https://example.test/search?q=needle",
            found=True,
            urls=["https://example.test/result"],
        ),
    }

    assert list(filter_candidates(results)) == ["with-links"]


def test_site_follow_config_can_disable_child_links(monkeypatch) -> None:
    pages = {
        "https://example.test/search?q=needle": '<a href="/result-1">needle result</a>',
        "https://example.test/result-1": '<p>needle content</p><a href="/child">needle child</a>',
    }

    def fake_fetch(url, _session, _headers, _timeout, _use_playwright=True):
        return pages[url]

    monkeypatch.setattr("python_deep_search.search_engine._fetch_page", fake_fetch)
    result = search_site(
        "example",
        {
            "base_url": "https://example.test",
            "search_template": "{base}/search?q={query}",
            "use_full_path": False,
            "params": None,
            "path_builder": None,
            "link_rules": {"search_strict_query": True},
            "dedupe": {},
            "follow": {"collect_child_links": False},
        },
        SearchRequest(query="needle", regex_pattern="", follow_limit=1, use_playwright=False),
    )

    assert result.urls == ["https://example.test/result-1"]
    assert len(result.followed) == 1
    assert result.followed[0].matches
    assert result.followed[0].urls == []


def test_site_follow_config_can_disable_following(monkeypatch) -> None:
    pages = {
        "https://example.test/search?q=needle": '<a href="/result-1">needle result</a>',
    }
    fetched: list[str] = []

    def fake_fetch(url, _session, _headers, _timeout, _use_playwright=True):
        fetched.append(url)
        return pages[url]

    monkeypatch.setattr("python_deep_search.search_engine._fetch_page", fake_fetch)
    result = search_site(
        "example",
        {
            "base_url": "https://example.test",
            "search_template": "{base}/search?q={query}",
            "use_full_path": False,
            "params": None,
            "path_builder": None,
            "link_rules": {"search_strict_query": True},
            "dedupe": {},
            "follow": {"enabled": False, "collect_child_links": True},
        },
        SearchRequest(query="needle", regex_pattern="", follow_limit=1, use_playwright=False),
    )

    assert result.urls == ["https://example.test/result-1"]
    assert result.followed == []
    assert fetched == ["https://example.test/search?q=needle"]
