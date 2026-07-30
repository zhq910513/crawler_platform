from __future__ import annotations

import asyncio
import os
import threading
from collections import defaultdict
from pathlib import Path
from typing import AsyncIterator

from app.config import settings

_locks: defaultdict[int, threading.Lock] = defaultdict(threading.Lock)


def build_log_path(task_id: int, run_no: str, date_part: str) -> Path:
    safe_run_no = "".join(ch for ch in run_no if ch.isalnum() or ch in "-_")
    return settings.task_log_root / date_part / f"task_{task_id}" / f"run_{safe_run_no}.log"


async def append_lines(run_id: int, path: Path, lines: list[str]) -> tuple[int, int]:
    if not lines:
        size = path.stat().st_size if path.exists() else 0
        return size, 0
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(line if line.endswith("\n") else f"{line}\n" for line in lines)
    await asyncio.to_thread(_append_text, run_id, path, text)
    return path.stat().st_size, len(lines)


def _append_text(run_id: int, path: Path, text: str) -> None:
    with _locks[run_id]:
        with path.open("a", encoding="utf-8", errors="replace") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())


def read_tail(path: Path, max_bytes: int = 512 * 1024) -> tuple[str, int]:
    if not path.exists():
        return "", 0
    with path.open("rb") as file:
        file.seek(0, os.SEEK_END)
        size = file.tell()
        start = max(0, size - max_bytes)
        file.seek(start)
        data = file.read()
    if start:
        newline = data.find(b"\n")
        if newline >= 0:
            start += newline + 1
            data = data[newline + 1:]
    return data.decode("utf-8", errors="replace"), start + len(data)


async def stream_file_from_offset(path: Path, offset: int = 0, poll_seconds: float = 0.5) -> AsyncIterator[tuple[int, str]]:
    position = max(0, offset)
    buffer = b""
    while True:
        if path.exists():
            size = path.stat().st_size
            if position > size:
                position = 0
                buffer = b""
            with path.open("rb") as file:
                file.seek(position)
                chunk = file.read(128 * 1024)
            if chunk:
                position += len(chunk)
                buffer += chunk
                while b"\n" in buffer:
                    raw, buffer = buffer.split(b"\n", 1)
                    line_end = position - len(buffer)
                    yield line_end, raw.decode("utf-8", errors="replace")
                continue
        await asyncio.sleep(poll_seconds)
