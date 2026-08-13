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
    file_data: dict[str, Any] = {}
    for candidate in (Path("/opt/crawler-agent/.release/version.json"), Path(".release/version.json")):
        file_data = _read_json(candidate)
        if file_data:
            break

    version = (
        os.getenv("AGENT_AGENT_VERSION")
        or os.getenv("AGENT_VERSION")
        or os.getenv("APP_VERSION")
        or str(file_data.get("version") or "").strip()
    )
    if not version:
        repo_root_version = Path(__file__).resolve().parents[2] / "VERSION"
        for candidate in (Path("/opt/crawler-agent/VERSION"), Path("VERSION"), repo_root_version):
            try:
                if candidate.exists():
                    version = candidate.read_text(encoding="utf-8").strip()
                    break
            except Exception:
                pass

    return {
        "appName": str(file_data.get("appName") or "crawler_platform_agent"),
        "version": version or _DEFAULT_VERSION,
        "gitCommit": os.getenv("AGENT_GIT_COMMIT") or os.getenv("APP_GIT_COMMIT") or str(file_data.get("gitCommit") or _DEFAULT_COMMIT),
        "buildTime": os.getenv("AGENT_BUILD_TIME") or os.getenv("APP_BUILD_TIME") or str(file_data.get("buildTime") or _DEFAULT_BUILD_TIME),
    }


def default_version() -> str:
    return release_metadata()["version"]


def default_git_commit() -> str:
    return release_metadata()["gitCommit"]


def default_build_time() -> str:
    return release_metadata()["buildTime"]
