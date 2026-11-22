import json

from python_deep_search.config import load_sites_config
from python_deep_search.models import SearchRequest
from python_deep_search.search_engine import search_site


def test_cppreference_example_loads_link_rules_and_dedupe() -> None:
    sites = load_sites_config("python_deep_search/json-sites-examples/cppreference.json")
    cfg = sites["cppreference"]

    assert cfg["link_rules"]["search_strict_query"] is False
    assert cfg["link_rules"]["include_url_patterns"]
    assert cfg["dedupe"]["strip_suffixes"] == [".html"]
    assert cfg["dedupe"]["path_rewrites"] == [{"from": "^/w/(.*)$", "to": "/$1"}]
    assert cfg["follow"]["enabled"] is True
    assert cfg["follow"]["collect_child_links"] is False


def test_path_builder_checks_root_and_subpages(tmp_path, monkeypatch) -> None:
    path = tmp_path / "sites.json"
    path.write_text(json.dumps({
        "mail": {
            "base_url": "https://mail.google.com/",
            "path_builder": {"paths": ["/", "/mail", "/mail"]},
        },
    }), encoding="utf-8")
    config = load_sites_config(path)["mail"]
    fetched = []

    def fetch_page(url, *_args):
        fetched.append(url)
        if url.endswith("/mail"):
            return "<p>needle</p>"
        return "<p>home</p>"

    monkeypatch.setattr("python_deep_search.search_engine._fetch_page", fetch_page)
    monkeypatch.setattr("python_deep_search.search_engine.time.sleep", lambda _: None)
    result = search_site(
        "mail",
        config,
        SearchRequest(query="needle", regex_pattern="needle", follow_links=False),
    )

    assert fetched == ["https://mail.google.com/", "https://mail.google.com/mail"]
    assert result.search_url.split(" | ") == fetched
    assert result.found
