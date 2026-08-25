from __future__ import annotations

from fastapi.testclient import TestClient

from test_rebuild_contract import app, login, migrate
from app.db import SessionLocal
from app.errors import AppError
from app.services.build_center_service import BuildCenterReadiness, BuildCenterService


def _ready() -> BuildCenterReadiness:
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


def test_project_build_job_detail_returns_failure_logs() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'build_obs_1096', 'companyName': '构建可观测公司1096'}).json()['data']
    from app.models import CrawlerProjectBuildJob
    with SessionLocal() as db:
        job = CrawlerProjectBuildJob(
            company_id=company['companyId'],
            repository_url='https://github.com/zhq910513/build_obs_1096.git',
            ref_name='main',
            build_status='FAILED',
            current_stage='DOCKER_BUILD_API',
            error_message='Docker Engine API 构建失败',
            build_logs=[{'stage': 'DOCKER_BUILD_API', 'message': 'mock docker build error', 'exitCode': 1}],
        )
        db.add(job)
        db.commit()
        job_id = job.build_job_id

    data = client.get(f'/api/v1/project-builds/{job_id}', headers=headers).json()['data']
    assert data['buildStatus'] == 'FAILED'
    assert data['currentStage'] == 'DOCKER_BUILD_API'
    assert data['errorMessage'] == 'Docker Engine API 构建失败'
    assert data['buildLogs'][0]['message'] == 'mock docker build error'


def test_build_center_readiness_exposes_executor_diagnostics() -> None:
    migrate()
    with SessionLocal() as db:
        payload = BuildCenterService(db).spider_project_readiness().asdict()
    diagnostics = payload['diagnostics']
    for key in ['gitAvailable', 'dockerCliAvailable', 'dockerSocketPath', 'dockerSocketExists', 'dockerEngineApiAvailable', 'dockerExecutorAvailable', 'selectedExecutor', 'imageRepositoryPrefix', 'buildRoot']:
        assert key in diagnostics
