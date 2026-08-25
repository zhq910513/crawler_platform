from __future__ import annotations

from fastapi.testclient import TestClient

from test_rebuild_contract import app, login, migrate
from app.models import CrawlerProjectBuildJob
from app.schemas import ProjectManifest
from app.services.build_center_service import BuildCenterReadiness, BuildCenterService
from app.utils import utcnow


def _ready() -> BuildCenterReadiness:
    return BuildCenterReadiness(
        enabled=True,
        implemented=True,
        mode="PLATFORM_BUILD_CENTER_READY",
        blocked_reason_code="",
        missing_items=(),
        message="平台构建中心已启用",
        next_actions=("点击发布项目后自动构建",),
    )


def test_project_publish_pipeline_starts_async_build_job_without_waiting(monkeypatch) -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'build_center_1092', 'companyName': '构建中心公司1092'}).json()['data']
    server = client.post('/api/v1/servers', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'build-center-1092-srv', 'serverName': '构建中心1092节点'}).json()['data']
    agent = client.post('/api/v1/agents', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'build-center-1092-srv', 'serverName': '构建中心1092节点', 'agentCode': 'build-center-1092-agent', 'agentName': '构建中心1092 Agent'}).json()['data']
    client.post('/api/v1/agent-heartbeats', headers={'Authorization': 'Agent ' + agent['agentToken']}, json={'agentInstanceId': 'build-center-1092-inst', 'dockerStatus': 'OK', 'availableSlots': 2, 'runningContainers': 0, 'hostIp': '10.92.0.10'})

    def fake_readiness(self):
        return _ready()

    def fake_start(self, user, company_id: int, repository_url: str, ref_name: str = 'main'):
        job = CrawlerProjectBuildJob(
            company_id=company_id,
            repository_url=repository_url,
            ref_name=ref_name,
            project_code='spider_build_1092',
            release_version='',
            image_repository='',
            image_digest='',
            git_commit='',
            build_status='PENDING',
            current_stage='QUEUED',
            build_logs=[{'stage': 'QUEUED', 'message': 'mock build queued'}],
            build_metadata={'mocked': True},
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    monkeypatch.setattr(BuildCenterService, 'spider_project_readiness', fake_readiness)
    monkeypatch.setattr(BuildCenterService, 'start_project_release_build', fake_start)

    payload = {'companyId': company['companyId'], 'serverIds': [server['serverId']], 'repositoryUrl': 'https://github.com/zhq910513/spider_build_1092.git', 'refName': 'main'}
    analysis = client.post('/api/v1/project-publish/pipeline-analyses', headers=headers, json=payload).json()['data']
    assert analysis['pipelineStatus'] == 'READY_TO_PUBLISH'
    build_step = next(item for item in analysis['steps'] if item['key'] == 'build')
    assert build_step['data']['mode'] == 'PLATFORM_BUILD_CENTER_READY'

    result = client.post('/api/v1/project-publish/pipelines', headers=headers, json=payload).json()['data']
    assert result['pipelineStatus'] == 'BUILDING'
    assert result['buildJob']['buildStatus'] == 'PENDING'
    assert result['buildJob']['currentStage'] == 'QUEUED'
    build_step = next(item for item in result['steps'] if item['key'] == 'build')
    assert build_step['status'] == 'process'


def test_project_build_job_list_endpoint_is_company_scoped(monkeypatch) -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'build_job_list_1092', 'companyName': '构建任务公司1092'}).json()['data']
    from app.db import SessionLocal
    with SessionLocal() as db:
        job = CrawlerProjectBuildJob(company_id=company['companyId'], repository_url='https://example.com/repo.git', ref_name='main', build_status='FAILED', current_stage='CLONE', error_message='mock')
        db.add(job)
        db.commit()
        job_id = job.build_job_id
    data = client.get('/api/v1/project-builds', headers=headers, params={'companyId': company['companyId']}).json()['data']
    assert any(item['buildJobId'] == job_id for item in data)
    detail = client.get(f'/api/v1/project-builds/{job_id}', headers=headers).json()['data']
    assert detail['errorMessage'] == 'mock'
