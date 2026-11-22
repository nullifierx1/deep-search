from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re
from threading import Event
from time import monotonic
from urllib.parse import urljoin, urlsplit

import requests

_ACCESS_ERRORS = {
    401: "authentication_required", 403: "access_denied", 407: "proxy_authentication_required",
    429: "rate_limited", 451: "unavailable_for_legal_reasons",
}
_CHALLENGE_TITLE = re.compile(
    r"<title>\s*(?:just a moment[.!…]*|attention required!?\s*\|\s*cloudflare|"
    r"verify (?:that )?you are human)\s*</title>", re.IGNORECASE,
)
SOURCE_STOP = {"authentication_required", "access_denied", "proxy_authentication_required",
               "rate_limited", "unavailable_for_legal_reasons", "bot_challenge", "request_budget"}


def is_challenge(html: str) -> bool:
    return bool(_CHALLENGE_TITLE.search(html[:8192]))


def _retry_after(value: str) -> float:
    try:
        return max(0, int(value))
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 0


class SearchSession(requests.Session):
    def __init__(self, cancel: Event, policy: dict | None, request_limit: int = 100) -> None:
        super().__init__()
        self.cancel = cancel
        self.policy = policy or {}
        self.status: int | None = None
        self.failure: str | None = None
        self.request_limit = request_limit
        self.http_requests = 0
        self.browser_renders = 0
        self.rendered_current = False
        self._min_delay = self.policy.get("min_delay_sec", 0.5)
        self._max_delay = self.policy.get("max_delay_sec", self._min_delay)
        self._delay = self._min_delay
        self._next_request = monotonic()

    @property
    def can_render(self) -> bool:
        return not self.cancel.is_set() and self.failure is None and not self.rendered_current

    def begin_render(self) -> bool:
        if not self._within_budget():
            return False
        self.rendered_current = True
        self.browser_renders += 1
        return True

    def _within_budget(self) -> bool:
        if self.http_requests + self.browser_renders < self.request_limit:
            return True
        self.failure = "request_budget"
        return False

    def _pace(self, elapsed: float, successful: bool) -> None:
        target = min(self._max_delay, max(self._min_delay, elapsed))
        if not successful:
            target = max(self._delay, target)
        self._delay = (self._delay + target) / 2
        self._next_request = monotonic() + self._delay

    def _get_page(self, url: str, headers: dict, timeout: int) -> requests.Response | None:
        for _ in range(6):
            if not self._within_budget():
                return None
            if self.cancel.wait(max(0, self._next_request - monotonic())):
                self.failure = "cancelled"
                return None
            if not self.policy.get("use_cookies", True):
                self.cookies.clear()
            started = monotonic()
            successful = False
            try:
                self.http_requests += 1
                response = self.get(url, headers=headers, timeout=timeout, allow_redirects=False)
                successful = response.status_code == 200
            finally:
                self._pace(monotonic() - started, successful)
            self.status = response.status_code
            if response.status_code not in {301, 302, 303, 307, 308} or not response.headers.get("Location"):
                return response
            url = urljoin(url, response.headers["Location"])
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username is not None:
                self.failure = "invalid_redirect"
                return None
        self.failure = "redirect_limit"
        return None

    def fetch(self, url: str, headers: dict, timeout: int) -> str | None:
        self.status = None
        self.failure = None
        self.rendered_current = False
        retry_codes = self.policy.get("retry_on_status", [429, 500, 502, 503, 504])
        retries = self.policy.get("max_retries", 2)
        for attempt in range(retries + 1):
            retry_after = 0
            try:
                response = self._get_page(url, headers, timeout)
            except requests.exceptions.ProxyError:
                self.failure = "proxy_error"
                break
            except requests.exceptions.SSLError:
                self.failure = "tls_error"
                break
            except (requests.ConnectionError, requests.Timeout) as error:
                self.failure = "timeout" if isinstance(error, requests.Timeout) else "connection_error"
            except (requests.RequestException, ValueError):
                self.failure = "request_error"
                break
            else:
                if response is None:
                    break
                if response.headers.get("cf-mitigated", "").lower() == "challenge":
                    self.failure = "bot_challenge"
                    break
                if response.status_code == 200:
                    if is_challenge(response.text):
                        self.failure = "bot_challenge"
                        break
                    self.failure = None
                    return response.text
                self.failure = _ACCESS_ERRORS.get(response.status_code, f"http_{response.status_code}")
                if response.status_code in {401, 403, 407, 451} or response.status_code not in retry_codes:
                    break
                retry_after = _retry_after(response.headers.get("Retry-After", ""))
            if attempt == retries or retry_after > 60:
                break
            if self.cancel.wait(max(retry_after, 2 ** attempt)):
                self.failure = "cancelled"
                break
        return None
