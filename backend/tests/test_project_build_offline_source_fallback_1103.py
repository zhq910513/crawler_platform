from __future__ import annotations

from io import BytesIO
import tarfile
import zipfile

from test_rebuild_contract import migrate
from app.db import SessionLocal
from types import SimpleNamespace
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


def _zip_payload(version: str = '1.0.17') -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('crawler_platform_spiders-main/VERSION', version + '\n')
        zf.writestr('crawler_platform_spiders-main/scripts/platform_build_contract.sh', '#!/usr/bin/env bash\n')
    return buf.getvalue()


def _tar_cache(path, version: str = '1.0.18') -> None:  # noqa: ANN001
    with tarfile.open(path, 'w:gz') as tf:
        data = (version + '\n').encode()
        info = tarfile.TarInfo('VERSION')
        info.size = len(data)
        tf.addfile(info, BytesIO(data))
        script = b'#!/usr/bin/env bash\n'
        info = tarfile.TarInfo('scripts/platform_build_contract.sh')
        info.size = len(script)
        tf.addfile(info, BytesIO(script))


def test_uploaded_source_bundle_fallback_when_github_unreachable(monkeypatch, tmp_path) -> None:
    migrate()
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_attempts', 1)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_retry_seconds', 0)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_git_clone_timeout_seconds', 30)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_archive_fallback_enabled', False)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_bundle_upload_enabled', True)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_bundle_dir', tmp_path / 'bundles')
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_cache_enabled', False)

    def fake_run(cmd, **kwargs):  # noqa: ANN001
        from subprocess import CompletedProcess
        return CompletedProcess(cmd, 128, '', 'fatal: unable to access repo')

    monkeypatch.setattr(build_center_module.subprocess, 'run', fake_run)
    with SessionLocal() as db:
        service = BuildCenterService(db)
        user = SimpleNamespace(user_id=1)
        service.save_source_bundle(user, 1, 'https://github.com/zhq910513/crawler_platform_spiders.git', 'main', 'source.zip', _zip_payload())
        job = _job()
        db.add(job)
        db.commit()
        source = tmp_path / 'source'
        service._git_clone_source(job, source=source, cwd=tmp_path)
        assert (source / 'VERSION').read_text(encoding='utf-8').strip() == '1.0.17'
        assert any(item['stage'] == 'SOURCE_BUNDLE' and '已上传源码包' in item['message'] for item in job.build_logs)


def test_source_cache_fallback_when_all_remote_sources_unavailable(monkeypatch, tmp_path) -> None:
    migrate()
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_archive_fallback_enabled', False)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_bundle_upload_enabled', False)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_cache_enabled', True)
    monkeypatch.setattr(build_center_module.settings, 'crawler_project_source_cache_dir', tmp_path / 'cache')
    monkeypatch.setattr(build_center_module.shutil, 'which', lambda name: None if name == 'git' else '/bin/true')
    with SessionLocal() as db:
        service = BuildCenterService(db)
        job = _job()
        key = service._source_key(job.repository_url, job.ref_name)
        cache = tmp_path / 'cache' / f'{key}.tar.gz'
        cache.parent.mkdir(parents=True)
        _tar_cache(cache)
        db.add(job)
        db.commit()
        source = tmp_path / 'source'
        service._git_clone_source(job, source=source, cwd=tmp_path)
        assert (source / 'VERSION').read_text(encoding='utf-8').strip() == '1.0.18'
        assert any(item['stage'] == 'SOURCE_CACHE' and '本地源码缓存' in item['message'] for item in job.build_logs)
