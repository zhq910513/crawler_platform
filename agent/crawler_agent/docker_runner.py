from __future__ import annotations

import json
import queue
import re
import shlex
import threading
import time
from typing import Any

import docker
from docker.errors import ImageNotFound

from crawler_agent.api import PlatformAPI


class DockerTaskRunner:
    def __init__(self, client: docker.DockerClient, api: PlatformAPI) -> None:
        self.client = client
        self.api = api

    @staticmethod
    def _container_name(payload: dict[str, Any]) -> str:
        base = f"crawler-{payload['task_code']}-{payload['run_id']}".lower()
        return re.sub(r"[^a-z0-9_.-]+", "-", base)[:120]

    @staticmethod
    def _command(payload: dict[str, Any]) -> list[str]:
        executor_type = payload["executor_type"]
        if executor_type == "PYTHON_METHOD":
            return [
                "python",
                "-m",
                "crawler_runtime",
                "--entrypoint",
                payload["entrypoint"],
                "--args-json",
                json.dumps(payload.get("arguments", []), ensure_ascii=False),
                "--kwargs-json",
                json.dumps(payload.get("keyword_arguments", {}), ensure_ascii=False),
            ]
        if executor_type == "PYTHON_MODULE":
            return ["python", "-m", payload["entrypoint"], *[str(item) for item in payload.get("arguments", [])]]
        command = payload.get("container_command") or []
        if isinstance(command, str):
            command = shlex.split(command)
        if not command:
            raise RuntimeError("COMMAND 执行方式必须配置 container_command")
        return [str(item) for item in command]

    @staticmethod
    def _volumes(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
        result: dict[str, dict[str, str]] = {}
        for item in payload.get("volume_mounts", []):
            source = str(item.get("source", "")).strip()
            target = str(item.get("target", "")).strip()
            mode = str(item.get("mode", "ro")).strip() or "ro"
            if not source or not target:
                continue
            result[source] = {"bind": target, "mode": mode}
        return result

    def _ensure_image(self, image_ref: str, pull_policy: str) -> None:
        if pull_policy == "ALWAYS":
            self.client.images.pull(image_ref)
            return
        try:
            self.client.images.get(image_ref)
        except ImageNotFound:
            if pull_policy == "NEVER":
                raise RuntimeError(f"本地不存在镜像且拉取策略为 NEVER：{image_ref}")
            self.client.images.pull(image_ref)

    def _log_reader(self, container, output_queue: queue.Queue[str], stop_event: threading.Event) -> None:
        try:
            for raw in container.logs(stream=True, follow=True, stdout=True, stderr=True):
                if stop_event.is_set():
                    break
                output_queue.put(raw.decode("utf-8", errors="replace"))
        except Exception as exc:
            output_queue.put(f"[agent] 容器日志读取失败：{exc}\n")

    def _flush_logs(self, run_id: int, output_queue: queue.Queue[str], force: bool = False) -> None:
        lines: list[str] = []
        max_lines = 200 if force else 50
        while len(lines) < max_lines:
            try:
                lines.append(output_queue.get_nowait())
            except queue.Empty:
                break
        if lines:
            self.api.logs(run_id, lines)

    def _stop_container(self, container, grace_seconds: int) -> None:
        try:
            container.stop(timeout=max(1, grace_seconds))
        except Exception:
            try:
                container.kill()
            except Exception:
                pass

    def run(self, payload: dict[str, Any]) -> None:
        run_id = int(payload["run_id"])
        container = None
        output_queue: queue.Queue[str] = queue.Queue()
        stop_logs = threading.Event()
        log_thread: threading.Thread | None = None
        forced_status: str | None = None
        error_type = ""
        error_message = ""
        exit_code: int | None = None
        inspect_summary: dict[str, Any] | None = None
        started_monotonic = 0.0
        try:
            image_ref = payload["image_ref"]
            self.api.event(run_id, {"event_type": "IMAGE", "event_action": "PULL_START", "event_message": image_ref})
            self._ensure_image(image_ref, payload.get("pull_policy", "IF_NOT_PRESENT"))
            self.api.event(run_id, {"event_type": "IMAGE", "event_action": "READY", "event_message": image_ref})

            environment = dict(payload.get("environment_variables", {}))
            environment.update(payload.get("resolved_secrets", {}))
            command = self._command(payload)
            container_name = self._container_name(payload)
            create_kwargs: dict[str, Any] = {
                "image": image_ref,
                "name": container_name,
                "command": command,
                "detach": True,
                "environment": environment,
                "labels": {
                    "crawler.managed": "true",
                    "crawler.run_id": str(run_id),
                    "crawler.run_no": payload["run_no"],
                    "crawler.task_id": str(payload["task_id"]),
                    "crawler.task_code": payload["task_code"],
                },
                "nano_cpus": int(float(payload.get("cpu_limit", 1)) * 1_000_000_000),
                "mem_limit": f"{int(payload.get('memory_limit_mb', 1024))}m",
                "shm_size": f"{int(payload.get('shm_size_mb', 64))}m",
                "pids_limit": int(payload.get("pids_limit", 512)),
                "volumes": self._volumes(payload),
                "init": True,
            }
            if payload.get("container_working_dir"):
                create_kwargs["working_dir"] = payload["container_working_dir"]
            network_mode = payload.get("network_mode", "bridge")
            if network_mode:
                create_kwargs["network_mode"] = network_mode

            container = self.client.containers.create(**create_kwargs)
            self.api.event(run_id, {"container_id": container.id, "container_name": container.name, "event_type": "CONTAINER", "event_action": "CREATED"})
            container.start()
            self.api.started(run_id, container.id, container.name)
            self.api.event(run_id, {"container_id": container.id, "container_name": container.name, "event_type": "CONTAINER", "event_action": "STARTED"})
            started_monotonic = time.monotonic()

            log_thread = threading.Thread(target=self._log_reader, args=(container, output_queue, stop_logs), daemon=True)
            log_thread.start()
            last_heartbeat = 0.0
            timeout_seconds = int(payload.get("timeout_seconds", 3600))
            grace_seconds = int(payload.get("stop_grace_seconds", 30))

            while True:
                container.reload()
                self._flush_logs(run_id, output_queue)
                now_mono = time.monotonic()
                if now_mono - last_heartbeat >= 10:
                    control = self.api.run_heartbeat(run_id, container.id)
                    action = control.get("desired_action", "NONE")
                    if action == "STOP":
                        forced_status = "CANCELLED"
                        self._stop_container(container, grace_seconds)
                    elif action == "TIMEOUT_STOP":
                        forced_status = "TIMEOUT"
                        self._stop_container(container, grace_seconds)
                    last_heartbeat = now_mono
                if timeout_seconds > 0 and now_mono - started_monotonic > timeout_seconds and not forced_status:
                    forced_status = "TIMEOUT"
                    self._stop_container(container, grace_seconds)
                if container.status in {"exited", "dead"}:
                    break
                time.sleep(1)

            stop_logs.set()
            if log_thread:
                log_thread.join(timeout=3)
            while not output_queue.empty():
                self._flush_logs(run_id, output_queue, force=True)
            container.reload()
            state = container.attrs.get("State", {})
            exit_code = state.get("ExitCode")
            inspect_summary = {
                "status": state.get("Status"),
                "exit_code": exit_code,
                "oom_killed": state.get("OOMKilled", False),
                "error": state.get("Error", ""),
                "started_at": state.get("StartedAt"),
                "finished_at": state.get("FinishedAt"),
            }
            if forced_status:
                final_status = forced_status
                error_type = "MANUAL_CANCEL" if forced_status == "CANCELLED" else "TASK_TIMEOUT"
                error_message = "任务收到停止指令" if forced_status == "CANCELLED" else "任务执行超时"
            elif exit_code == 0:
                final_status = "SUCCESS"
            else:
                final_status = "FAILED"
                error_type = "OOM_KILLED" if state.get("OOMKilled") else "CONTAINER_EXIT_NONZERO"
                error_message = state.get("Error") or f"容器退出码：{exit_code}"
            self.api.event(run_id, {"container_id": container.id, "container_name": container.name, "event_type": "CONTAINER", "event_action": "EXITED", "exit_code": exit_code, "event_message": error_message})
            self.api.finish(run_id, {"status": final_status, "exit_code": exit_code, "error_type": error_type, "error_message": error_message, "inspect_summary": inspect_summary})

            should_remove = bool(payload.get("auto_remove", True)) and not (final_status != "SUCCESS" and payload.get("keep_failed_container", False))
            if should_remove:
                try:
                    container.remove(force=True)
                    self.api.event(run_id, {"container_id": container.id, "container_name": container.name, "event_type": "CONTAINER", "event_action": "REMOVED"})
                except Exception as exc:
                    print(f"清理容器失败 run={run_id}: {exc}")
        except Exception as exc:
            error_type = type(exc).__name__
            error_message = str(exc)
            try:
                self.api.logs(run_id, [f"[agent] 任务执行失败：{error_type}: {error_message}\n"])
                self.api.finish(run_id, {"status": forced_status or "FAILED", "exit_code": exit_code, "error_type": error_type, "error_message": error_message, "inspect_summary": inspect_summary})
            except Exception as report_exc:
                print(f"上报任务失败结果失败 run={run_id}: {report_exc}")
            if container:
                try:
                    self._stop_container(container, int(payload.get("stop_grace_seconds", 30)))
                except Exception:
                    pass
        finally:
            stop_logs.set()
