from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOST_SH = ROOT / 'deploy/scripts/lib/host.sh'
WORKFLOW = ROOT / '.github/workflows/deploy-test-server.yml'
REMOTE = ROOT / 'deploy/scripts/remote-auto-deploy.sh'


def test_runtime_exclude_block_is_repaired_when_old_marker_exists(tmp_path: Path) -> None:
    subprocess.run(['git', 'init'], cwd=tmp_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    info = tmp_path / '.git' / 'info' / 'exclude'
    info.write_text(
        '# crawler_platform runtime excludes: begin\n'
        '/frontend/dist/\n'
        '# crawler_platform runtime excludes: end\n',
        encoding='utf-8',
    )
    (tmp_path / 'data' / 'project-builds' / 'build-1').mkdir(parents=True)
    (tmp_path / 'data' / 'project-builds' / 'build-1' / 'source.txt').write_text('runtime', encoding='utf-8')

    cmd = f". {HOST_SH}; cp_git_ensure_runtime_excludes; git check-ignore data/project-builds/build-1/source.txt; cp_git_status_runtime_filtered"
    result = subprocess.run(['bash', '-lc', cmd], cwd=tmp_path, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert result.returncode == 0, result.stderr
    assert 'data/project-builds/build-1/source.txt' in result.stdout
    # The filtered status output should not surface data/ as a real deployment blocker.
    assert '?? data/' not in result.stdout
    assert '/data/' in info.read_text(encoding='utf-8')


def test_remote_deploy_uses_filtered_status_for_dirty_workspace_gate() -> None:
    host = HOST_SH.read_text(encoding='utf-8')
    remote = REMOTE.read_text(encoding='utf-8')
    workflow = WORKFLOW.read_text(encoding='utf-8')

    assert 'cp_git_status_runtime_filtered()' in host
    assert 'cp_git_status_runtime_filtered >&2' in remote
    assert 'git status --short >&2' not in remote
    assert 'cp_status_runtime_filtered()' in workflow
    assert 'if [ -n "$(cp_status_runtime_filtered)" ]; then cp_status_runtime_filtered; exit 1; fi' in workflow
    assert 'marker_begin="# crawler_platform runtime excludes: begin"' in workflow
