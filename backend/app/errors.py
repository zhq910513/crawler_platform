from __future__ import annotations

from typing import Any

from fastapi import status


class AppError(Exception):
    def __init__(self, message: str, code: int = 40000, http_status: int = status.HTTP_400_BAD_REQUEST, data: Any = None):
        self.message = message
        self.code = code
        self.http_status = http_status
        self.data = data
        super().__init__(message)
