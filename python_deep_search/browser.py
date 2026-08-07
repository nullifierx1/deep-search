from __future__ import annotations

import webbrowser


def open_browser_tab(url: str, browser_name: str = "") -> tuple[bool, str | None]:
    name = browser_name.strip()
    try:
        controller = webbrowser.get(name) if name else webbrowser
        ok = controller.open_new_tab(url)
    except webbrowser.Error as e:
        return False, str(e)
    return bool(ok), None if ok else "browser returned false"
