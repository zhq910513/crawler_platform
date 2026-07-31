#!/usr/bin/env python3
"""Parse sch.py static TASKS into crawler_manifest.json.

sch.py remains the local execution file. Online platform only uses TASKS to discover task definitions.
This parser intentionally does not import or execute sch.py. TASKS must be a static Python literal list.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

REQUIRED_TASK_KEYS = {"definitionKey", "taskName", "entryModule", "entryFunction"}


def _normalize_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize_keys(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_keys(item) for item in value]
    return value


def load_tasks(sch_path: Path) -> list[dict]:
    tree = ast.parse(sch_path.read_text(encoding="utf-8"), filename=str(sch_path))
    task_node: ast.AST | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "TASKS":
                    task_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "TASKS":
            task_node = node.value
    if task_node is None:
        raise RuntimeError("sch.py 必须声明静态 TASKS = [...] 任务清单")
    try:
        tasks = ast.literal_eval(task_node)
    except Exception as exc:
        raise RuntimeError("TASKS 必须是纯静态字面量，不能调用函数、读取环境变量或动态生成") from exc
    tasks = _normalize_keys(tasks)
    if not isinstance(tasks, list) or not tasks:
        raise RuntimeError("TASKS 必须是非空列表")
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            raise RuntimeError(f"TASKS 第 {index} 项必须是字典")
        missing = sorted(REQUIRED_TASK_KEYS - set(task))
        if missing:
            raise RuntimeError(f"TASKS 第 {index} 项缺少字段：{', '.join(missing)}")
    return tasks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sch", default="sch.py")
    parser.add_argument("--output", default="crawler_manifest.json")
    parser.add_argument("--project-key", required=True)
    parser.add_argument("--project-code", required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--image-repository", required=True)
    parser.add_argument("--image-digest", required=True)
    parser.add_argument("--release-version", required=True)
    parser.add_argument("--release-channel", default="stable")
    parser.add_argument("--repository-url", default="")
    parser.add_argument("--git-branch", default="")
    parser.add_argument("--git-commit", default="")
    args = parser.parse_args()
    manifest = {
        "manifestVersion": "1",
        "projectKey": args.project_key,
        "projectCode": args.project_code,
        "projectName": args.project_name,
        "repositoryUrl": args.repository_url,
        "imageRepository": args.image_repository,
        "imageDigest": args.image_digest,
        "gitBranch": args.git_branch,
        "gitCommit": args.git_commit,
        "releaseVersion": args.release_version,
        "releaseChannel": args.release_channel,
        "runtimeType": "python",
        "taskDefinitions": load_tasks(Path(args.sch)),
    }
    Path(args.output).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
