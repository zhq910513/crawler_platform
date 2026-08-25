from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_build_center_does_not_require_docker_cli_when_socket_is_available() -> None:
    service = (ROOT / 'backend' / 'app' / 'services' / 'build_center_service.py').read_text(encoding='utf-8')
    assert 'DockerEngineClient' in service
    assert 'def _docker_executor_available' in service
    assert 'Docker 执行器不可用：未找到 docker 命令，且 /var/run/docker.sock 不可访问' in service
    assert 'v1.0.95 起 docker CLI 缺失时会自动走 Docker Engine API' in service
    assert 'LOCAL_DOCKER_CLI_OR_ENGINE_API' in service


def test_docker_engine_client_implements_minimal_build_push_inspect_contract() -> None:
    client = (ROOT / 'backend' / 'app' / 'services' / 'docker_engine_client.py').read_text(encoding='utf-8')
    assert 'class DockerEngineClient' in client
    assert 'def build(' in client
    assert 'def push(' in client
    assert 'def inspect_image(' in client
    assert '/var/run/docker.sock' in client
    assert 'Content-Type": "application/x-tar"' in client
    assert 'X-Registry-Auth' in client
