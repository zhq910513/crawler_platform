from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

_DEFAULT_VERSION = "0.0.0"
_DEFAULT_COMMIT = "unknown"
_DEFAULT_BUILD_TIME = "unknown"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        return {}
    return {}


@lru_cache(maxsize=1)
def release_metadata() -> dict[str, str]:
    """Return runtime release metadata from the shared release contract.

    Runtime env variables are authoritative in containers. The optional
    /app/.release/version.json file is a secondary source used by packaged or
    offline deployments. The VERSION file is only a final development fallback.
    """
    file_data: dict[str, Any] = {}
    for candidate in (Path("/app/.release/version.json"), Path(".release/version.json")):
        file_data = _read_json(candidate)
        if file_data:
            break

    version = os.getenv("APP_VERSION") or str(file_data.get("version") or "").strip()
    if not version:
        for candidate in (Path("/app/VERSION"), Path("VERSION")):
            try:
                if candidate.exists():
                    version = candidate.read_text(encoding="utf-8").strip()
                    break
            except Exception:
                pass

    return {
        "appName": os.getenv("APP_NAME") or str(file_data.get("appName") or "crawler_platform"),
        "version": version or _DEFAULT_VERSION,
        "gitCommit": os.getenv("APP_GIT_COMMIT") or str(file_data.get("gitCommit") or _DEFAULT_COMMIT),
        "buildTime": os.getenv("APP_BUILD_TIME") or str(file_data.get("buildTime") or _DEFAULT_BUILD_TIME),
    }


def default_version() -> str:
    return release_metadata()["version"]


def default_git_commit() -> str:
    return release_metadata()["gitCommit"]


def default_build_time() -> str:
    return release_metadata()["buildTime"]
