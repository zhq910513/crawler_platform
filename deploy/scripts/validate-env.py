#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else ".env")
    if not path.is_file():
        print(f"配置文件不存在：{path}", file=sys.stderr)
        return 2
    env = load_dotenv(path)
    required = {
        "MYSQL_ROOT_PASSWORD": 16,
        "MYSQL_PASSWORD": 16,
        "DATABASE_URL": 20,
        "REDIS_PASSWORD": 16,
        "REDIS_URL": 15,
        "JWT_SECRET": 32,
        "SECRET_ENCRYPTION_KEY": 32,
        "ADMIN_PASSWORD": 12,
        "CICD_TOKEN": 24,
        "AGENT_BOOTSTRAP_TOKEN": 24,
    }
    errors: list[str] = []
    for key, minimum in required.items():
        value = env.get(key, "")
        lowered = value.lower()
        if len(value) < minimum or "replacewith" in lowered or "change-this" in lowered:
            errors.append(f"{key} 未设置为足够强的生产值")
    if env.get("APP_ENV", "production").lower() not in {"production", "prod"}:
        errors.append("APP_ENV 生产部署必须为 production")
    if env.get("CORS_ORIGINS") == "*":
        errors.append("CORS_ORIGINS 不应使用 *，同源部署请留空")
    if errors:
        print("配置检查失败：", file=sys.stderr)
        for item in errors:
            print(f"- {item}", file=sys.stderr)
        return 2
    print("配置检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
