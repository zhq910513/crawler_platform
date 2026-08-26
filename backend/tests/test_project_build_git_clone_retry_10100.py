from __future__ import annotations

import subprocess

from test_rebuild_contract import migrate
from app.db import SessionLocal
from app.models import CrawlerProjectBuildJob
from app.services.build_center_service import BuildCenterService
from app.errors import AppError
import app.services.build_center_service as build_center_module


def _job() -> CrawlerProjectBuildJob:
    return CrawlerProjectBuildJob(
        company_id=1,
        repository_url='https://github.com/zhq910513/crawler_platform_spiders.git',
        ref_name='main',
        build_status='RUNNING',
        current_stage='CLONE',
        build_logs=[],
    )


def test_git_clone_retries_transient_tls_failure(monkeypatch, tmp_path) -> None:
    migrate()
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_attempts', 2)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_retry_seconds', 0)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_timeout_seconds', 30)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_archive_fallback_enabled', False)
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        calls.append(list(cmd))
        if len(calls) == 1:
            return subprocess.CompletedProcess(cmd, 128, '', "fatal: unable to access 'https://github.com/zhq910513/crawler_platform_spiders.git/': GnuTLS recv error (-110): The TLS connection was non-properly terminated.")
        return subprocess.CompletedProcess(cmd, 0, '', "Cloning into 'source'...")

    monkeypatch.setattr(build_center_module.subprocess, 'run', fake_run)
    with SessionLocal() as db:
        job = _job()
        db.add(job)
        db.commit()
        BuildCenterService(db)._git_clone_source(job, source=tmp_path / 'source', cwd=tmp_path)
        assert len(calls) == 2
        assert any('-c' in call and 'http.version=HTTP/1.1' in call for call in calls)
        assert any(item['stage'] == 'CLONE_RETRY' for item in job.build_logs)


def test_git_clone_failure_exposes_retry_context(monkeypatch, tmp_path) -> None:
    migrate()
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_attempts', 2)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_retry_seconds', 0)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_timeout_seconds', 30)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_archive_fallback_enabled', False)

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        return subprocess.CompletedProcess(cmd, 128, '', 'fatal: unable to access repo: GnuTLS recv error (-110)')

    monkeypatch.setattr(build_center_module.subprocess, 'run', fake_run)
    with SessionLocal() as db:
        job = _job()
        db.add(job)
        db.commit()
        try:
            BuildCenterService(db)._git_clone_source(job, source=tmp_path / 'source', cwd=tmp_path)
        except AppError as exc:
            assert exc.code == 40106
            assert exc.message == '源码拉取失败：Git 网络/TLS 连接异常或仓库不可访问'
            assert exc.data['attempts'] == 2
            assert 'GnuTLS' in exc.data['lastOutput']
            assert exc.data['nextActions']
        else:  # pragma: no cover
            raise AssertionError('expected AppError')
