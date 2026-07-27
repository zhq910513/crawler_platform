from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import json
import sys
import traceback
from typing import Any, Callable


def resolve_callable(entrypoint: str) -> Callable[..., Any]:
    value = entrypoint.strip()
    if ":" in value:
        module_name, attr_path = value.split(":", 1)
    else:
        module_name, _, attr_path = value.rpartition(".")
    if not module_name or not attr_path:
        raise ValueError("entrypoint 必须为 package.module:function 或 package.module.function")
    target: Any = importlib.import_module(module_name)
    for attr in attr_path.split("."):
        target = getattr(target, attr)
    if not callable(target):
        raise TypeError(f"目标对象不可调用：{entrypoint}")
    return target


def parse_json(value: str, expected_type: type) -> Any:
    result = json.loads(value)
    if not isinstance(result, expected_type):
        raise TypeError(f"参数必须解析为 {expected_type.__name__}")
    return result


def emit_result(result: Any) -> None:
    if result is None:
        return
    try:
        print(json.dumps({"runtime_result": result}, ensure_ascii=False, default=str), flush=True)
    except Exception:
        print(f"runtime_result={result!r}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawler Runtime Method Runner")
    parser.add_argument("--entrypoint", required=True)
    parser.add_argument("--args-json", default="[]")
    parser.add_argument("--kwargs-json", default="{}")
    args = parser.parse_args()

    try:
        positional = parse_json(args.args_json, list)
        keyword = parse_json(args.kwargs_json, dict)
        target = resolve_callable(args.entrypoint)
        result = target(*positional, **keyword)
        if inspect.isawaitable(result):
            result = asyncio.run(result)
        emit_result(result)
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
