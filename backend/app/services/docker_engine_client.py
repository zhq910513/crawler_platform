from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
import socket
import tarfile
import time
from typing import Any
from urllib.parse import quote, urlencode
import http.client


class DockerEngineError(RuntimeError):
    pass


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: float = 60):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:  # pragma: no cover - depends on host docker socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        self.sock = sock


class DockerEngineClient:
    """Minimal Docker Engine API client used when docker CLI is absent.

    The platform build center should not fail just because the API image does not
    include the docker binary. When /var/run/docker.sock is mounted, Docker Engine
    already exposes the build/push/inspect capabilities we need. This client keeps
    the fallback intentionally small and only implements the calls used by
    BuildCenterService.
    """

    def __init__(self, socket_path: str | None = None, timeout: float = 1800):
        self.socket_path = socket_path or self._resolve_socket_path()
        self.timeout = timeout

    @staticmethod
    def _resolve_socket_path() -> str:
        docker_host = (os.getenv("DOCKER_HOST") or "").strip()
        if docker_host.startswith("unix://"):
            return docker_host.removeprefix("unix://")
        return "/var/run/docker.sock"

    def is_available(self) -> bool:
        try:
            return Path(self.socket_path).exists() and self.ping()
        except Exception:
            return False

    def ping(self) -> bool:
        status, body = self._request("GET", "/_ping", timeout=8)
        return status == 200 and body.strip() in {b"OK", b""}

    def build(self, context_dir: Path, tag: str, build_args: dict[str, str] | None = None, platform: str | None = None) -> str:
        context = self._tar_context(context_dir)
        params: dict[str, str] = {
            "t": tag,
            "dockerfile": "Dockerfile",
            "rm": "1",
            "forcerm": "1",
            "version": "2",
        }
        if build_args:
            params["buildargs"] = json.dumps(build_args, ensure_ascii=False)
        if platform:
            params["platform"] = platform
        path = self._versioned_path("/build?") + urlencode(params)
        status, body = self._request("POST", path, body=context, headers={"Content-Type": "application/x-tar"}, timeout=self.timeout)
        text = body.decode("utf-8", errors="replace")
        if status >= 400:
            raise DockerEngineError(self._http_error_message("Docker build", status, text))
        self._raise_on_stream_error(text, "Docker build")
        return text

    def push(self, image_repository: str, tag: str) -> str:
        # Docker accepts an empty auth config for local/insecure registries. The
        # value is base64url/json compatible with the Docker Engine API contract.
        auth = base64.b64encode(b"{}").decode("ascii")
        path = self._versioned_path(f"/images/{quote(image_repository, safe='')}/push?") + urlencode({"tag": tag})
        status, body = self._request("POST", path, headers={"X-Registry-Auth": auth}, timeout=self.timeout)
        text = body.decode("utf-8", errors="replace")
        if status >= 400:
            raise DockerEngineError(self._http_error_message("Docker push", status, text))
        self._raise_on_stream_error(text, "Docker push")
        return text

    def inspect_image(self, image_ref: str) -> dict[str, Any]:
        status, body = self._request("GET", self._versioned_path(f"/images/{quote(image_ref, safe='')}/json"), timeout=60)
        text = body.decode("utf-8", errors="replace")
        if status >= 400:
            raise DockerEngineError(self._http_error_message("Docker image inspect", status, text))
        return json.loads(text)

    def _versioned_path(self, path: str) -> str:
        api_version = (os.getenv("DOCKER_API_VERSION") or "").strip()
        if not api_version:
            status, body = self._request("GET", "/version", timeout=8)
            text = body.decode("utf-8", errors="replace")
            if status >= 400:
                raise DockerEngineError(self._http_error_message("Docker API version negotiation", status, text))
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise DockerEngineError(f"Docker API version negotiation failed: invalid /version response: {text[-1000:]}") from exc
            api_version = str(payload.get("ApiVersion") or "").strip()
            if not api_version:
                raise DockerEngineError("Docker API version negotiation failed: /version did not return ApiVersion")
        if not path.startswith("/"):
            path = "/" + path
        return f"/v{api_version}{path}"

    @staticmethod
    def _http_error_message(stage: str, status: int, text: str) -> str:
        message = ""
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                message = str(payload.get("message") or payload.get("error") or "").strip()
        except json.JSONDecodeError:
            pass
        detail = message or text.strip() or f"HTTP {status}"
        return f"{stage} failed: HTTP {status}: {detail}"[-6000:]

    def _request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> tuple[int, bytes]:
        conn = UnixHTTPConnection(self.socket_path, timeout=timeout or self.timeout)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            data = response.read()
            return response.status, data
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            raise DockerEngineError(f"Docker Engine request failed: {method} {path}: {exc}") from exc
        finally:
            conn.close()

    @staticmethod
    def _raise_on_stream_error(text: str, stage: str) -> None:
        stream_tail: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            stream = str(payload.get("stream") or "").strip()
            status = str(payload.get("status") or "").strip()
            if stream:
                stream_tail.append(stream)
            elif status:
                progress = str(payload.get("progress") or "").strip()
                stream_tail.append(f"{status} {progress}".strip())
            if len(stream_tail) > 20:
                stream_tail = stream_tail[-20:]
            detail = payload.get("errorDetail") or {}
            detail_message = str(detail.get("message") or "").strip() if isinstance(detail, dict) else ""
            error_message = str(payload.get("error") or "").strip()
            if detail_message or error_message:
                message = detail_message or error_message
                context = "\n".join(stream_tail).strip()[-6000:]
                suffix = f"\nDocker stream tail:\n{context}" if context else ""
                raise DockerEngineError(f"{stage} failed: {message}{suffix}")

    @staticmethod
    def _tar_context(context_dir: Path) -> bytes:
        context_dir = context_dir.resolve()
        ignored_dirs = {".git", "__pycache__", ".pytest_cache", "node_modules", "dist", ".venv", "venv"}
        ignored_files = {".DS_Store"}
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as tar:
            for path in sorted(context_dir.rglob("*")):
                rel = path.relative_to(context_dir)
                if any(part in ignored_dirs for part in rel.parts):
                    continue
                if path.name in ignored_files:
                    continue
                info = tar.gettarinfo(str(path), arcname=str(rel))
                # Keep mtime deterministic enough for repeatable diagnostics.
                info.mtime = int(time.time())
                if path.is_file():
                    with path.open("rb") as fh:
                        tar.addfile(info, fh)
                else:
                    tar.addfile(info)
        return buffer.getvalue()
