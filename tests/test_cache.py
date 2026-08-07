from python_deep_search.cache import _query_key
from python_deep_search.models import SearchRequest


def test_cache_key_changes_when_search_options_change() -> None:
    sites = {"example": {"base_url": "https://example.test"}}
    base = SearchRequest(query="needle", regex_pattern="needle")
    changed_regex = SearchRequest(query="needle", regex_pattern="other")
    changed_limit = SearchRequest(query="needle", regex_pattern="needle", max_links=10)

    assert _query_key(base, sites) != _query_key(changed_regex, sites)
    assert _query_key(base, sites) != _query_key(changed_limit, sites)
