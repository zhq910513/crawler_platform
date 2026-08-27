from __future__ import annotations

import subprocess
import json
import zipfile

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
    monkeypatch.setattr(build_center_module.shutil, 'which', lambda name: '/usr/bin/git' if name == 'git' else None)
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
    monkeypatch.setattr(build_center_module.shutil, 'which', lambda name: '/usr/bin/git' if name == 'git' else None)

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



def test_git_missing_uses_local_source_bundle_fallback(monkeypatch, tmp_path) -> None:
    migrate()
    bundle_dir = tmp_path / 'bundles'
    bundle_dir.mkdir()
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_bundle_dir', bundle_dir)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_archive_fallback_enabled', False)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_cache_enabled', False)
    monkeypatch.setattr(build_center_module.shutil, 'which', lambda name: None)

    bundle = bundle_dir / 'crawler_platform_spiders__main.zip'
    with zipfile.ZipFile(bundle, 'w') as zf:
        zf.writestr('crawler_platform_spiders-main/VERSION', '1.0.17')
        zf.writestr('crawler_platform_spiders-main/scripts/platform_build_contract.sh', '#!/usr/bin/env bash\n')

    with SessionLocal() as db:
        job = _job()
        db.add(job)
        db.commit()
        source = tmp_path / 'source'
        BuildCenterService(db)._git_clone_source(job, source=source, cwd=tmp_path)
        assert (source / 'VERSION').read_text(encoding='utf-8') == '1.0.17'
        assert any(item['stage'] == 'CLONE_SKIP' for item in job.build_logs)
        assert any(item['stage'] == 'SOURCE_BUNDLE' for item in job.build_logs)


def test_git_and_archive_failure_can_use_source_cache(monkeypatch, tmp_path) -> None:
    migrate()
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_archive_fallback_enabled', False)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_cache_enabled', True)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_cache_root', tmp_path / 'cache')
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_bundle_dir', tmp_path / 'missing-bundles')
    monkeypatch.setattr(build_center_module.shutil, 'which', lambda name: None)

    job = _job()
    cache = (tmp_path / 'cache') / BuildCenterService.__new__(BuildCenterService)._source_key(job.repository_url, job.ref_name)
    cache.mkdir(parents=True)
    (cache / 'VERSION').write_text('1.0.17', encoding='utf-8')
    (cache / 'scripts').mkdir()
    (cache / 'scripts' / 'platform_build_contract.sh').write_text('#!/usr/bin/env bash\n', encoding='utf-8')
    (cache / '.crawler_source_cache.json').write_text(json.dumps({'gitCommit': 'cache-main'}), encoding='utf-8')

    with SessionLocal() as db:
        db.add(job)
        db.commit()
        source = tmp_path / 'source'
        BuildCenterService(db)._git_clone_source(job, source=source, cwd=tmp_path)
        assert (source / 'VERSION').read_text(encoding='utf-8') == '1.0.17'
        assert 'sourceCacheCommit' in (job.build_metadata or {})
        assert any(item['stage'] == 'SOURCE_CACHE' for item in job.build_logs)
