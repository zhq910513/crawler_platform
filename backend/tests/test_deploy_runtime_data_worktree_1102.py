from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_deploy_runtime_paths_are_filtered_from_git_cleanliness_check() -> None:
    host = (ROOT / 'deploy/scripts/lib/host.sh').read_text(encoding='utf-8')
    remote = (ROOT / 'deploy/scripts/remote-auto-deploy.sh').read_text(encoding='utf-8')
    workflow = (ROOT / '.github/workflows/deploy-test-server.yml').read_text(encoding='utf-8')
    gitignore = (ROOT / '.gitignore').read_text(encoding='utf-8')

    assert 'cp_git_register_deploy_runtime_excludes()' in host
    assert 'cp_git_status_deploy_relevant()' in host
    assert 'data/' in host and '.release/' in host
    assert 'cp_git_register_deploy_runtime_excludes' in remote
    assert '真实未提交源码改动' in remote
    assert 'data/ .release/ agent/state.json crawler_agent.env' in workflow
    assert 'relevant_status' in workflow
    assert 'data/project-builds/*' in gitignore


def test_git_status_filter_ignores_runtime_data_but_blocks_source_files(tmp_path: Path) -> None:
    subprocess.run(['git', 'init'], cwd=tmp_path, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['git', 'config', 'user.email', 'ci@example.invalid'], cwd=tmp_path, check=True)
    subprocess.run(['git', 'config', 'user.name', 'CI'], cwd=tmp_path, check=True)
    (tmp_path / 'tracked.txt').write_text('ok\n', encoding='utf-8')
    subprocess.run(['git', 'add', 'tracked.txt'], cwd=tmp_path, check=True)
    subprocess.run(['git', 'commit', '-m', 'init'], cwd=tmp_path, check=True, stdout=subprocess.DEVNULL)

    runtime_file = tmp_path / 'data' / 'project-builds' / 'build-1' / 'log.txt'
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_text('runtime\n', encoding='utf-8')

    script = f"""
set -Eeuo pipefail
. '{ROOT / 'deploy/scripts/lib/host.sh'}'
cp_git_register_deploy_runtime_excludes
cp_git_status_deploy_relevant
"""
    clean = subprocess.run(['bash', '-lc', script], cwd=tmp_path, check=True, text=True, capture_output=True)
    assert clean.stdout.strip() == ''

    (tmp_path / 'untracked_source.py').write_text('print(1)\n', encoding='utf-8')
    dirty = subprocess.run(['bash', '-lc', script], cwd=tmp_path, check=True, text=True, capture_output=True)
    assert '?? untracked_source.py' in dirty.stdout
