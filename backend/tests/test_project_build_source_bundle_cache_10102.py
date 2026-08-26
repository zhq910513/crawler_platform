from __future__ import annotations

from io import BytesIO
import subprocess
import tarfile

from test_rebuild_contract import migrate
from app.db import SessionLocal
from app.models import CrawlerProjectBuildJob, SysUser
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


def _tar_bytes(version: str = '1.0.17') -> bytes:
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as tf:
        root = 'crawler_platform_spiders-bundle'
        version_data = f'{version}\n'.encode()
        info = tarfile.TarInfo(f'{root}/VERSION')
        info.size = len(version_data)
        tf.addfile(info, BytesIO(version_data))
        script_data = b'#!/usr/bin/env bash\n'
        info = tarfile.TarInfo(f'{root}/scripts/platform_build_contract.sh')
        info.size = len(script_data)
        tf.addfile(info, BytesIO(script_data))
    return buf.getvalue()


def test_uploaded_source_bundle_fallback_when_github_unreachable(monkeypatch, tmp_path) -> None:
    migrate()
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_attempts', 1)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_retry_seconds', 0)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_timeout_seconds', 30)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_archive_fallback_enabled', False)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_bundle_upload_enabled', True)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_bundle_root', tmp_path / 'bundles')
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_bundle_max_bytes', 10 * 1024 * 1024)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_cache_enabled', False)

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        return subprocess.CompletedProcess(cmd, 128, '', 'fatal: unable to access repo: Could not connect to server')

    monkeypatch.setattr(build_center_module.subprocess, 'run', fake_run)
    with SessionLocal() as db:
        service = BuildCenterService(db)
        user = SysUser(user_id=7, user_name='admin', nick_name='admin', password_hash='x')
        saved = service.save_source_bundle(user, 1, 'https://github.com/zhq910513/crawler_platform_spiders.git', 'main', 'spiders.tar.gz', _tar_bytes())
        assert saved['sizeBytes'] > 0
        job = _job()
        db.add(job)
        db.commit()
        source = tmp_path / 'source'
        service._git_clone_source(job, source=source, cwd=tmp_path)
        assert (source / 'VERSION').read_text(encoding='utf-8').strip() == '1.0.17'
        assert any(item['stage'] == 'SOURCE_BUNDLE' and '兜底成功' in item['message'] for item in job.build_logs)


def test_source_cache_fallback_when_all_remote_sources_unavailable(monkeypatch, tmp_path) -> None:
    migrate()
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_attempts', 1)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_retry_seconds', 0)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_timeout_seconds', 30)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_archive_fallback_enabled', False)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_bundle_upload_enabled', False)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_cache_enabled', True)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_cache_root', tmp_path / 'cache')

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        return subprocess.CompletedProcess(cmd, 128, '', 'fatal: unable to access repo: Could not connect to server')

    monkeypatch.setattr(build_center_module.subprocess, 'run', fake_run)
    with SessionLocal() as db:
        service = BuildCenterService(db)
        job_for_cache = _job()
        job_for_cache.build_job_id = 991
        src = tmp_path / 'seed-source'
        (src / 'scripts').mkdir(parents=True)
        (src / 'VERSION').write_text('1.0.17\n', encoding='utf-8')
        (src / 'scripts' / 'platform_build_contract.sh').write_text('#!/usr/bin/env bash\n', encoding='utf-8')
        service._store_source_cache(job_for_cache, src)

        job = _job()
        db.add(job)
        db.commit()
        source = tmp_path / 'source'
        service._git_clone_source(job, source=source, cwd=tmp_path)
        assert (source / 'VERSION').read_text(encoding='utf-8').strip() == '1.0.17'
        assert any(item['stage'] == 'SOURCE_CACHE' and '使用最近成功源码缓存兜底' in item['message'] for item in job.build_logs)
