from __future__ import annotations

import base64
import fnmatch
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
    """Docker Engine API error with build/push stream tail preserved."""

    def __init__(self, message: str, output: str = "", status: int | None = None):
        super().__init__(message)
        self.output = output
        self.status = status


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
    already exposes the build/push/inspect capabilities we need. v1.0.103 keeps
    failure streams and context diagnostics visible so users can distinguish base
    image pull/network errors from Dockerfile errors.
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

    def build(self, context_dir: Path, tag: str, build_args: dict[str, str] | None = None, platform: str | None = None, dockerfile: str = "Dockerfile") -> str:
        context = self._tar_context(context_dir)
        params: dict[str, str] = {
            "t": tag,
            "dockerfile": dockerfile,
            "rm": "1",
            "forcerm": "1",
        }
        if build_args:
            params["buildargs"] = json.dumps(build_args, ensure_ascii=False)
        if platform:
            params["platform"] = platform
        path = "/build?" + urlencode(params)
        try:
            status, body = self._request("POST", path, body=context, headers={"Content-Type": "application/x-tar"}, timeout=self.timeout)
        except DockerEngineError:
            raise
        except Exception as exc:  # pragma: no cover - host/network dependent
            raise DockerEngineError(f"Docker build API transport failed: {exc}") from exc
        raw = body.decode("utf-8", errors="replace")
        text = self._format_stream(raw)
        if status >= 400:
            raise DockerEngineError(text[-8000:] or f"Docker build API failed: HTTP {status}", output=text, status=status)
        self._raise_on_stream_error(raw, "Docker build")
        return text

    def pull(self, image_ref: str) -> str:
        from_image, tag = self._split_image_ref_for_pull(image_ref)
        params = {"fromImage": from_image}
        if tag:
            params["tag"] = tag
        auth = base64.b64encode(b"{}").decode("ascii")
        try:
            status, body = self._request("POST", "/images/create?" + urlencode(params), headers={"X-Registry-Auth": auth}, timeout=self.timeout)
        except DockerEngineError:
            raise
        except Exception as exc:  # pragma: no cover - host/network dependent
            raise DockerEngineError(f"Docker pull API transport failed: {exc}") from exc
        raw = body.decode("utf-8", errors="replace")
        text = self._format_stream(raw)
        if status >= 400:
            raise DockerEngineError(text[-8000:] or f"Docker pull API failed: HTTP {status}", output=text, status=status)
        self._raise_on_stream_error(raw, "Docker pull")
        return text

    def push(self, image_repository: str, tag: str) -> str:
        # Docker accepts an empty auth config for local/insecure registries. The
        # value is base64url/json compatible with the Docker Engine API contract.
        auth = base64.b64encode(b"{}").decode("ascii")
        path = f"/images/{quote(image_repository, safe='')}/push?" + urlencode({"tag": tag})
        try:
            status, body = self._request("POST", path, headers={"X-Registry-Auth": auth}, timeout=self.timeout)
        except DockerEngineError:
            raise
        except Exception as exc:  # pragma: no cover - host/network dependent
            raise DockerEngineError(f"Docker push API transport failed: {exc}") from exc
        raw = body.decode("utf-8", errors="replace")
        text = self._format_stream(raw)
        if status >= 400:
            raise DockerEngineError(text[-8000:] or f"Docker push API failed: HTTP {status}", output=text, status=status)
        self._raise_on_stream_error(raw, "Docker push")
        return text

    def inspect_image(self, image_ref: str) -> dict[str, Any]:
        status, body = self._request("GET", f"/images/{quote(image_ref, safe='')}/json", timeout=60)
        text = body.decode("utf-8", errors="replace")
        if status >= 400:
            raise DockerEngineError(text[-2000:] or f"Docker image inspect API failed: HTTP {status}", output=text, status=status)
        return json.loads(text)

    def image_exists(self, image_ref: str) -> bool:
        try:
            self.inspect_image(image_ref)
            return True
        except Exception:
            return False

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
            raise DockerEngineError(f"Docker Engine API request failed: {method} {path}: {exc}") from exc
        finally:
            conn.close()

    @staticmethod
    def _raise_on_stream_error(raw_text: str, stage: str) -> None:
        formatted = DockerEngineClient._format_stream(raw_text)
        for line in raw_text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("error"):
                detail = payload.get("errorDetail") or {}
                message = detail.get("message") or payload.get("error")
                tail = formatted[-8000:]
                raise DockerEngineError(f"{stage} failed: {message}\n--- docker output tail ---\n{tail}", output=formatted)

    @staticmethod
    def _format_stream(raw_text: str) -> str:
        lines: list[str] = []
        for line in raw_text.splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                lines.append(line)
                continue
            if payload.get("stream"):
                lines.append(str(payload["stream"]).rstrip("\n"))
            if payload.get("status"):
                detail = payload.get("progress") or payload.get("id") or ""
                lines.append((str(payload["status"]) + (f" {detail}" if detail else "")).rstrip())
            if payload.get("aux"):
                lines.append(json.dumps(payload["aux"], ensure_ascii=False, sort_keys=True))
            if payload.get("error"):
                detail = payload.get("errorDetail") or {}
                lines.append(str(detail.get("message") or payload.get("error")))
        return "\n".join(item for item in lines if item)

    @staticmethod
    def _split_image_ref_for_pull(image_ref: str) -> tuple[str, str | None]:
        image_ref = (image_ref or "").strip()
        if "@" in image_ref:
            return image_ref, None
        slash = image_ref.rfind("/")
        colon = image_ref.rfind(":")
        if colon > slash:
            return image_ref[:colon], image_ref[colon + 1:]
        return image_ref, "latest"

    @staticmethod
    def _dockerignore_patterns(context_dir: Path) -> list[tuple[str, bool]]:
        dockerignore = context_dir / ".dockerignore"
        if not dockerignore.exists():
            return []
        patterns: list[tuple[str, bool]] = []
        for raw in dockerignore.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            negated = line.startswith("!")
            if negated:
                line = line[1:].strip()
            if line:
                patterns.append((line.strip("/"), negated))
        return patterns

    @staticmethod
    def _ignored_by_dockerignore(rel: Path, patterns: list[tuple[str, bool]]) -> bool:
        value = str(rel).replace(os.sep, "/")
        ignored = False
        for pattern, negated in patterns:
            if not pattern:
                continue
            matches = fnmatch.fnmatch(value, pattern) or fnmatch.fnmatch(rel.name, pattern)
            if pattern.endswith("/"):
                matches = value.startswith(pattern.rstrip("/") + "/")
            if "/" not in pattern and any(fnmatch.fnmatch(part, pattern) for part in rel.parts):
                matches = True
            if matches:
                ignored = not negated
        return ignored

    @staticmethod
    def _tar_context(context_dir: Path) -> bytes:
        context_dir = context_dir.resolve()
        ignored_dirs = {".git", "__pycache__", ".pytest_cache", "node_modules", "dist", ".venv", "venv"}
        ignored_files = {".DS_Store"}
        dockerignore_patterns = DockerEngineClient._dockerignore_patterns(context_dir)
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as tar:
            for path in sorted(context_dir.rglob("*")):
                rel = path.relative_to(context_dir)
                if any(part in ignored_dirs for part in rel.parts):
                    continue
                if path.name in ignored_files:
                    continue
                if DockerEngineClient._ignored_by_dockerignore(rel, dockerignore_patterns):
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
