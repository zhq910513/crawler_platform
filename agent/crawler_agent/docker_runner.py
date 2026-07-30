from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import docker
from docker.errors import ImageNotFound, NotFound

from crawler_agent.api import LeaseLostError, PlatformAPI, PlatformUnavailable, UnauthorizedError
from crawler_agent.config import AgentConfig
from crawler_agent.spool import RunSpool, read_json


class LeaseKeeper:
    def __init__(self, api: PlatformAPI, run_id: int, lease: str, interval: int) -> None:
        self.api = api
        self.run_id = run_id
        self.lease = lease
        self.interval = interval
        self.stop_event = threading.Event()
        self.cancel_action = ""
        self.lease_lost = False
        self.container_id = ""
        self.last_success = time.monotonic()
        self.max_silence_seconds = max(int(api.lease_seconds), interval * 2)
        self.thread = threading.Thread(target=self._loop, daemon=True, name=f"lease-{run_id}")

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)

    def _loop(self) -> None:
        while not self.stop_event.wait(self.interval):
            try:
                result = self.api.run_heartbeat(self.run_id, self.lease, self.container_id)
                self.last_success = time.monotonic()
                action = result.get("desired_action", "NONE")
                if action in {"STOP", "TIMEOUT_STOP"}:
                    self.cancel_action = action
            except LeaseLostError:
                self.lease_lost = True
                self.cancel_action = "STOP"
                return
            except (PlatformUnavailable, UnauthorizedError):
                # 短暂断网不影响任务；但超过租约有效期仍继续执行会与平台重试容器
                # 并行，造成重复入库。达到上限后主动停止本地容器。
                if time.monotonic() - self.last_success >= self.max_silence_seconds:
                    self.lease_lost = True
                    self.cancel_action = "STOP"
                    return
                continue


class ContainerStopper:
    """Stop a running container as soon as platform control requests cancellation.

    Docker log attachment is blocking when a crawler is quiet, so cancellation cannot
    depend on the next log line arriving. This tiny monitor is per TaskRun and exits
    immediately after the container stops or the executor completes.
    """

    def __init__(self, keeper: LeaseKeeper, container: Any, grace_seconds: int) -> None:
        self.keeper = keeper
        self.container = container
        self.grace_seconds = max(1, grace_seconds)
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True, name=f"stop-{keeper.run_id}")

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.done.set()
        self.thread.join(timeout=2)

    def _loop(self) -> None:
        while not self.done.wait(0.2):
            if not self.keeper.cancel_action:
                continue
            try:
                self.container.stop(timeout=self.grace_seconds)
            except Exception:
                try:
                    self.container.kill()
                except Exception:
                    pass
            return


class RunExecutor:
    def __init__(self, config: AgentConfig, api: PlatformAPI) -> None:
        self.config = config
        self.api = api
        self.client = docker.from_env()

    def _pull_image(self, image_ref: str) -> None:
        auth_config = None
        if self.config.registry_username and self.config.registry_password:
            auth_config = {"username": self.config.registry_username, "password": self.config.registry_password}
        self.client.images.pull(image_ref, auth_config=auth_config)

    def _ensure_image(self, image_ref: str, policy: str) -> None:
        if policy == "ALWAYS":
            self._pull_image(image_ref)
            return
        try:
            self.client.images.get(image_ref)
        except ImageNotFound:
            if policy == "NEVER":
                raise RuntimeError(f"本地不存在镜像且拉取策略为 NEVER：{image_ref}")
            self._pull_image(image_ref)

    @staticmethod
    def _event_from_log(record: dict[str, Any], stream: str, seq: int) -> dict[str, Any] | None:
        line = record["line"].strip()
        try:
            payload = json.loads(line)
        except ValueError:
            return None
        if not isinstance(payload, dict) or payload.get("schema") != "crawler.event.v1":
            return None
        level = str(payload.get("level", "INFO")).upper()
        if level not in {"ERROR", "CRITICAL"}:
            return None
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        return {
            "event_uid": str(payload.get("event_id") or f"evt_{uuid.uuid4().hex}"),
            "stream": stream,
            "seq": seq,
            "level": level,
            "event_name": str(payload.get("event", "error")),
            "message": str(payload.get("message", "")),
            "error_code": str(error.get("code") or payload.get("error_code") or "SPIDER.ERROR"),
            "error_type": str(error.get("type") or "CrawlerError"),
            "retryable": bool(error.get("retryable", False)),
            "context": payload.get("context") if isinstance(payload.get("context"), dict) else {},
            "payload": payload,
            "occurred_at": payload.get("timestamp"),
        }

    def _append_chunk(
        self,
        spool: RunSpool,
        stream: str,
        data: bytes,
        buffers: dict[str, str],
        skip_remaining: dict[str, int] | None = None,
    ) -> None:
        text = buffers[stream] + data.decode("utf-8", errors="replace")
        parts = text.split("\n")
        buffers[stream] = parts.pop()
        for line in parts:
            if skip_remaining is not None and skip_remaining.get(stream, 0) > 0:
                skip_remaining[stream] -= 1
                continue
            seq, record = spool.append_log(stream, line)
            event = self._event_from_log(record, stream, seq)
            if event:
                spool.append_event(event)

    def flush(self, spool: RunSpool) -> bool:
        execution = spool.execution()
        if not execution:
            return False
        run_id = int(execution["run_id"])
        lease = str(execution["lease_token"])
        state = spool.upload_state()
        try:
            for stream, path in (("stdout", spool.stdout_path), ("stderr", spool.stderr_path)):
                stream_state = state[stream]
                records, next_offset = spool.read_records(path, int(stream_state["offset"]), self.config.log_upload_batch_size)
                if records:
                    response = self.api.logs(run_id, lease, stream, int(records[0]["seq"]), [str(x["line"]) for x in records])
                    if int(response.get("ack_seq", 0)) >= int(records[-1]["seq"]):
                        stream_state["offset"] = next_offset
                        stream_state["ack_seq"] = int(response["ack_seq"])
                        spool.save_upload_state(state)
                        return True
            event_state = state["events"]
            records, next_offset = spool.read_records(spool.events_path, int(event_state["offset"]), self.config.event_upload_batch_size)
            if records:
                self.api.events(run_id, lease, [x["event"] for x in records])
                event_state["offset"] = next_offset
                event_state["ack_local_seq"] = int(records[-1]["local_seq"])
                spool.save_upload_state(state)
                return True
            finish = spool.finish_payload()
            if finish and not state.get("finish_uploaded"):
                self.api.finish(run_id, lease, finish)
                state["finish_uploaded"] = True
                spool.save_upload_state(state)
                spool.mark_completed()
                return True
        except LeaseLostError:
            spool.set_phase("LEASE_LOST")
            raise
        except (PlatformUnavailable, UnauthorizedError):
            return False
        return False

    def flush_all(self, spool: RunSpool, max_seconds: int = 10) -> None:
        deadline = time.monotonic() + max_seconds
        while time.monotonic() < deadline:
            if not self.flush(spool):
                break

    def _confirm_started(self, keeper: LeaseKeeper, container: Any) -> bool:
        """Confirm RUNNING without killing a healthy container during a short outage."""
        while True:
            if keeper.cancel_action:
                return False
            try:
                self.api.started(keeper.run_id, keeper.lease, container.id, container.name)
                return True
            except LeaseLostError:
                raise
            except (PlatformUnavailable, UnauthorizedError):
                if keeper.lease_lost or keeper.cancel_action:
                    return False
                time.sleep(2)

    def _write_agent_event(self, spool: RunSpool, name: str, message: str, level: str = "INFO", **extra: Any) -> None:
        spool.append_event({
            "event_uid": f"agent_{uuid.uuid4().hex}",
            "stream": "agent",
            "seq": None,
            "level": level,
            "event_name": name,
            "message": message,
            "error_code": extra.pop("error_code", ""),
            "error_type": extra.pop("error_type", ""),
            "retryable": bool(extra.pop("retryable", False)),
            "context": extra,
            "payload": {},
        })

    def _build_finish(self, spool: RunSpool, state: dict[str, Any], exit_code: int | None, forced: str = "") -> dict[str, Any]:
        result = read_json(spool.path / "result.json", None)
        last_error = read_json(spool.path / "last_error.json", None)
        result_status = str((result or {}).get("status", "")).lower()
        status_map = {
            "success": "SUCCEEDED",
            "partial_success": "PARTIAL_SUCCESS",
            "skipped": "SKIPPED",
            "failed": "FAILED",
            "cancelled": "CANCELLED",
            "timeout": "TIMED_OUT",
        }
        oom = bool(state.get("OOMKilled", False))
        terminal = (result or {}).get("terminal_error") if isinstance(result, dict) else None
        if forced == "TIMEOUT_STOP":
            status = "TIMED_OUT"
            terminal = terminal or {"code": "AGENT.TASK_TIMEOUT", "type": "TaskTimeoutError", "message": "任务执行超时", "retryable": True}
        elif forced == "STOP":
            status = "CANCELLED"
        elif oom:
            status = "FAILED"
            terminal = terminal or {"code": "AGENT.OOM_KILLED", "type": "ContainerOOMError", "message": "容器被 OOM Killer 终止", "retryable": True}
        elif result_status in status_map:
            status = status_map[result_status]
        elif exit_code == 0:
            status = "FAILED"
            terminal = {"code": "RUNTIME.RESULT_MISSING", "type": "ResultMissingError", "message": "容器退出码为 0，但未生成有效 result.json", "retryable": False}
        else:
            status = "FAILED"
            terminal = {"code": "AGENT.CONTAINER_EXIT_NONZERO", "type": "ContainerExitError", "message": f"容器非零退出：{exit_code}", "retryable": True}
        return {
            "status": status,
            "exit_code": exit_code,
            "oom_killed": oom,
            "result": result,
            "last_error": last_error,
            "terminal_error": terminal,
            "inspect_summary": {
                "status": state.get("Status"),
                "exit_code": exit_code,
                "oom_killed": oom,
                "error": state.get("Error", ""),
                "started_at": state.get("StartedAt"),
                "finished_at": state.get("FinishedAt"),
            },
        }

    def execute(self, spool: RunSpool, recover: bool = False) -> None:
        execution = spool.execution()
        run_id = int(execution["run_id"])
        lease = str(execution["lease_token"])
        image = execution["image"]
        runtime = execution["runtime"]
        keeper = LeaseKeeper(self.api, run_id, lease, self.config.run_heartbeat_seconds)
        container = None
        stopper: ContainerStopper | None = None
        forced = ""
        try:
            state = spool.state()
            container_id = state.get("container_id", "")
            if recover and state.get("phase") in {"STARTING", "RUNNING"} and container_id:
                try:
                    container = self.client.containers.get(container_id)
                    container.reload()
                except NotFound:
                    self._write_agent_event(spool, "container_missing", "Agent 重启后无法找到运行容器", "ERROR", error_code="AGENT.CONTAINER_MISSING", error_type="ContainerMissingError")
                    spool.write_finish({
                        "status": "FAILED", "exit_code": None, "oom_killed": False, "result": None, "last_error": None,
                        "terminal_error": {"code": "AGENT.CONTAINER_MISSING", "type": "ContainerMissingError", "message": "Agent 重启后无法找到运行容器", "retryable": True},
                        "inspect_summary": None,
                    })
                    self.flush_all(spool, 30)
                    return
            if container is None:
                # 未获得 STARTING 确认前不启动容器，避免租约失效后重复执行。
                while True:
                    try:
                        self.api.starting(run_id, lease, "准备镜像和任务容器")
                        break
                    except PlatformUnavailable:
                        spool.set_phase("WAITING_PLATFORM")
                        time.sleep(3)
                    except UnauthorizedError:
                        time.sleep(3)
                    except LeaseLostError:
                        spool.set_phase("LEASE_LOST")
                        return
                spool.set_phase("STARTING")
                keeper.start()
                self._write_agent_event(spool, "image_pull_started", image["ref"])
                self._ensure_image(image["ref"], image.get("pull_policy", "IF_NOT_PRESENT"))
                if keeper.cancel_action:
                    forced = keeper.cancel_action
                    spool.write_finish(self._build_finish(spool, {}, None, forced))
                    self.flush_all(spool, 30)
                    return
                name = f"crawler-run-{run_id}-{uuid.uuid4().hex[:8]}"
                command = [
                    "run", "--mode", "server",
                    "--task-file", "/run/crawler/task.json",
                    "--resources-file", "/run/crawler/resources.json",
                    "--secrets-file", "/run/crawler/secrets.json",
                    "--result-file", "/run/crawler/result.json",
                    "--errors-file", "/run/crawler/errors.ndjson",
                    "--last-error-file", "/run/crawler/last_error.json",
                ]
                container = self.client.containers.create(
                    image=image["ref"],
                    name=name,
                    command=command,
                    detach=True,
                    labels={"crawler.managed": "true", "crawler.run_id": str(run_id), "crawler.run_no": execution.get("run_no", "")},
                    nano_cpus=int(float(runtime.get("cpu_limit", 2)) * 1_000_000_000),
                    mem_limit=f"{int(runtime.get('memory_limit_mb', 4096))}m",
                    shm_size=f"{int(runtime.get('shm_size_mb', 256))}m",
                    pids_limit=int(runtime.get("pids_limit", 512)),
                    volumes={str(spool.path): {"bind": "/run/crawler", "mode": "rw"}},
                    network_mode=self.config.container_network,
                    init=True,
                )
                spool.set_phase("STARTING", container_id=container.id, container_name=container.name)
                container.start()
                keeper.container_id = container.id
                stopper = ContainerStopper(keeper, container, int(runtime.get("stop_grace_seconds", 30)))
                stopper.start()
                if self._confirm_started(keeper, container):
                    spool.set_phase("RUNNING", container_id=container.id, container_name=container.name, started_monotonic=time.monotonic(), started_at=time.time())
                else:
                    forced = keeper.cancel_action or "STOP"
            else:
                keeper.container_id = container.id
                keeper.start()
                container.reload()
                if container.status == "created":
                    container.start()
                stopper = ContainerStopper(keeper, container, int(runtime.get("stop_grace_seconds", 30)))
                stopper.start()
                # started 接口允许 STARTING->RUNNING 和 RUNNING->RUNNING，确保
                # Agent 在任何崩溃点恢复后，平台与本地状态重新对齐。
                if self._confirm_started(keeper, container):
                    spool.set_phase(
                        "RUNNING",
                        container_id=container.id,
                        container_name=container.name,
                        started_at=spool.state().get("started_at") or time.time(),
                    )
                else:
                    forced = keeper.cancel_action or "STOP"

            buffers = {"stdout": "", "stderr": ""}
            # Agent 重启后 Docker 会回放容器历史日志。按已落盘行数分别跳过，
            # 既避免重复，又能补齐 Agent 停机期间产生的日志。
            skip_remaining = {
                "stdout": max(0, spool.next_seq["stdout"] - 1) if recover else 0,
                "stderr": max(0, spool.next_seq["stderr"] - 1) if recover else 0,
            }
            log_stream = container.attach(stream=True, logs=True, stdout=True, stderr=True, demux=True)
            for item in log_stream:
                if keeper.cancel_action:
                    forced = keeper.cancel_action
                if isinstance(item, tuple):
                    out, err = item
                    if out:
                        self._append_chunk(spool, "stdout", out, buffers, skip_remaining)
                    if err:
                        self._append_chunk(spool, "stderr", err, buffers, skip_remaining)
                elif item:
                    self._append_chunk(spool, "stdout", item, buffers, skip_remaining)
                self.flush(spool)
            for stream, pending in buffers.items():
                if pending:
                    seq, record = spool.append_log(stream, pending)
                    event = self._event_from_log(record, stream, seq)
                    if event:
                        spool.append_event(event)
            container.wait()
            container.reload()
            docker_state = container.attrs.get("State", {})
            exit_code = docker_state.get("ExitCode")
            spool.write_finish(self._build_finish(spool, docker_state, exit_code, forced))
            self.flush_all(spool, 30)
            if runtime.get("auto_remove", True) and not (spool.finish_payload().get("status") == "FAILED" and runtime.get("keep_failed_container", False)):
                try:
                    container.remove(force=True)
                except Exception:
                    pass
        except LeaseLostError:
            if container:
                try:
                    container.kill()
                except Exception:
                    pass
            spool.set_phase("LEASE_LOST")
        except Exception as exc:
            self._write_agent_event(spool, "agent_execution_failed", str(exc), "ERROR", error_code="AGENT.EXECUTION_FAILED", error_type=type(exc).__name__, retryable=True)
            if container:
                try:
                    container.reload()
                    state = container.attrs.get("State", {})
                    if state.get("Running"):
                        container.kill()
                except Exception:
                    state = {}
            else:
                state = {}
            spool.write_finish({
                "status": "FAILED",
                "exit_code": state.get("ExitCode"),
                "oom_killed": bool(state.get("OOMKilled", False)),
                "result": read_json(spool.path / "result.json", None),
                "last_error": read_json(spool.path / "last_error.json", None),
                "terminal_error": {"code": "AGENT.EXECUTION_FAILED", "type": type(exc).__name__, "message": str(exc), "retryable": True},
                "inspect_summary": state or None,
            })
            self.flush_all(spool, 30)
        finally:
            if stopper:
                stopper.stop()
            keeper.stop()
