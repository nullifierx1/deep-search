from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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



def test_concurrent_settings_writes_preserve_each_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cache, "SETTINGS_FILE", tmp_path / "settings.json")
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda key: cache.set_setting(str(key), "value"), range(30)))
    assert all(cache.get_setting(str(key)) == "value" for key in range(30))


def test_failed_cache_replace_leaves_previous_settings_intact(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cache, "SETTINGS_FILE", tmp_path / "settings.json")
    cache.set_setting("key", "original")

    def fail(*_):
        raise PermissionError("file locked")

    monkeypatch.setattr(Path, "replace", fail)
    cache.set_setting("key", "replacement")
    assert cache.get_setting("key") == "original"
    assert list(tmp_path.iterdir()) == [cache.SETTINGS_FILE]
