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


def test_ci_and_docs_do_not_use_test_prefixed_server_secrets() -> None:
    checked = [
        ROOT / '.github/workflows/deploy-test-server.yml',
        ROOT / 'docs/auto-deploy-test-server.md',
        ROOT / 'backend/app/services/alert_service.py',
    ]
    for path in checked:
        source = path.read_text(encoding='utf-8')
        assert ('TE' + 'ST_SERVER_') not in source
        assert ('TE' + 'ST_NOTIFICATION_CHANNEL') not in source

    workflow = (ROOT / '.github/workflows/deploy-test-server.yml').read_text(encoding='utf-8')
    for secret in ['SERVER_HOST', 'SERVER_USER', 'SERVER_SSH_KEY', 'SERVER_PORT', 'SERVER_PROJECT_DIR']:
        assert f'secrets.{secret}' in workflow


def test_remote_auto_deploy_recovers_mode_only_changes_without_reset_hard() -> None:
    host = (ROOT / 'deploy/scripts/lib/host.sh').read_text(encoding='utf-8')
    remote = (ROOT / 'deploy/scripts/remote-auto-deploy.sh').read_text(encoding='utf-8')
    contract = (ROOT / 'deploy/scripts/check-deploy-worktree-contract.py').read_text(encoding='utf-8')

    assert 'cp_git_restore_mode_only_changes()' in host
    assert 'cp_git_status_deploy_relevant()' in host
    assert 'cp_git_register_deploy_runtime_excludes()' in host
    assert 'core.fileMode=false' in host
    assert 'git reset -q HEAD -- .' in host
    assert 'git checkout -q -- .' in host
    assert 'data/' in host and '.release/' in host
    assert 'git reset --hard' not in host
    assert 'chmod +x deploy/scripts/*.sh' not in host
    assert 'chmod +x agent/install-linux.sh' not in host
    assert 'cp_git_register_deploy_runtime_excludes' in remote
    assert 'cp_git_restore_mode_only_changes' in remote
    assert '真实未提交源码改动' in remote
    assert '运行期 data/' in remote
    gate = (ROOT / 'deploy/scripts/commercial-release-gate.sh').read_text(encoding='utf-8')
    workflow = (ROOT / '.github/workflows/deploy-test-server.yml').read_text(encoding='utf-8')
    assert 'check-deploy-worktree-contract.py' in gate
    assert 'CI/CD 工作区权限位自愈契约检查' in gate
    assert '内部部署脚本调用应使用 bash' in contract
    assert '检测到仅 Git 文件权限位变化' in workflow
    assert 'core.fileMode=false' in workflow
    assert 'data/ .release/ agent/state.json crawler_agent.env' in workflow
    assert 'relevant_status' in workflow
    assert '[ ! -f deploy/scripts/remote-auto-deploy.sh ]' in workflow
