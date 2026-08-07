from python_deep_search.models import SearchRequest
from python_deep_search.search_engine import _extract_from_page


def test_search_page_query_echo_is_not_reported_as_a_match() -> None:
    page = '<h1>Search results for needle</h1><a href="/result-1">result</a>'
    req = SearchRequest(query="needle", regex_pattern="")

    links, matches = _extract_from_page(
        page, "https://example.test/search?q=needle", req, include_query_snippets=False
    )

    assert links == ["https://example.test/result-1"]
    assert matches == []
