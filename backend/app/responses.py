from __future__ import annotations

from typing import Any

from app.utils import api_data


def ok(data: Any = None, message: str = "success") -> dict[str, Any]:
    return {"code": 200, "message": message, "data": api_data(data)}
