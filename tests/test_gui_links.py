from python_deep_search.gui import DeepSearchApp
import python_deep_search.gui as gui


class _Text:
    def __init__(self) -> None:
        self.tags: list[tuple[str, str, str]] = []
        self.bindings: list[str] = []
        self.inserted = False

    def index(self, _index: str) -> str:
        return "1.22" if self.inserted else "1.0"

    def insert(self, _index: str, _text: str) -> None:
        self.inserted = True

    def tag_add(self, tag: str, start: str, end: str) -> None:
        self.tags.append((tag, start, end))

    def tag_bind(self, tag: str, _sequence: str, _callback) -> None:
        self.bindings.append(tag)


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


def test_single_link_gets_clickable_url_range() -> None:
    app = object.__new__(DeepSearchApp)
    app.text = _Text()
    app._url_tag_count = 0

    DeepSearchApp._append_url(app, "https://example.test/1")

    assert app.text.tags == [
        ("url", "1.0", "1.22"),
        ("url-0", "1.0", "1.22"),
    ]
    assert app.text.bindings == ["url-0"]


def test_bulk_link_opening_uses_a_new_tab_for_every_url(monkeypatch) -> None:
    app = _AppStub()
    opened: list[tuple[str, str]] = []
    monkeypatch.setattr(gui, "open_browser_tab", lambda url, browser_name="": (opened.append((url, browser_name)) is None, None))
    monkeypatch.setattr(gui._time, "sleep", lambda _seconds: None)

    DeepSearchApp._open_links_worker(app, ["https://example.test/1", "https://example.test/2"], "firefox")

    assert opened == [("https://example.test/1", "firefox"), ("https://example.test/2", "firefox")]
    assert app.status_var.values[-1] == "Opened links: 2"
