from __future__ import annotations

from pathlib import Path
import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:////tmp/crawler_platform_docker_diagnostics_10103.db")

from app.services.build_center_service import BuildCenterService
from app.services.docker_engine_client import DockerEngineClient, DockerEngineError

ROOT = Path(__file__).resolve().parents[2]


def test_docker_engine_error_preserves_stream_tail() -> None:
    raw = '\n'.join([
        '{"stream":"Step 1/3 : FROM python:3.12-slim\\n"}',
        '{"stream":"Pulling from library/python\\n"}',
        '{"errorDetail":{"message":"failed to solve: failed to copy: connection reset by peer"},"error":"failed to solve"}',
    ])
    try:
        DockerEngineClient._raise_on_stream_error(raw, 'Docker build')
    except DockerEngineError as exc:
        text = str(exc)
        assert 'Step 1/3' in text
        assert 'Pulling from library/python' in text
        assert 'connection reset by peer' in text
    else:  # pragma: no cover
        raise AssertionError('expected DockerEngineError')


def test_dockerfile_base_image_parser_handles_platform_and_alias(tmp_path: Path) -> None:
    dockerfile = tmp_path / 'Dockerfile'
    dockerfile.write_text('''\nFROM --platform=$TARGETPLATFORM python:3.12-slim AS runtime\nRUN python --version\nFROM scratch AS empty\n''', encoding='utf-8')
    service = BuildCenterService.__new__(BuildCenterService)
    assert service._dockerfile_base_images(dockerfile) == ['python:3.12-slim']


def test_build_center_logs_docker_context_pull_and_error_details() -> None:
    service = (ROOT / 'backend' / 'app' / 'services' / 'build_center_service.py').read_text(encoding='utf-8')
    config = (ROOT / 'backend' / 'app' / 'config.py').read_text(encoding='utf-8')
    env_example = (ROOT / '.env.example').read_text(encoding='utf-8')
    configure = (ROOT / 'deploy' / 'scripts' / 'configure-project-build-center.sh').read_text(encoding='utf-8')
    assert 'DOCKER_CONTEXT' in service
    assert '_dockerfile_base_images' in service
    assert 'crawler_project_docker_context_diagnostics_enabled' in config
    assert 'CRAWLER_PROJECT_DOCKER_CONTEXT_DIAGNOSTICS_ENABLED=1' in env_example
    assert 'set_env_value CRAWLER_PROJECT_DOCKER_CONTEXT_DIAGNOSTICS_ENABLED' in configure


def test_docker_engine_error_uses_error_detail_without_legacy_error_field() -> None:
    raw = '\n'.join([
        '{"stream":"Step 1/2 : FROM python:3.12-slim\\n"}',
        '{"errorDetail":{"message":"failed to resolve source metadata"}}',
    ])
    try:
        DockerEngineClient._raise_on_stream_error(raw, 'Docker build')
    except DockerEngineError as exc:
        text = str(exc)
        assert 'failed to resolve source metadata' in text
        assert 'Step 1/2' in text
    else:  # pragma: no cover
        raise AssertionError('expected DockerEngineError')


def test_docker_engine_build_uses_negotiated_api_version(tmp_path: Path) -> None:
    (tmp_path / 'Dockerfile').write_text('FROM scratch\n', encoding='utf-8')

    class FakeDockerEngineClient(DockerEngineClient):
        def __init__(self) -> None:
            super().__init__(socket_path='/tmp/fake-docker.sock', timeout=30)
            self.paths: list[str] = []

        def _request(self, method, path, body=None, headers=None, timeout=None):
            self.paths.append(path)
            if path == '/version':
                return 200, b'{"ApiVersion":"1.48","MinAPIVersion":"1.24"}'
            return 200, b'{"stream":"Successfully built deadbeef\\n"}\n'

    client = FakeDockerEngineClient()
    client.build(tmp_path, 'localhost:5000/example:1.0.0', platform='linux/amd64')
    assert client.paths[0] == '/version'
    assert client.paths[1].startswith('/v1.48/build?')
    assert 'version=2' in client.paths[1]


def test_docker_http_error_extracts_daemon_message() -> None:
    text = DockerEngineClient._http_error_message('Docker build', 400, '{"message":"client version is too old"}')
    assert text == 'Docker build failed: HTTP 400: client version is too old'


def test_build_center_persists_engine_api_failure_diagnostics(monkeypatch, tmp_path: Path) -> None:
    import app.services.build_center_service as build_center_module

    class FakeDB:
        def __init__(self) -> None:
            self.commits = 0

        def commit(self) -> None:
            self.commits += 1

    class FakeJob:
        current_stage = ''
        build_logs = []

    class FailingDockerEngineClient:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        def build(self, *args, **kwargs):
            raise DockerEngineError('Docker build failed: HTTP 400: daemon rejected build')

    service = BuildCenterService.__new__(BuildCenterService)
    service.db = FakeDB()
    monkeypatch.setattr(service, '_log_docker_context', lambda job, source: None)
    monkeypatch.setattr(service, '_use_docker_cli', lambda: False)
    monkeypatch.setattr(build_center_module, 'DockerEngineClient', FailingDockerEngineClient)
    job = FakeJob()

    try:
        service._docker_build(job, tmp_path, 'localhost:5000/example:1.0.0', '1.0.0', 'deadbeef')
    except Exception as exc:
        assert getattr(exc, 'message', '') == 'Docker Engine API 构建失败'
    else:  # pragma: no cover
        raise AssertionError('expected build failure')

    assert job.current_stage == 'DOCKER_BUILD_API'
    assert job.build_logs[-1]['exitCode'] == 1
    assert 'daemon rejected build' in job.build_logs[-1]['message']
    assert service.db.commits == 1
