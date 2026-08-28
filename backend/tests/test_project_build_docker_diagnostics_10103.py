from __future__ import annotations

from pathlib import Path

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
