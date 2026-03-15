from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from .config import UpdateConfig


UPDATE_CACHE_PATH = Path(".insightforge") / "update-check.json"


def maybe_get_update_message(current_version: str, config: UpdateConfig) -> str | None:
    if not config.enabled or os.environ.get("INSIGHTFORGE_SKIP_UPDATE_CHECK") == "1":
        return None

    latest_version = _get_latest_version_cached(config)
    if not latest_version or not is_newer_version(latest_version, current_version):
        return None

    return (
        f"A newer InsightForge version is available ({latest_version}; current {current_version}). "
        "Update with `pipx upgrade insightforge` or `pip install -U insightforge`."
    )


def is_newer_version(latest_version: str, current_version: str) -> bool:
    return _parse_version(latest_version) > _parse_version(current_version)


def _parse_version(value: str) -> tuple[int, ...]:
    parts = []
    for segment in value.split("."):
        digits = "".join(char for char in segment if char.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _get_latest_version_cached(config: UpdateConfig) -> str | None:
    UPDATE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache = _load_cache()

    checked_at_raw = cache.get("checked_at")
    if checked_at_raw:
        checked_at = datetime.fromisoformat(checked_at_raw)
        if checked_at >= datetime.now(timezone.utc) - timedelta(hours=config.check_interval_hours):
            return cache.get("latest_version")

    latest = _fetch_latest_version(config.package_name)
    _save_cache(
        {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "latest_version": latest,
        }
    )
    return latest


def _fetch_latest_version(package_name: str) -> str | None:
    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        with urlopen(url, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None
    return payload.get("info", {}).get("version")


def _load_cache() -> dict[str, str]:
    if not UPDATE_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(UPDATE_CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_cache(payload: dict[str, str | None]) -> None:
    UPDATE_CACHE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
