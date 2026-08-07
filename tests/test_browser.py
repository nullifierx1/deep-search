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


def test_open_browser_tab_registers_known_chrome_path(monkeypatch) -> None:
    controller = _Controller()
    registered: dict[str, object] = {}

    monkeypatch.setattr(browser, "_REGISTERED_ALIASES", set())
    monkeypatch.setattr(browser, "_KNOWN_BROWSER_PATHS", {"chrome": [r"C:\Chrome\chrome.exe"]})
    monkeypatch.setattr(browser.Path, "exists", lambda _self: True)
    monkeypatch.setattr(browser.webbrowser, "register", lambda name, _klass, instance: registered.setdefault(name, instance))
    monkeypatch.setattr(browser.webbrowser, "get", lambda name: controller if name == "chrome" else None)

    ok, error = browser.open_browser_tab("https://example.test", "chrome")

    assert ok is True
    assert error is None
    assert "chrome" in registered
    assert controller.opened == ["https://example.test"]


def test_known_chrome_registration_keeps_path_and_url_as_separate_args(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(browser, "_REGISTERED_ALIASES", set())
    monkeypatch.setattr(browser, "_KNOWN_BROWSER_PATHS", {"chrome": [r"C:\Program Files\Chrome\chrome.exe"]})
    monkeypatch.setattr(browser.Path, "exists", lambda _self: True)
    monkeypatch.setattr(browser.webbrowser, "register", lambda name, _klass, instance: captured.setdefault(name, instance))

    browser._register_known_browser("chrome")

    controller = captured["chrome"]
    assert controller.name == r"C:\Program Files\Chrome\chrome.exe"
    assert controller.args == ["%s"]


def test_open_browser_tab_accepts_quoted_command_with_placeholder(monkeypatch) -> None:
    controller = _Controller()
    aliases: list[str] = []

    monkeypatch.setattr(browser, "_REGISTERED_ALIASES", set())
    monkeypatch.setattr(browser.Path, "exists", lambda _self: True)
    monkeypatch.setattr(browser.webbrowser, "register", lambda name, _klass, _instance: aliases.append(name))
    monkeypatch.setattr(browser.webbrowser, "get", lambda _name: controller)

    ok, error = browser.open_browser_tab(
        "https://example.test",
        r'"C:\Program Files\Google\Chrome\Application\chrome.exe" %s',
    )

    assert ok is True
    assert error is None
    assert aliases
    assert controller.opened == ["https://example.test"]


def test_open_browser_tab_reports_unknown_browser(monkeypatch) -> None:
    def raise_error(_name):
        raise webbrowser.Error("not found")

    monkeypatch.setattr(browser.webbrowser, "get", raise_error)

    ok, error = browser.open_browser_tab("https://example.test", "missing")

    assert ok is False
    assert error == "not found"
