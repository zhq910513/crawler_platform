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
        candidate_data = _read_json(candidate)
        if not candidate_data:
            continue
        # 只接受明确标识为 Agent 的发布元数据。仓库根 .release/version.json 属于平台，
        # 不能作为 Agent 版本兜底，否则普通平台 patch 会把 Agent 伪装成同版本。
        if str(candidate_data.get("appName") or "").strip() == "crawler_platform_agent":
            file_data = candidate_data
            break

    version = (
        os.getenv("AGENT_AGENT_VERSION")
        or os.getenv("AGENT_VERSION")
        or str(file_data.get("version") or "").strip()
    )

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
