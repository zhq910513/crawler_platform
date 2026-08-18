#!/usr/bin/env python3
"""Offline frontend package-lock sanity checks for release builds.

This guard catches deterministic lockfile mistakes before Docker build spends time
pulling images and running npm ci. It is intentionally offline: registry outages
are still handled by the Dockerfile registry fallback, while impossible lockfile
entries should be rejected from source control.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "frontend" / "package-lock.json"
PACKAGE_JSON_PATH = ROOT / "frontend" / "package.json"

# Incident-derived denylist. Keep this small and explicit: these versions were
# proven to be referenced by our lockfile but unavailable from both npmmirror and
# the official npm registry during the commercial release gate.
KNOWN_UNPUBLISHED = {
    ("picocolors", "1.1.2"),
}


def fail(message: str, failures: list[str]) -> None:
    failures.append(message)


def parse_version(value: str) -> tuple[int, int, int] | None:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$", value or "")
    if not m:
        return None
    return tuple(int(part) for part in m.groups())  # type: ignore[return-value]


def satisfies_simple_range(version: str, requirement: str) -> bool | None:
    """Return None for unsupported npm range syntax."""
    req = (requirement or "").strip()
    ver = parse_version(version)
    if not req or req in {"*", "latest"} or ver is None:
        return None
    if req.startswith("^"):
        base = parse_version(req[1:])
        if base is None:
            return None
        if base[0] > 0:
            return ver[0] == base[0] and ver >= base
        if base[1] > 0:
            return ver[0] == 0 and ver[1] == base[1] and ver >= base
        return ver[0] == 0 and ver[1] == 0 and ver[2] == base[2]
    if req.startswith("~"):
        base = parse_version(req[1:])
        if base is None:
            return None
        return ver[0] == base[0] and ver[1] == base[1] and ver >= base
    if re.match(r"^\d+\.\d+\.\d+", req):
        base = parse_version(req)
        return base == ver if base is not None else None
    return None


def package_name_from_path(package_path: str) -> str | None:
    prefix = "node_modules/"
    if not package_path.startswith(prefix):
        return None
    parts = package_path.split("node_modules/")
    last = parts[-1]
    bits = last.split("/")
    if not bits:
        return None
    if bits[0].startswith("@") and len(bits) >= 2:
        return f"{bits[0]}/{bits[1]}"
    return bits[0]


def expected_tarball_basename(package_name: str, version: str) -> str:
    short_name = package_name.split("/")[-1]
    return f"{short_name}-{version}.tgz"


def main() -> int:
    failures: list[str] = []
    if not LOCK_PATH.exists():
        print(f"FAIL: 缺少 {LOCK_PATH.relative_to(ROOT)}", file=sys.stderr)
        return 1

    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    package_json = json.loads(PACKAGE_JSON_PATH.read_text(encoding="utf-8")) if PACKAGE_JSON_PATH.exists() else {}
    packages = lock.get("packages") or {}
    root_package = packages.get("") or {}

    source = LOCK_PATH.read_text(encoding="utf-8")
    for forbidden in ("registry.npmmirror.com", "cdn.npmmirror.com"):
        if forbidden in source:
            fail(f"package-lock.json 不允许固化 {forbidden}；镜像源只能由 Docker build 参数控制。", failures)

    if package_json.get("version") and root_package.get("version") and package_json["version"] != root_package["version"]:
        fail(
            f"frontend/package.json version={package_json['version']} 与 package-lock 根版本={root_package['version']} 不一致。",
            failures,
        )

    by_name: dict[str, dict] = {}
    for path, meta in packages.items():
        if not path:
            continue
        if not isinstance(meta, dict):
            continue
        name = package_name_from_path(path)
        version = str(meta.get("version") or "")
        if not name or not version:
            continue
        by_name.setdefault(name, meta)
        if (name, version) in KNOWN_UNPUBLISHED:
            fail(f"package-lock.json 引用了已知不可发布/不可下载版本：{name}@{version}。", failures)
        resolved = str(meta.get("resolved") or "")
        if resolved.startswith("http"):
            parsed = urlparse(resolved)
            basename = unquote(Path(parsed.path).name)
            if not name.startswith("@"):
                expected = expected_tarball_basename(name, version)
                if basename != expected:
                    fail(f"{name}@{version} resolved 文件名不匹配：{basename}，期望 {expected}。", failures)
            if parsed.netloc not in {"registry.npmjs.org"}:
                fail(f"{name}@{version} resolved 必须使用 registry.npmjs.org，当前为 {parsed.netloc}。", failures)

    for path, meta in packages.items():
        if not path or not isinstance(meta, dict):
            continue
        package_name = package_name_from_path(path) or path
        dependencies = meta.get("dependencies") or {}
        if not isinstance(dependencies, dict):
            continue
        for dep_name, requirement in dependencies.items():
            dep_meta = by_name.get(dep_name)
            if not dep_meta:
                continue
            dep_version = str(dep_meta.get("version") or "")
            ok = satisfies_simple_range(dep_version, str(requirement))
            if ok is False:
                fail(
                    f"{package_name} 依赖 {dep_name}{requirement}，但 lockfile 锁定为 {dep_version}，不满足约束。",
                    failures,
                )

    if failures:
        print("前端 package-lock 完整性检查失败：", file=sys.stderr)
        for item in failures:
            print(f"- {item}", file=sys.stderr)
        return 1

    print("前端 package-lock 完整性检查通过：resolved 源、已知不可下载版本和简单依赖约束均符合要求。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
