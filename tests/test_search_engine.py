from python_deep_search.models import SearchMatch, SearchRequest, SiteResult
from python_deep_search.search_engine import _extract_from_page, _filter_child_links, filter_candidates


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
