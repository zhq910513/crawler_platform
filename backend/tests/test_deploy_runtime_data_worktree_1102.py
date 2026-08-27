from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_git_status_filter_ignores_runtime_data_but_blocks_source_files(tmp_path: Path) -> None:
    if shutil.which('git') is None:
        pytest.skip('git is not installed in the lightweight Python tool image')
    subprocess.run(['git', 'init'], cwd=tmp_path, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['git', 'config', 'user.email', 'ci@example.invalid'], cwd=tmp_path, check=True)
    subprocess.run(['git', 'config', 'user.name', 'CI'], cwd=tmp_path, check=True)
    (tmp_path / 'deploy/scripts/lib').mkdir(parents=True)
    helper = ROOT / 'deploy' / 'scripts' / 'lib' / 'host.sh'
    (tmp_path / 'deploy/scripts/lib/host.sh').write_text(helper.read_text(encoding='utf-8'), encoding='utf-8')
    (tmp_path / 'README.md').write_text('ok\n', encoding='utf-8')
    subprocess.run(['git', 'add', '.'], cwd=tmp_path, check=True)
    subprocess.run(['git', 'commit', '-m', 'init'], cwd=tmp_path, check=True, stdout=subprocess.DEVNULL)
    (tmp_path / 'data/mysql').mkdir(parents=True)
    (tmp_path / 'data/mysql/db.ibd').write_text('runtime\n', encoding='utf-8')
    status = subprocess.check_output(['bash', '-lc', '. deploy/scripts/lib/host.sh; cp_ensure_runtime_data_git_excludes; cp_git_status_filtered'], cwd=tmp_path, text=True)
    assert 'data/' not in status
    (tmp_path / 'backend').mkdir()
    (tmp_path / 'backend/new_code.py').write_text('print(1)\n', encoding='utf-8')
    status = subprocess.check_output(['bash', '-lc', '. deploy/scripts/lib/host.sh; cp_git_status_filtered'], cwd=tmp_path, text=True)
    assert 'backend/new_code.py' in status
