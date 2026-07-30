from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
import time
from types import SimpleNamespace
from pathlib import Path

# docker SDK is a production dependency. Provide a tiny import shim for offline tests.
try:
    import docker  # noqa: F401
except ModuleNotFoundError:
    docker_module = types.ModuleType("docker")
    docker_module.from_env = lambda: None
    errors = types.ModuleType("docker.errors")
    errors.ImageNotFound = type("ImageNotFound", (Exception,), {})
    errors.NotFound = type("NotFound", (Exception,), {})
    docker_module.errors = errors
    sys.modules["docker"] = docker_module
    sys.modules["docker.errors"] = errors

from crawler_agent.api import PlatformUnavailable
from crawler_agent.docker_runner import ContainerStopper, RunExecutor
from crawler_agent.spool import RunSpool


class SpoolTest(unittest.TestCase):
    def test_persistent_sequences_offsets_and_replay_skip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spool = RunSpool(root, 11, uid=0, gid=0)
            spool.append_log("stdout", "old-1")
            spool.append_log("stdout", "old-2")
            spool.append_log("stderr", "old-error")
            restored = RunSpool(root, 11, uid=0, gid=0)
            self.assertEqual(restored.next_seq["stdout"], 3)
            self.assertEqual(restored.next_seq["stderr"], 2)

            executor = object.__new__(RunExecutor)
            buffers = {"stdout": "", "stderr": ""}
            skip = {"stdout": 2, "stderr": 1}
            executor._append_chunk(restored, "stdout", b"old-1\nold-2\nnew-3\n", buffers, skip)
            executor._append_chunk(restored, "stderr", b"old-error\nnew-error\n", buffers, skip)
            stdout, _ = restored.read_records(restored.stdout_path, 0, 20)
            stderr, _ = restored.read_records(restored.stderr_path, 0, 20)
            self.assertEqual([x["line"] for x in stdout], ["old-1", "old-2", "new-3"])
            self.assertEqual([x["line"] for x in stderr], ["old-error", "new-error"])


    def test_started_confirmation_survives_short_platform_outage(self) -> None:
        class API:
            def __init__(self):
                self.calls = 0

            def started(self, *_args):
                self.calls += 1
                if self.calls == 1:
                    raise PlatformUnavailable("temporary")
                return {"ok": True}

        executor = object.__new__(RunExecutor)
        executor.api = API()
        keeper = SimpleNamespace(run_id=1, lease="lease", cancel_action="", lease_lost=False)
        container = SimpleNamespace(id="cid", name="container")
        self.assertTrue(executor._confirm_started(keeper, container))
        self.assertEqual(executor.api.calls, 2)

    def test_cancel_monitor_stops_quiet_container(self) -> None:
        class Container:
            def __init__(self):
                self.stopped = False

            def stop(self, timeout):
                self.stopped = True

            def kill(self):
                self.stopped = True

        keeper = SimpleNamespace(run_id=1, cancel_action="", lease_lost=False)
        container = Container()
        stopper = ContainerStopper(keeper, container, 1)
        stopper.start()
        keeper.cancel_action = "STOP"
        deadline = time.monotonic() + 2
        while not container.stopped and time.monotonic() < deadline:
            time.sleep(0.02)
        stopper.stop()
        self.assertTrue(container.stopped)

    def test_recover_starting_container_uses_original_container(self) -> None:
        import crawler_agent.main as main_module

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spool = RunSpool(root, 23, uid=0, gid=0)
            spool.set_phase("STARTING", container_id="existing")
            original = main_module.config
            main_module.config = SimpleNamespace(run_root=root, container_uid=0, container_gid=0)
            try:
                app = object.__new__(main_module.AgentApp)
                submitted = []
                app._submit = lambda item, recover: submitted.append((item.run_id, recover))
                app.executor = SimpleNamespace(flush_all=lambda *_args: None)
                app.recover()
            finally:
                main_module.config = original
            self.assertEqual(submitted, [(23, True)])

    def test_structured_error_event_parsing(self) -> None:
        payload = {
            "schema": "crawler.event.v1",
            "event_id": "evt-1",
            "timestamp": "2026-07-30T00:00:00Z",
            "level": "ERROR",
            "event": "login_failed",
            "message": "登录失败",
            "error": {"code": "LOGIN.FAILED", "type": "AuthenticationError", "retryable": False},
            "context": {"account_id": "a1"},
        }
        event = RunExecutor._event_from_log({"line": json.dumps(payload, ensure_ascii=False)}, "stdout", 9)
        self.assertEqual(event["event_uid"], "evt-1")
        self.assertEqual(event["seq"], 9)
        self.assertEqual(event["error_code"], "LOGIN.FAILED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
