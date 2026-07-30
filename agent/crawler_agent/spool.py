from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: Any, mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, separators=(",", ":"), default=str)
        file.flush()
        os.fsync(file.fileno())
    os.chmod(temp, mode)
    os.replace(temp, path)


def read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, ValueError, TypeError):
        return default


def _last_seq(path: Path, key: str = "seq") -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0
    with path.open("rb") as file:
        file.seek(0, os.SEEK_END)
        pos = file.tell() - 1
        # 跳过文件尾部换行，再反向定位最后一条完整 NDJSON。
        while pos >= 0:
            file.seek(pos)
            if file.read(1) not in {b"\n", b"\r"}:
                break
            pos -= 1
        if pos < 0:
            return 0
        line_end = pos + 1
        while pos >= 0:
            file.seek(pos)
            if file.read(1) == b"\n":
                break
            pos -= 1
        file.seek(pos + 1)
        raw = file.read(line_end - pos - 1)
    try:
        return int(json.loads(raw.decode("utf-8"))[key])
    except Exception:
        return 0



class RunSpool:
    def __init__(self, root: Path, run_id: int, uid: int = 10001, gid: int = 10001) -> None:
        self.run_id = run_id
        self.path = root / str(run_id)
        self.path.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path, 0o750)
        self.uid = uid
        self.gid = gid
        self.lock = threading.RLock()
        self.stdout_path = self.path / "stdout.ndjson"
        self.stderr_path = self.path / "stderr.ndjson"
        self.events_path = self.path / "events.ndjson"
        self.upload_path = self.path / "upload.state.json"
        self.agent_state_path = self.path / "agent-state.json"
        self.next_seq = {
            "stdout": _last_seq(self.stdout_path) + 1,
            "stderr": _last_seq(self.stderr_path) + 1,
            "events": _last_seq(self.events_path, "local_seq") + 1,
        }
        if not self.upload_path.exists():
            self.save_upload_state({
                "stdout": {"offset": 0, "ack_seq": 0},
                "stderr": {"offset": 0, "ack_seq": 0},
                "events": {"offset": 0, "ack_local_seq": 0},
                "finish_uploaded": False,
            })

    @classmethod
    def prepare(cls, root: Path, claim: dict[str, Any], uid: int, gid: int) -> "RunSpool":
        spool = cls(root, int(claim["run_id"]), uid, gid)
        atomic_json(spool.path / "task.json", claim["files"]["task"])
        atomic_json(spool.path / "resources.json", claim["files"]["resources"])
        atomic_json(spool.path / "secrets.json", claim["files"]["secrets"], 0o600)
        execution = {key: value for key, value in claim.items() if key != "files"}
        atomic_json(spool.path / "execution.json", execution, 0o600)
        spool.set_phase("PREPARED")
        spool._set_container_permissions()
        return spool

    def _set_container_permissions(self) -> None:
        try:
            os.chown(self.path, self.uid, self.gid)
            for name in ("task.json", "resources.json", "secrets.json"):
                path = self.path / name
                if path.exists():
                    os.chown(path, self.uid, self.gid)
            os.chmod(self.path / "task.json", 0o640)
            os.chmod(self.path / "resources.json", 0o640)
            os.chmod(self.path / "secrets.json", 0o600)
        except PermissionError:
            # 非 root 本地开发模式允许跳过 chown；Docker 生产部署应以 root 运行 Agent。
            pass

    def execution(self) -> dict[str, Any]:
        return read_json(self.path / "execution.json", {})

    def state(self) -> dict[str, Any]:
        return read_json(self.agent_state_path, {})

    def set_phase(self, phase: str, **values: Any) -> None:
        with self.lock:
            state = self.state()
            state.update(values)
            state["phase"] = phase
            state["updated_at"] = _now()
            atomic_json(self.agent_state_path, state)

    def append_log(self, stream: str, line: str) -> tuple[int, dict[str, Any]]:
        path = self.stdout_path if stream == "stdout" else self.stderr_path
        with self.lock:
            seq = self.next_seq[stream]
            self.next_seq[stream] += 1
            record = {"seq": seq, "collected_at": _now(), "line": line}
            with path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                file.flush()
            return seq, record

    def append_event(self, event: dict[str, Any]) -> int:
        with self.lock:
            seq = self.next_seq["events"]
            self.next_seq["events"] += 1
            record = {"local_seq": seq, "collected_at": _now(), "event": event}
            with self.events_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str) + "\n")
                file.flush()
            return seq

    def upload_state(self) -> dict[str, Any]:
        return read_json(self.upload_path, {
            "stdout": {"offset": 0, "ack_seq": 0},
            "stderr": {"offset": 0, "ack_seq": 0},
            "events": {"offset": 0, "ack_local_seq": 0},
            "finish_uploaded": False,
        })

    def save_upload_state(self, state: dict[str, Any]) -> None:
        atomic_json(self.upload_path, state)

    def read_records(self, path: Path, offset: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        if not path.exists():
            return [], offset
        records: list[dict[str, Any]] = []
        next_offset = offset
        with path.open("rb") as file:
            file.seek(offset)
            while len(records) < limit:
                raw = file.readline()
                if not raw:
                    break
                next_offset = file.tell()
                try:
                    records.append(json.loads(raw.decode("utf-8")))
                except (ValueError, UnicodeDecodeError):
                    continue
        return records, next_offset

    def write_finish(self, payload: dict[str, Any]) -> None:
        atomic_json(self.path / "finish.json", payload)
        self.set_phase("FINISHED_PENDING_UPLOAD", finished_at=_now())

    def finish_payload(self) -> dict[str, Any] | None:
        value = read_json(self.path / "finish.json", None)
        return value if isinstance(value, dict) else None

    def mark_completed(self) -> None:
        self.set_phase("COMPLETED", completed_at=_now())
