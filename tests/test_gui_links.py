from python_deep_search.gui import DeepSearchApp
import python_deep_search.gui as gui


class _Status:
    def __init__(self) -> None:
        self.values: list[str] = []

    def set(self, value: str) -> None:
        self.values.append(value)


class _AppStub:
    def __init__(self) -> None:
        self.status_var = _Status()

    def after(self, _delay: int, callback, *args) -> None:
        callback(*args)


def test_bulk_link_opening_uses_a_new_tab_for_every_url(monkeypatch) -> None:
    app = _AppStub()
    opened: list[str] = []
    monkeypatch.setattr(gui.webbrowser, "open_new_tab", lambda url: opened.append(url))
    monkeypatch.setattr(gui._time, "sleep", lambda _seconds: None)

    DeepSearchApp._open_links_worker(app, ["https://example.test/1", "https://example.test/2"])

    assert opened == ["https://example.test/1", "https://example.test/2"]
    assert app.status_var.values[-1] == "Открыто ссылок: 2"
