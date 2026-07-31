from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def to_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def api_data(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list | tuple | set):
        return [api_data(item) for item in value]
    if isinstance(value, dict):
        return {to_camel(str(key)): api_data(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return api_data(value.model_dump(by_alias=True))
    if hasattr(value, "__table__"):
        payload: dict[str, Any] = {}
        for column in value.__table__.columns:
            payload[to_camel(column.name)] = api_data(getattr(value, column.name))
        return payload
    return value
