from __future__ import annotations

import fcntl
import os
import platform
import shutil
import socket
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import docker
import psutil

from crawler_agent.api import PlatformAPI, PlatformUnavailable, UnauthorizedError
from crawler_agent.config import config
from crawler_agent.docker_runner import RunExecutor
from crawler_agent.spool import RunSpool



def acquire_process_lock():
    lock_path = config.run_root.parent / "agent.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError(f"another crawler-agent process is already running: {lock_path}") from exc
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


class AgentApp:
    def __init__(self) -> None:
        self.api = PlatformAPI(config)
        self.executor = RunExecutor(config, self.api)
        self.pool = ThreadPoolExecutor(max_workers=config.max_slots, thread_name_prefix="crawler-run")
        self.futures: dict[int, Future] = {}
        self.lock = threading.Lock()
        self.docker_client = docker.from_env()
        config.run_root.mkdir(parents=True, exist_ok=True)

    def register(self) -> None:
        docker_version = ""
        try:
            docker_version = str(self.docker_client.version().get("Version", ""))
        except Exception:
            pass
        self.api.register({
            "protocol_version": "2.0",
            "company_id": config.company_id or None,
            "instance_id": config.instance_id,
            "agent_code": config.agent_code,
            "server_code": config.server_code,
            "server_name": config.server_name,
            "hostname": socket.gethostname(),
            "agent_version": config.agent_version,
            "os_name": platform.platform(),
            "python_version": sys.version.split()[0],
            "docker_version": docker_version,
            "cpu_count": psutil.cpu_count() or 0,
            "memory_total_bytes": psutil.virtual_memory().total,
            "capabilities": config.capabilities,
            "labels": config.labels,
            "max_container_slots": config.max_slots,
        })
        print(f"Agent registered id={self.api.agent_id} server={self.api.server_id}", flush=True)

    def _active_count(self) -> int:
        with self.lock:
            done = [run_id for run_id, future in self.futures.items() if future.done()]
            for run_id in done:
                future = self.futures.pop(run_id)
                try:
                    future.result()
                except Exception as exc:
                    print(f"run worker failed run={run_id}: {exc!r}", flush=True)
            return len(self.futures)

    def _submit(self, spool: RunSpool, recover: bool) -> None:
        run_id = spool.run_id
        with self.lock:
            if run_id in self.futures:
                return
            self.futures[run_id] = self.pool.submit(self.executor.execute, spool, recover)

    def recover(self) -> None:
        for child in config.run_root.iterdir():
            if not child.is_dir() or not child.name.isdigit():
                continue
            spool = RunSpool(config.run_root, int(child.name), config.container_uid, config.container_gid)
            state = spool.state()
            phase = state.get("phase", "")
            if phase in {"PREPARED", "WAITING_PLATFORM"}:
                self._submit(spool, recover=False)
            elif phase == "STARTING":
                # 容器已创建后 Agent 可能在 started 确认前崩溃。存在 container_id
                # 时必须接管原容器，不能再次创建造成重复抓取和重复入库。
                self._submit(spool, recover=bool(state.get("container_id")))
            elif phase == "RUNNING":
                self._submit(spool, recover=True)
            elif phase == "FINISHED_PENDING_UPLOAD":
                try:
                    self.executor.flush_all(spool, 30)
                except Exception:
                    pass

    def heartbeat_payload(self) -> dict[str, Any]:
        disk = psutil.disk_usage(str(config.run_root))
        net = psutil.net_io_counters()
        load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
        running = self._active_count()
        return {
            "instance_id": config.instance_id,
            "status": "ONLINE",
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": disk.percent,
            "load_1m": load[0],
            "load_5m": load[1],
            "network_sent_bytes": net.bytes_sent,
            "network_received_bytes": net.bytes_recv,
            "running_task_count": running,
            "process_count": len(psutil.pids()),
            "docker_image_bytes": 0,
            "available_slots": max(0, config.max_slots - running),
            "last_error": "",
        }

    def cleanup(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=config.completed_retention_hours)
        for child in config.run_root.iterdir():
            if not child.is_dir() or not child.name.isdigit():
                continue
            spool = RunSpool(config.run_root, int(child.name), config.container_uid, config.container_gid)
            state = spool.state()
            if state.get("phase") != "COMPLETED":
                continue
            completed = state.get("completed_at")
            try:
                completed_at = datetime.fromisoformat(str(completed).replace("Z", "+00:00"))
            except Exception:
                continue
            if completed_at < cutoff:
                shutil.rmtree(child, ignore_errors=True)

    def run_forever(self) -> None:
        while True:
            try:
                self.register()
                break
            except Exception as exc:
                print(f"Agent register failed: {exc}", flush=True)
                time.sleep(5)
        self.recover()
        last_heartbeat = 0.0
        last_recovery = 0.0
        last_cleanup = 0.0
        while True:
            now = time.monotonic()
            try:
                if now - last_heartbeat >= config.heartbeat_seconds:
                    self.api.heartbeat(self.heartbeat_payload())
                    last_heartbeat = now
                if now - last_recovery >= config.recovery_scan_seconds:
                    self.recover()
                    last_recovery = now
                active = self._active_count()
                available = max(0, config.max_slots - active)
                if available:
                    for claim in self.api.claim(available):
                        spool = RunSpool.prepare(config.run_root, claim, config.container_uid, config.container_gid)
                        self._submit(spool, recover=False)
                if now - last_cleanup >= 3600:
                    self.cleanup()
                    last_cleanup = now
            except UnauthorizedError:
                self.api.agent_token = ""
                while True:
                    try:
                        self.register()
                        break
                    except Exception as exc:
                        print(f"Agent re-register failed: {exc}", flush=True)
                        time.sleep(5)
            except PlatformUnavailable as exc:
                print(f"Platform unavailable: {exc}", flush=True)
            except Exception as exc:
                print(f"Agent loop error: {exc!r}", flush=True)
            time.sleep(config.claim_seconds)


def main() -> None:
    config.validate()
    lock_handle = acquire_process_lock()
    try:
        AgentApp().run_forever()
    finally:
        lock_handle.close()


if __name__ == "__main__":
    main()
