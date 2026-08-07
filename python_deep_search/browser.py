from __future__ import annotations

import os
from pathlib import Path
import webbrowser


_REGISTERED_ALIASES: set[str] = set()

_KNOWN_BROWSER_PATHS = {
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
    ],
    "edge": [
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
    ],
}


def _register_known_browser(name: str) -> None:
    alias = name.strip().lower()
    if alias in _REGISTERED_ALIASES:
        return
    for path in _KNOWN_BROWSER_PATHS.get(alias, []):
        if Path(path).exists():
            webbrowser.register(alias, None, webbrowser.BackgroundBrowser([path, "%s"]))
            _REGISTERED_ALIASES.add(alias)
            return


def _register_browser_command(command: str) -> str:
    spec = command.strip()
    alias = f"custom-{abs(hash(spec))}"
    if alias in _REGISTERED_ALIASES:
        return alias

    if spec.endswith("%s"):
        executable = spec[:-2].strip().strip("\"'")
        if Path(executable).exists():
            webbrowser.register(alias, None, webbrowser.BackgroundBrowser([executable, "%s"]))
            _REGISTERED_ALIASES.add(alias)
            return alias

    return spec


def open_browser_tab(url: str, browser_name: str = "") -> tuple[bool, str | None]:
    name = browser_name.strip()
    try:
        if name:
            _register_known_browser(name)
            if "%s" in name:
                name = _register_browser_command(name)
        controller = webbrowser.get(name) if name else webbrowser
        ok = controller.open_new_tab(url)
    except webbrowser.Error as e:
        return False, str(e)
    return bool(ok), None if ok else "browser returned false"
