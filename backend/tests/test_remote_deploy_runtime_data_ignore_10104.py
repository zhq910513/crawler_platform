from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_data_directories_are_ignored_by_git() -> None:
    gitignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
    assert '# BEGIN CRAWLER_PLATFORM_RUNTIME_DATA_EXCLUDES' in gitignore
    assert 'data/*' in gitignore
    assert '!data/**/.gitkeep' in gitignore
    assert 'data/mysql/*' not in gitignore
    assert 'data/project-builds/*' not in gitignore


def test_remote_deploy_bootstraps_runtime_excludes_before_status_gate() -> None:
    workflow = (ROOT / '.github' / 'workflows' / 'deploy-test-server.yml').read_text(encoding='utf-8')
    script = (ROOT / 'deploy' / 'scripts' / 'remote-auto-deploy.sh').read_text(encoding='utf-8')
    host = (ROOT / 'deploy' / 'scripts' / 'lib' / 'host.sh').read_text(encoding='utf-8')
    assert '.git/info/exclude' in workflow
    assert 'ensure_runtime_data_ignore' in workflow
    assert 'filtered_status' in workflow
    assert 'script_stop:' not in workflow
    assert script.index('cp_ensure_runtime_data_git_excludes') < script.index('cp_git_restore_mode_only_changes')
    assert 'cp_git_status_filtered' in host
