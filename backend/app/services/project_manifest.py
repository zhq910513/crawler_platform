from __future__ import annotations

import hashlib
import re
from typing import Any

ENTRY_RE = re.compile(r"^(?P<module>[A-Za-z_][A-Za-z0-9_.]*):(?P<function>[A-Za-z_][A-Za-z0-9_]*)$")
TASK_CODE_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class ProjectManifestError(ValueError):
    pass


def normalize_task_code(value: str) -> str:
    value = TASK_CODE_RE.sub("_", value.strip()).strip("._-")
    return value[:120] or "imported_task"


def parse_entry(entry: str) -> tuple[str, str]:
    match = ENTRY_RE.fullmatch(entry.strip())
    if not match:
        raise ProjectManifestError(f"无效入口 {entry!r}，格式必须为 module.path:function_name")
    return match.group("module"), match.group("function")


def task_name_from_entry(module: str, function: str) -> str:
    # 平台内 V2 入口名称使用小写点分命名，保持和 SpiderEntry 校验兼容。
    raw = f"{module}.{function}".lower()
    return re.sub(r"[^a-z0-9_.]+", "_", raw)


def fingerprint(data: dict[str, Any]) -> str:
    source = repr(sorted(data.items())).encode("utf-8", "ignore")
    return hashlib.sha256(source).hexdigest()[:32]


def normalize_project_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Return normalized task descriptors from crawler_project.yml JSON.

    The manifest is a capability declaration, not the production schedule source.
    suggested_trigger is imported only as a disabled/default hint and never
    overwrites existing platform schedules.
    """
    if not manifest:
        return []
    platforms = manifest.get("platforms")
    if not isinstance(platforms, dict):
        raise ProjectManifestError("crawler_project.yml 缺少 platforms 对象")
    result: list[dict[str, Any]] = []
    for platform_code, platform_spec in platforms.items():
        if not isinstance(platform_spec, dict):
            continue
        tasks = platform_spec.get("tasks") or []
        if not isinstance(tasks, list):
            raise ProjectManifestError(f"platforms.{platform_code}.tasks 必须是列表")
        for item in tasks:
            if not isinstance(item, dict):
                raise ProjectManifestError(f"platforms.{platform_code}.tasks 项必须是对象")
            entry = str(item.get("entry", ""))
            module, function = parse_entry(entry)
            code = normalize_task_code(str(item.get("code") or function))
            normalized = {
                "platform": str(platform_code)[:100],
                "task_code": code,
                "task_name": str(item.get("name") or code)[:200],
                "entry_module": module[:300],
                "entry_function": function[:120],
                "spider_task_name": str(item.get("task_name") or task_name_from_entry(module, function))[:200],
                "description": str(item.get("description", ""))[:1000],
                "resources": item.get("resources") if isinstance(item.get("resources"), dict) else {},
                "default_parameters": item.get("default_parameters") if isinstance(item.get("default_parameters"), dict) else {},
                "suggested_trigger": item.get("suggested_trigger") if isinstance(item.get("suggested_trigger"), dict) else {},
                "source_file": str(item.get("source_file") or "crawler_project.yml")[:300],
            }
            normalized["source_fingerprint"] = fingerprint(normalized)
            result.append(normalized)
    return result
