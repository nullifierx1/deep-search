from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(slots=True)
class SearchMatch:
    text: str
    score: int = 0


@dataclass(slots=True)
class FollowResult:
    source_url: str
    matches: List[SearchMatch] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    error: Optional[str] = None
    depth: int = 1


@dataclass(slots=True)
class SiteResult:
    site_name: str
    base_url: str
    search_url: str
    found: bool
    matches: List[SearchMatch] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    followed: List[FollowResult] = field(default_factory=list)
    status_code: Optional[int] = None
    elapsed_sec: float = 0.0
    error: Optional[str] = None
    search_stop_reason: str | None = None
    follow_stop_reason: str | None = None
    network_errors: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class SearchRequest:
    query: str
    regex_pattern: str
    max_results: int = 10
    max_links: int = 100
    timeout_sec: int = 15
    follow_links: bool = True
    follow_limit: int = 5
    use_playwright: bool = True
    verbose: bool = False
    follow_depth: int = 1
    stop_after_empty: int = 0
