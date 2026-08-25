from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_project_build_center_env_defaults_are_auto_enabled() -> None:
    env = (ROOT / '.env.example').read_text(encoding='utf-8')
    config = (ROOT / 'backend' / 'app' / 'config.py').read_text(encoding='utf-8')
    assert 'CRAWLER_PROJECT_BUILD_ENABLED=1' in env
    assert 'os.getenv("CRAWLER_PROJECT_BUILD_ENABLED", "1")' in config
    assert 'CRAWLER_PROJECT_BUILD_ROOT=/data/project-builds' in env


def test_project_build_center_deploy_scripts_auto_configure_env() -> None:
    script = ROOT / 'deploy' / 'scripts' / 'configure-project-build-center.sh'
    assert script.exists()
    content = script.read_text(encoding='utf-8')
    assert 'set_env_value CRAWLER_PROJECT_BUILD_ENABLED 1' in content
    assert 'CRAWLER_PROJECT_IMAGE_REPOSITORY_PREFIX' in content
    assert 'data/project-builds' in content
    for rel in ['sync-runtime-version.sh', 'prepare.sh', 'deploy-single-server.sh']:
        rel_content = (ROOT / 'deploy' / 'scripts' / rel).read_text(encoding='utf-8')
        assert 'configure-project-build-center.sh .env' in rel_content


def test_api_container_has_git_docker_socket_and_build_workspace() -> None:
    dockerfile = (ROOT / 'backend' / 'Dockerfile').read_text(encoding='utf-8')
    compose = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')
    assert 'git docker.io' in dockerfile
    assert '/var/run/docker.sock:/var/run/docker.sock' in compose
    assert './data/project-builds:/data/project-builds' in compose
    assert 'user: "0:0"' in compose


def test_build_center_uses_local_registry_push_for_builtin_registry() -> None:
    service = (ROOT / 'backend' / 'app' / 'services' / 'build_center_service.py').read_text(encoding='utf-8')
    assert 'def _push_image_repository_for' in service
    assert 'localhost:{settings.crawler_agent_registry_port}/crawler_projects' in service
    assert 'Release 对外仓库' in service
