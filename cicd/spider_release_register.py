#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Register a crawler project release from Git CI.

Self-contained and stdlib-only.  It reads non-sensitive project ownership from
crawler_project.json, parses crawler_manifest.json or static TASKS in sch.py,
and never imports spider business code.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CODE_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def die(message: str, code: int = 2) -> None:
    print(f"[crawler-platform] {message}", file=sys.stderr)
    raise SystemExit(code)


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def require_env(name: str) -> str:
    value = env(name)
    if not value:
        die(f"缺少环境变量：{name}")
    return value


def read_json_file(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"{path} 不是合法 JSON：{exc}")
    if not isinstance(data, dict):
        die(f"{path} 顶层必须是 JSON 对象")
    return data


def pick(data: dict[str, Any], *names: str, default: str = "") -> str:
    for name in names:
        value = data.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def sanitize_code(value: str) -> str:
    value = CODE_RE.sub("-", value.strip()).strip("-_.")
    return value or "crawler-project"


def repo_name() -> str:
    github_repo = env("GITHUB_REPOSITORY")
    if github_repo and "/" in github_repo:
        return github_repo.rsplit("/", 1)[-1]
    gitlab_project = env("CI_PROJECT_NAME")
    if gitlab_project:
        return gitlab_project
    return Path.cwd().name


def repo_url() -> str:
    return env("GITHUB_SERVER_URL") + "/" + env("GITHUB_REPOSITORY") if env("GITHUB_SERVER_URL") and env("GITHUB_REPOSITORY") else env("CI_PROJECT_URL", env("REPOSITORY_URL"))


def git_branch() -> str:
    return env("GITHUB_REF_NAME", env("CI_COMMIT_REF_NAME", env("GIT_BRANCH")))


def git_commit() -> str:
    return env("GITHUB_SHA", env("CI_COMMIT_SHA", env("GIT_COMMIT")))


def release_version() -> str:
    raw = env("RELEASE_VERSION")
    if raw:
        return raw[1:] if raw.startswith("v") and SEMVER_RE.match(raw[1:]) else raw
    ref_name = git_branch()
    if ref_name.startswith("v") and SEMVER_RE.match(ref_name[1:]):
        return ref_name[1:]
    if SEMVER_RE.match(ref_name):
        return ref_name
    version_file = Path("VERSION")
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip().lstrip("v")
    die("无法确定 releaseVersion：请提供 RELEASE_VERSION、打 vX.Y.Z tag，或在仓库根目录放 VERSION 文件")


def normalize_digest(value: str) -> str:
    value = value.strip()
    if "@" in value:
        value = value.rsplit("@", 1)[-1]
    if not DIGEST_RE.match(value):
        die("IMAGE_DIGEST 必须是 sha256: 后接 64 位小写十六进制，禁止使用 latest/tag")
    return value


def default_image_repository(project_code: str) -> str:
    configured = env("IMAGE_REPOSITORY") or env("CRAWLER_IMAGE_REPOSITORY")
    if configured:
        return configured.rstrip(":")
    registry_host = env("CRAWLER_REGISTRY_HOST", env("CRAWLER_PLATFORM_REGISTRY_HOST", env("REGISTRY_HOST", "ghcr.io"))).rstrip("/")
    namespace = env("CRAWLER_REGISTRY_NAMESPACE", env("CRAWLER_PLATFORM_REGISTRY_NAMESPACE", env("REGISTRY_NAMESPACE")))
    if not namespace and env("GITHUB_REPOSITORY_OWNER"):
        namespace = env("GITHUB_REPOSITORY_OWNER")
    if not namespace and env("CI_PROJECT_NAMESPACE"):
        namespace = env("CI_PROJECT_NAMESPACE")
    if not namespace:
        die("无法推导 IMAGE_REPOSITORY：请设置 CRAWLER_REGISTRY_NAMESPACE 或 IMAGE_REPOSITORY")
    return f"{registry_host}/{namespace.strip('/')}/{project_code}".lower()


def literal_task_items_from_sch(path: Path) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        die(f"sch.py 语法错误，无法解析 TASKS：{exc}")
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "TASKS" for t in node.targets):
                value = ast.literal_eval(node.value)
                if not isinstance(value, list):
                    die("sch.py 中 TASKS 必须是 list[dict] 静态字面量")
                return value
    die("未在 sch.py 中找到静态 TASKS = [...] 定义")


def normalize_task(item: dict[str, Any], idx: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        die(f"TASKS[{idx}] 不是 dict")
    definition_key = str(item.get("definitionKey") or item.get("definition_key") or item.get("taskCode") or item.get("task_code") or "").strip()
    task_name = str(item.get("taskName") or item.get("task_name") or definition_key).strip()
    entry_module = str(item.get("entryModule") or item.get("entry_module") or "").strip()
    entry_function = str(item.get("entryFunction") or item.get("entry_function") or "").strip()
    if not definition_key or not task_name or not entry_module or not entry_function:
        die(f"TASKS[{idx}] 缺少 definitionKey/taskName/entryModule/entryFunction")
    return {
        "definitionKey": definition_key,
        "taskName": task_name,
        "entryModule": entry_module,
        "entryFunction": entry_function,
        "defaultParams": item.get("defaultParams") or item.get("default_params") or {},
        "suggestedCron": str(item.get("suggestedCron") or item.get("suggested_cron") or ""),
        "executionMode": item.get("executionMode") or item.get("execution_mode") or "SINGLE",
        "idempotencyPolicy": item.get("idempotencyPolicy") or item.get("idempotency_policy") or "IDEMPOTENT",
        "runtimeMode": item.get("runtimeMode") or item.get("runtime_mode") or "SHARED_ENV_ISOLATED",
        "taskGroup": item.get("taskGroup") or item.get("task_group") or "default",
        "taskMaxConcurrency": int(item.get("taskMaxConcurrency") or item.get("task_max_concurrency") or 1),
        "groupMaxConcurrency": int(item.get("groupMaxConcurrency") or item.get("group_max_concurrency") or 4),
        "exclusiveMode": bool(item.get("exclusiveMode") or item.get("exclusive_mode") or False),
        "ioClass": item.get("ioClass") or item.get("io_class") or "NORMAL",
        "shmSizeMb": int(item.get("shmSizeMb") or item.get("shm_size_mb") or 64),
        "logLimitMb": int(item.get("logLimitMb") or item.get("log_limit_mb") or 50),
        "resourceLocks": item.get("resourceLocks") or item.get("resource_locks") or [],
        "resourceRequirements": item.get("resourceRequirements") or item.get("resource_requirements") or {},
        "requiredCapabilities": item.get("requiredCapabilities") or item.get("required_capabilities") or {},
        "platformCode": item.get("platformCode") or item.get("platform_code") or "",
        "requiredConfigs": item.get("requiredConfigs") or item.get("required_configs") or [],
        "requiredCredentials": item.get("requiredCredentials") or item.get("required_credentials") or [],
        "outputTables": item.get("outputTables") or item.get("output_tables") or [],
        "sourceFile": item.get("sourceFile") or item.get("source_file") or "sch.py",
    }


def load_task_definitions() -> list[dict[str, Any]]:
    manifest_path = Path("crawler_manifest.json")
    if manifest_path.exists():
        manifest = read_json_file("crawler_manifest.json")
        items = manifest.get("taskDefinitions") or manifest.get("task_definitions") or []
    else:
        project_meta = read_json_file("crawler_project.json")
        items = project_meta.get("taskDefinitions") or project_meta.get("task_definitions") or []
        if not items:
            sch_path = Path(env("SCH_FILE", "sch.py"))
            if not sch_path.exists():
                die("缺少 crawler_manifest.json、crawler_project.json.taskDefinitions 或 sch.py，无法生成任务定义")
            items = literal_task_items_from_sch(sch_path)
    tasks = [normalize_task(item, idx) for idx, item in enumerate(items, start=1)]
    seen: set[str] = set()
    for task in tasks:
        key = task["definitionKey"]
        if key in seen:
            die(f"任务 definitionKey 重复：{key}")
        seen.add(key)
    if not tasks:
        die("任务定义为空")
    return tasks


def platform_api_url() -> str:
    base = env("CRAWLER_CONTROL_BASE_URL") or env("CONTROL_PLANE_URL") or env("CRAWLER_PLATFORM_URL") or env("PLATFORM_URL")
    if not base:
        die("缺少控制端回调地址：请使用平台 CI一键初始化 生成的 workflow，或设置 CRAWLER_CONTROL_BASE_URL")
    base = base.rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        die("CRAWLER_CONTROL_BASE_URL 必须是 http(s) URL")
    if base.endswith("/api/v1"):
        return base
    if base.endswith("/api"):
        return base + "/v1"
    return base + "/api/v1"


def project_meta() -> dict[str, Any]:
    meta = read_json_file("crawler_project.json")
    if not meta:
        meta = read_json_file("crawler_manifest.json")
    return meta


def build_payload() -> dict[str, Any]:
    meta = project_meta()
    project_code = sanitize_code(env("PROJECT_CODE", env("CRAWLER_PROJECT_CODE", pick(meta, "projectCode", "project_code", default=repo_name()))))
    project_key = env("PROJECT_KEY", env("CRAWLER_PROJECT_KEY", pick(meta, "projectKey", "project_key", default=project_code)))
    project_name = env("PROJECT_NAME", env("CRAWLER_PROJECT_NAME", pick(meta, "projectName", "project_name", default=project_code)))
    company_code = env("CRAWLER_COMPANY_CODE", env("COMPANY_CODE", pick(meta, "companyCode", "company_code")))
    version = release_version()
    if not SEMVER_RE.match(version):
        die("releaseVersion 必须是 X.Y.Z，不允许 main/dev/latest")
    digest = normalize_digest(require_env("IMAGE_DIGEST"))
    image_repository = default_image_repository(project_code)
    company_value = env("CRAWLER_PLATFORM_COMPANY_ID") or env("PLATFORM_COMPANY_ID")
    server_codes = [item.strip() for item in env("SERVER_CODES", env("CRAWLER_SERVER_CODES", pick(meta, "serverCodes", "server_codes"))).split(",") if item.strip()]
    manifest = {
        "manifestVersion": "1",
        "companyCode": company_code,
        "projectKey": project_key,
        "projectName": project_name,
        "projectCode": project_code,
        "repositoryUrl": repo_url(),
        "imageRepository": image_repository,
        "imageDigest": digest,
        "gitBranch": git_branch(),
        "gitCommit": git_commit(),
        "releaseVersion": version,
        "releaseChannel": env("RELEASE_CHANNEL", env("CRAWLER_RELEASE_CHANNEL", env("CRAWLER_PLATFORM_RELEASE_CHANNEL", pick(meta, "releaseChannel", "release_channel", default="stable")))),
        "runtimeType": env("RUNTIME_TYPE", pick(meta, "runtimeType", "runtime_type", default="python")),
        "supportedArch": env("SUPPORTED_ARCH", pick(meta, "supportedArch", "supported_arch", default="linux/amd64")),
        "requiredCapabilities": meta.get("requiredCapabilities") or meta.get("required_capabilities") or {},
        "taskDefinitions": load_task_definitions(),
    }
    if not company_value and not company_code:
        die("缺少项目归属：请在 crawler_project.json 写 companyCode，或设置 CRAWLER_PLATFORM_COMPANY_ID")
    payload: dict[str, Any] = {"serverCodes": server_codes, "manifest": manifest}
    if company_value:
        if not company_value.isdigit():
            die("CRAWLER_PLATFORM_COMPANY_ID / PLATFORM_COMPANY_ID 必须是数字")
        payload["companyId"] = int(company_value)
    return payload


def post_release(payload: dict[str, Any]) -> dict[str, Any]:
    token = env("CRAWLER_PLATFORM_DISCOVERY_TOKEN") or env("PLATFORM_DISCOVERY_TOKEN")
    if not token:
        die("缺少环境变量：CRAWLER_PLATFORM_DISCOVERY_TOKEN 或 PLATFORM_DISCOVERY_TOKEN")
    url = platform_api_url() + "/discovered-projects"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, method="POST", headers={"Content-Type": "application/json", "Authorization": "Discovery " + token})
    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        die(f"平台注册 release 失败 HTTP {exc.code}: {body}", 1)
    except URLError as exc:
        die(f"无法访问爬虫平台：{exc}", 1)


def main() -> None:
    payload = build_payload()
    print("[crawler-platform] register release", payload["manifest"]["projectCode"], payload["manifest"]["releaseVersion"], payload["manifest"]["imageDigest"])
    result = post_release(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
