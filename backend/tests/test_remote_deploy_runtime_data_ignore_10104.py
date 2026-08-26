from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_data_directories_are_ignored_by_git(tmp_path: Path) -> None:
    gitignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
    assert 'data/' in gitignore
    assert 'data/mysql/*' not in gitignore
    (tmp_path / '.gitignore').write_text(gitignore, encoding='utf-8')
    subprocess.run(['git', 'init'], cwd=tmp_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    result = subprocess.run(
        ['git', 'check-ignore', 'data/project-builds/build-1/source/file.py'],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stderr


def test_remote_deploy_bootstraps_runtime_excludes_before_status_gate() -> None:
    host = (ROOT / 'deploy/scripts/lib/host.sh').read_text(encoding='utf-8')
    remote = (ROOT / 'deploy/scripts/remote-auto-deploy.sh').read_text(encoding='utf-8')
    workflow = (ROOT / '.github/workflows/deploy-test-server.yml').read_text(encoding='utf-8')

    assert 'cp_git_ensure_runtime_excludes()' in host
    assert '/data/' in host
    assert 'cp_git_ensure_runtime_excludes || true' in remote
    assert 'git status --porcelain' in workflow
    assert '# crawler_platform runtime excludes: begin' in workflow
    assert '/data/' in workflow
    assert workflow.index('# crawler_platform runtime excludes: begin') < workflow.index('git status --porcelain')
