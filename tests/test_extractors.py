from python_deep_search.extractors import _navigation_noise_paths, extract_links


def test_extract_links_keeps_single_segment_and_query_result_urls() -> None:
    html = """
        <a href="/album-123">album</a>
        <a href="?id=456">query result</a>
        <a href="/catalog/item-789">nested result</a>
    """

    assert extract_links(html, "https://example.test/search?q=test") == [
        "https://example.test/album-123",
        "https://example.test/search?id=456",
        "https://example.test/catalog/item-789",
    ]


def test_extract_links_resolves_relative_urls_from_the_search_page() -> None:
    html = '<a href="item/123">item</a><a href=/item/456>item</a>'

    assert extract_links(html, "https://example.test/search/page/") == [
        "https://example.test/search/page/item/123",
        "https://example.test/item/456",
    ]


def test_extract_links_honours_explicit_limit() -> None:
    html = "".join(f'<a href="/result-{n}">r</a>' for n in range(10))

    assert len(extract_links(html, "https://example.test", limit=7)) == 7


def test_extract_links_can_prefer_query_matches_over_homepage_navigation() -> None:
    html = """
        <a href="/wiki/English_language">English</a>
        <a href="/wiki/Main_Page">Main page</a>
        <a href="/wiki/Python_(programming_language)">Python programming language</a>
        <a href="/wiki/Pythonidae">Pythonidae</a>
    """

    assert extract_links(
        html,
        "https://en.wikipedia.org/w/index.php?search=python",
        query="python",
        prefer_query_matches=True,
    ) == [
        "https://en.wikipedia.org/wiki/Python_(programming_language)",
        "https://en.wikipedia.org/wiki/Pythonidae",
    ]


def test_search_links_do_not_fallback_to_bunkr_homepage_noise() -> None:
    html = """
        <a href="/topimages">Top images</a>
        <a href="/topfiles">Top files</a>
        <a href="/a/abc123" title="needle archive">album</a>
        <a href="/a/def456"><img alt="needle gallery"></a>
    """

    assert extract_links(
        html,
        "https://balbums.st/?search=needle&mode=broad&per=100&sort=latest",
        query="needle",
        prefer_query_matches=True,
    ) == [
        "https://balbums.st/a/abc123",
        "https://balbums.st/a/def456",
    ]


def test_search_links_return_empty_when_only_homepage_noise_exists() -> None:
    html = """
        <a href="/topimages">Top images</a>
        <a href="/topfiles">Top files</a>
        <a href="/privacy">Privacy</a>
    """

    assert extract_links(
        html,
        "https://balbums.st/?search=needle&mode=broad&per=100&sort=latest",
        query="needle",
        prefer_query_matches=True,
    ) == []


def test_followed_links_drop_bunkr_navigation_noise() -> None:
    html = """
        <a href="/">Home</a>
        <a href="/live">Live</a>
        <a href="/topalbums">Top albums</a>
        <a href="/topvideos">Top videos</a>
        <a href="/topfiles">Top files</a>
        <a href="/topimages">Top images</a>
        <a href="/a/child123">Child album</a>
    """

    assert extract_links(html, "https://balbums.st/a/result") == [
        "https://balbums.st/a/child123",
    ]


def test_navigation_noise_paths_are_loaded_from_config() -> None:
    assert "/topfiles" in _navigation_noise_paths()
