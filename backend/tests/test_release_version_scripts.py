from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1].parent


def test_release_version_scripts_do_not_require_host_python_or_npm() -> None:
    for relative in [
        'deploy/scripts/resolve-release-version.sh',
        'deploy/scripts/sync-runtime-version.sh',
        'deploy/scripts/check-version-consistency.sh',
        'deploy/scripts/release-upgrade.sh',
        'deploy/scripts/remote-auto-deploy.sh',
    ]:
        source = (ROOT / relative).read_text(encoding='utf-8')
        assert not any(line.lstrip().startswith('npm ') for line in source.splitlines())
        assert not any(line.lstrip().startswith('python3 ') for line in source.splitlines())
        assert not any(line.lstrip().startswith('jq ') for line in source.splitlines())


def test_common_shell_version_module_documents_priority() -> None:
    source = (ROOT / 'deploy/scripts/lib/version.sh').read_text(encoding='utf-8')
    assert 'cp_resolve_release_version' in source
    assert 'git tag --points-at HEAD' in source
    assert 'git log -1 --pretty=%s' in source
    assert 'VERSION' in source
    assert re.search(r'[0-9]\+\\\.[0-9]\+\\\.[0-9]\+', source) or '([0-9]+\\.[0-9]+\\.[0-9]+)' in source


def test_health_exposes_release_metadata() -> None:
    source = (ROOT / 'backend/app/main.py').read_text(encoding='utf-8')
    for field in ['gitCommit', 'buildTime', 'migrationVersion']:
        assert field in source
    assert 'SELECT *' not in source.upper()


def test_backend_agent_frontend_use_shared_release_contract() -> None:
    backend_version = (ROOT / 'backend/app/version.py').read_text(encoding='utf-8')
    backend_config = (ROOT / 'backend/app/config.py').read_text(encoding='utf-8')
    agent_version = (ROOT / 'agent/crawler_agent/version.py').read_text(encoding='utf-8')
    agent_config = (ROOT / 'agent/crawler_agent/config.py').read_text(encoding='utf-8')
    frontend_version = (ROOT / 'frontend/src/config/version.ts').read_text(encoding='utf-8')
    frontend_dockerfile = (ROOT / 'frontend/Dockerfile').read_text(encoding='utf-8')

    assert 'def release_metadata' in backend_version
    assert 'default_factory=default_version' in backend_config
    assert 'def release_metadata' in agent_version
    assert 'default_factory=default_version' in agent_config
    assert 'VITE_APP_VERSION' in frontend_version
    assert 'version.json' in frontend_dockerfile


def test_frontend_dockerfile_injects_package_version_after_copy_all() -> None:
    lines = (ROOT / 'frontend/Dockerfile').read_text(encoding='utf-8').splitlines()
    copy_all = max(index for index, line in enumerate(lines, start=1) if line.strip() == 'COPY . .')
    npm_version = max(index for index, line in enumerate(lines, start=1) if 'npm version "$APP_VERSION"' in line)
    assert npm_version > copy_all
