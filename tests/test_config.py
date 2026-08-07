from python_deep_search.config import load_sites_config


def test_cppreference_example_loads_link_rules_and_dedupe() -> None:
    sites = load_sites_config("python_deep_search/json-sites-examples/cppreference.json")
    cfg = sites["cppreference"]

    assert cfg["link_rules"]["search_strict_query"] is False
    assert cfg["link_rules"]["include_url_patterns"]
    assert cfg["dedupe"]["strip_suffixes"] == [".html"]
    assert cfg["dedupe"]["path_rewrites"] == [{"from": "^/w/(.*)$", "to": "/$1"}]
    assert cfg["follow"]["enabled"] is True
    assert cfg["follow"]["collect_child_links"] is False
