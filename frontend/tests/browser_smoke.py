"""Exercise the Vite client against an isolated local catalog and real Python API."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread

from playwright.sync_api import expect, sync_playwright

from python_deep_search.api import make_server


@contextmanager
def serving(server):
    with server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield server
        finally:
            server.shutdown()
            worker.join()


def main():
    release = Event()

    class Source(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/slow":
                release.wait(8)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'<a href="/article">needle example page</a>')

    origin = "http://127.0.0.1:5173"
    with TemporaryDirectory() as temp, serving(ThreadingHTTPServer(("127.0.0.1", 0), Source)) as source:
        base = f"http://127.0.0.1:{source.server_port}"
        catalog = {"fixture": {"base_url": base, "name": "Local fixture", "group": "sites",
                               "network": {"min_delay_sec": 0}}}
        with serving(make_server(0, catalog, origin, history_path=Path(temp) / "history.db")) as server:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 920})
                page.set_default_timeout(6000)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))

                def reroute(route):
                    suffix = route.request.url.split("/api/v1", 1)[1]
                    route.fulfill(response=route.fetch(url=f"http://127.0.0.1:{server.server_port}/api/v1{suffix}"))

                page.route("**/api/v1/**", reroute)
                page.goto(origin)
                page.get_by_role("checkbox", name="Local fixture").check()
                page.get_by_role("button", name="Пути для Local fixture").click()
                paths = page.get_by_role("textbox", name="Пути, каждый с новой строки")
                paths.fill("/catalog")
                page.get_by_role("textbox", name="Поисковый запрос").fill("needle")
                page.get_by_role("button", name="Настройки").click()
                page.get_by_role("checkbox", name="Включить Playwright").uncheck()
                page.get_by_role("checkbox", name="Обходить ссылки").uncheck()
                page.get_by_role("button", name="Найти", exact=True).click()
                expect(page.locator(".result-row")).to_contain_text("Найдено")
                page.locator(".result-row").click()
                expect(page.get_by_role("link", name=base + "/article")).to_be_visible()
                expect(page.get_by_role("link", name=base + "/catalog")).to_be_visible()

                page.reload()
                expect(page.locator(".result-row")).to_contain_text("Найдено")
                page.get_by_role("button", name="История", exact=True).click()
                page.locator(".history-row").click()
                page.get_by_role("button", name="Повторить", exact=True).click()
                with page.expect_response(lambda response: response.url.endswith("/retry")) as response:
                    page.get_by_role("button", name="Запустить повтор").click()
                assert response.value.status == 202
                expect(page.locator(".result-row")).to_contain_text("Найдено")

                page.get_by_role("checkbox", name="Local fixture").check()
                page.get_by_role("button", name="Пути для Local fixture").click()
                paths.fill("/slow")
                page.get_by_role("textbox", name="Поисковый запрос").fill("cancel me")
                page.get_by_role("button", name="Настройки").click()
                page.get_by_role("checkbox", name="Включить Playwright").uncheck()
                page.get_by_role("button", name="Найти", exact=True).click()
                with page.expect_response(lambda response: response.url.endswith("/cancel")) as response:
                    page.get_by_role("button", name="Остановить").click()
                assert response.value.status == 200
                release.set()
                expect(page.locator(".section-title")).to_contain_text("Отменено")

                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
                assert not errors, errors
                page.unroute_all(behavior="wait")
                browser.close()
    print("Browser smoke passed.")


if __name__ == "__main__":
    main()
