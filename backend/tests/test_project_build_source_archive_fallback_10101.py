from __future__ import annotations

from io import BytesIO
import subprocess
import tarfile

from test_rebuild_contract import migrate
from app.db import SessionLocal
from app.models import CrawlerProjectBuildJob
from app.services.build_center_service import BuildCenterService
import app.services.build_center_service as build_center_module


def _job() -> CrawlerProjectBuildJob:
    return CrawlerProjectBuildJob(
        company_id=1,
        repository_url='https://github.com/zhq910513/crawler_platform_spiders.git',
        ref_name='main',
        build_status='RUNNING',
        current_stage='CLONE',
        build_logs=[],
        build_metadata={},
    )


def _tar_bytes() -> bytes:
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tf:
        root = 'crawler_platform_spiders-1234567890abcdef'
        version_data = b'1.0.17\n'
        info = tarfile.TarInfo(f'{root}/VERSION')
        info.size = len(version_data)
        tf.addfile(info, BytesIO(version_data))
        script_data = b'#!/usr/bin/env bash\n'
        info = tarfile.TarInfo(f'{root}/scripts/platform_build_contract.sh')
        info.size = len(script_data)
        tf.addfile(info, BytesIO(script_data))
    return buf.getvalue()


class _Resp:
    def __init__(self, payload: bytes):
        self._payload = BytesIO(payload)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False

    def read(self, size: int = -1) -> bytes:
        return self._payload.read(size)


def test_git_clone_failure_falls_back_to_github_source_archive(monkeypatch, tmp_path) -> None:
    migrate()
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_attempts', 1)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_retry_seconds', 0)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_timeout_seconds', 30)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_archive_fallback_enabled', True)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_archive_attempts', 1)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_archive_timeout_seconds', 30)

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        return subprocess.CompletedProcess(cmd, 128, '', 'fatal: unable to access repo: Could not connect to server')

    requested: list[str] = []

    def fake_urlopen(request, timeout=0):  # noqa: ANN001
        requested.append(request.full_url)
        return _Resp(_tar_bytes())

    monkeypatch.setattr(build_center_module.subprocess, 'run', fake_run)
    monkeypatch.setattr(build_center_module, 'urlopen', fake_urlopen)
    with SessionLocal() as db:
        job = _job()
        db.add(job)
        db.commit()
        source = tmp_path / 'source'
        BuildCenterService(db)._git_clone_source(job, source=source, cwd=tmp_path)
        assert (source / 'VERSION').read_text(encoding='utf-8').strip() == '1.0.17'
        assert requested and 'codeload.github.com' in requested[0]
        assert any(item['stage'] == 'SOURCE_ARCHIVE' and '兜底成功' in item['message'] for item in job.build_logs)
        assert job.build_metadata['sourceArchiveCommit'].startswith('1234567890ab')
