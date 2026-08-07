from python_deep_search.extractors import extract_links


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
