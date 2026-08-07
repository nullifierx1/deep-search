import webbrowser

import python_deep_search.browser as browser


class _Controller:
    def __init__(self) -> None:
        self.opened: list[str] = []

    def open_new_tab(self, url: str) -> bool:
        self.opened.append(url)
        return True


def test_open_browser_tab_uses_default_browser(monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(browser.webbrowser, "open_new_tab", lambda url: opened.append(url) is None)

    ok, error = browser.open_browser_tab("https://example.test")

    assert ok is True
    assert error is None
    assert opened == ["https://example.test"]


def test_open_browser_tab_uses_named_browser(monkeypatch) -> None:
    controller = _Controller()
    monkeypatch.setattr(browser.webbrowser, "get", lambda _name: controller)

    ok, error = browser.open_browser_tab("https://example.test", "firefox")

    assert ok is True
    assert error is None
    assert controller.opened == ["https://example.test"]


def test_open_browser_tab_reports_unknown_browser(monkeypatch) -> None:
    def raise_error(_name):
        raise webbrowser.Error("not found")

    monkeypatch.setattr(browser.webbrowser, "get", raise_error)

    ok, error = browser.open_browser_tab("https://example.test", "missing")

    assert ok is False
    assert error == "not found"
