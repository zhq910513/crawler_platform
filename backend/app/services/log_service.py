from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from pathlib import Path
from typing import AsyncIterator

from app.config import settings

_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def build_log_path(task_id: int, run_no: str, date_part: str) -> Path:
    safe_run_no = "".join(ch for ch in run_no if ch.isalnum() or ch in "-_")
    return settings.task_log_root / date_part / f"task_{task_id}" / f"run_{safe_run_no}.log"


async def append_lines(run_id: int, path: Path, lines: list[str]) -> tuple[int, int]:
    if not lines:
        size = path.stat().st_size if path.exists() else 0
        return size, 0
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(line if line.endswith("\n") else f"{line}\n" for line in lines)
    async with _locks[run_id]:
        await asyncio.to_thread(_append_text, path, text)
        size = path.stat().st_size
    return size, len(lines)


def _append_text(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8", errors="replace") as file:
        file.write(text)
        file.flush()


def read_tail(path: Path, max_bytes: int = 512 * 1024) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as file:
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(max(0, size - max_bytes), os.SEEK_SET)
        data = file.read()
    return data.decode("utf-8", errors="replace")


async def stream_file(path: Path, poll_seconds: float = 1.0) -> AsyncIterator[str]:
    position = 0
    idle_count = 0
    while True:
        if path.exists():
            with path.open("r", encoding="utf-8", errors="replace") as file:
                file.seek(position)
                chunk = file.read()
                position = file.tell()
            if chunk:
                idle_count = 0
                for line in chunk.splitlines():
                    yield f"data: {line}\n\n"
            else:
                idle_count += 1
        else:
            idle_count += 1
        yield ": keepalive\n\n"
        await asyncio.sleep(poll_seconds)
        if idle_count > 3600:
            return
