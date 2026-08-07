from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import SiteResult


def to_serializable(results: dict[str, SiteResult]) -> dict:
    payload = {}
    for site_name, result in results.items():
        payload[site_name] = asdict(result)
    return payload


def save_results_json(results: dict[str, SiteResult], path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = to_serializable(results)
    with target.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return target
