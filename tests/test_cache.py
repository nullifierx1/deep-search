from python_deep_search import cache
from python_deep_search.cache import _query_key
from python_deep_search.models import SearchRequest, SiteResult
from python_deep_search.search_engine import deep_search


def test_cache_key_changes_when_search_options_change() -> None:
    sites = {"example": {"base_url": "https://example.test"}}
    base = SearchRequest(query="needle", regex_pattern="needle")
    changed_regex = SearchRequest(query="needle", regex_pattern="other")
    changed_limit = SearchRequest(query="needle", regex_pattern="needle", max_links=10)

    assert _query_key(base, sites) != _query_key(changed_regex, sites)
    assert _query_key(base, sites) != _query_key(changed_limit, sites)


def test_cached_results_preserve_checked_page_urls(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "RESULTS_FILE", tmp_path / "results.json")
    base_url = "https://example.test"
    sites = {"example": {"base_url": base_url}}
    request = SearchRequest(query="needle", regex_pattern="")
    checked = f"{base_url}/ | {base_url}/mail"
    cache.set_cached_results(request, sites, {
        "example": SiteResult("example", base_url, checked, found=False),
    })

    assert deep_search(sites=sites, req=request)["example"].search_url == checked
