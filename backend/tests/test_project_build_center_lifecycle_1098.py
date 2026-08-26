from __future__ import annotations

from fastapi.testclient import TestClient

from test_rebuild_contract import app, login, migrate
from app.db import SessionLocal
from app.models import CrawlerProjectBuildJob
from app.services.build_center_service import BuildCenterReadiness, BuildCenterService
import app.services.build_center_service as build_center_module


def _ready(self: BuildCenterService) -> BuildCenterReadiness:  # noqa: ARG001
    return BuildCenterReadiness(
        enabled=True,
        implemented=True,
        mode="PLATFORM_BUILD_CENTER_READY",
        blocked_reason_code="",
        missing_items=(),
        message="平台构建中心已启用",
        next_actions=("点击发布项目后自动构建",),
        diagnostics={"selectedExecutor": "TEST"},
    )


def _company(client: TestClient, headers: dict, code: str) -> dict:
    return client.post('/api/v1/companies', headers=headers, json={'companyCode': code, 'companyName': code}).json()['data']


def test_pending_build_job_poll_auto_resumes(monkeypatch) -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = _company(client, headers, 'build_lifecycle_resume_1098')
    with SessionLocal() as db:
        job = CrawlerProjectBuildJob(
            company_id=company['companyId'],
            repository_url='https://github.com/zhq910513/crawler_platform_spiders.git',
            ref_name='main',
            build_status='PENDING',
            current_stage='QUEUED',
            build_logs=[],
            build_metadata={'executionMode': 'ASYNC_BACKGROUND_THREAD'},
        )
        db.add(job)
        db.commit()
        job_id = job.build_job_id

    started: list[int] = []
    monkeypatch.setattr(build_center_module, 'start_project_release_build_thread', lambda build_job_id, user_id=None: started.append(build_job_id))
    data = client.get(f'/api/v1/project-builds/{job_id}', headers=headers).json()['data']

    assert started == [job_id]
    assert data['buildStatus'] == 'PENDING'
    assert data['canCancel'] is True
    assert data['canRetry'] is False
    assert data['isTerminal'] is False
    assert any(item['stage'] == 'QUEUED' for item in data['buildLogs'])


def test_build_job_cancel_and_retry_uses_new_job(monkeypatch) -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = _company(client, headers, 'build_lifecycle_cancel_1098')
    with SessionLocal() as db:
        job = CrawlerProjectBuildJob(
            company_id=company['companyId'],
            repository_url='https://github.com/zhq910513/crawler_platform_spiders.git',
            ref_name='main',
            build_status='PENDING',
            current_stage='QUEUED',
            build_logs=[],
            build_metadata={'executionMode': 'ASYNC_BACKGROUND_THREAD'},
        )
        db.add(job)
        db.commit()
        job_id = job.build_job_id

    started: list[int] = []
    monkeypatch.setattr(build_center_module, 'start_project_release_build_thread', lambda build_job_id, user_id=None: started.append(build_job_id))
    monkeypatch.setattr(BuildCenterService, 'spider_project_readiness', _ready)

    canceled = client.post(f'/api/v1/project-builds/{job_id}/cancellations', headers=headers, json={'reason': '测试取消'}).json()['data']['buildJob']
    assert canceled['buildStatus'] == 'CANCELED'
    assert canceled['canRetry'] is True
    assert canceled['errorMessage'] == '测试取消'

    retried = client.post(f'/api/v1/project-builds/{job_id}/retries', headers=headers).json()['data']['buildJob']
    assert retried['buildJobId'] != job_id
    assert retried['buildStatus'] == 'PENDING'
    assert retried['buildMetadata']['retryOfBuildJobId'] == job_id
    assert started[-1] == retried['buildJobId']
