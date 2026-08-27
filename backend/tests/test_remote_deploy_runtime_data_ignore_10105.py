from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_exclude_block_is_repaired_when_old_marker_exists() -> None:
    host = (ROOT / 'deploy' / 'scripts' / 'lib' / 'host.sh').read_text(encoding='utf-8')
    assert 'cp_ensure_runtime_data_git_excludes' in host
    assert '# BEGIN CRAWLER_PLATFORM_RUNTIME_DATA_EXCLUDES' in host
    assert 'data/mysql/*' in host  # legacy patterns are explicitly removed when repairing .gitignore
    gitignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
    assert 'data/*' in gitignore
    assert 'data/mysql/*' not in gitignore


def test_remote_deploy_uses_filtered_status_for_dirty_workspace_gate() -> None:
    remote = (ROOT / 'deploy' / 'scripts' / 'remote-auto-deploy.sh').read_text(encoding='utf-8')
    workflow = (ROOT / '.github' / 'workflows' / 'deploy-test-server.yml').read_text(encoding='utf-8')
    assert 'cp_git_status_filtered' in remote
    assert '.git/info/exclude' in workflow
    assert 'filtered_status' in workflow
