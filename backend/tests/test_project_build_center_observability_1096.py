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


def test_publish_pipeline_returns_build_job_logs_when_platform_build_fails(monkeypatch) -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'build_obs_1096', 'companyName': '构建可观测公司1096'}).json()['data']
    server = client.post('/api/v1/servers', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'build-obs-1096-srv', 'serverName': '构建可观测1096节点'}).json()['data']
    agent = client.post('/api/v1/agents', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'build-obs-1096-srv', 'serverName': '构建可观测1096节点', 'agentCode': 'build-obs-1096-agent', 'agentName': '构建可观测1096 Agent'}).json()['data']
    client.post('/api/v1/agent-heartbeats', headers={'Authorization': 'Agent ' + agent['agentToken']}, json={'agentInstanceId': 'build-obs-1096-inst', 'dockerStatus': 'OK', 'availableSlots': 2, 'runningContainers': 0, 'hostIp': '10.96.0.10'})

    def fake_readiness(self):
        return _ready()

    def fake_build(self, user, company_id: int, repository_url: str, ref_name: str = 'main'):
        raise AppError(
            'Docker Engine API 构建失败',
            code=40102,
            data={
                'buildJob': {
                    'build_job_id': 9601,
                    'company_id': company_id,
                    'build_status': 'FAILED',
                    'current_stage': 'DOCKER_BUILD_API',
                    'error_message': 'Docker Engine API 构建失败',
                    'build_logs': [{'stage': 'DOCKER_BUILD_API', 'message': 'mock docker build error', 'exitCode': 1}],
                }
            },
        )

    monkeypatch.setattr(BuildCenterService, 'spider_project_readiness', fake_readiness)
    monkeypatch.setattr(BuildCenterService, 'build_project_release', fake_build)

    payload = {'companyId': company['companyId'], 'serverIds': [server['serverId']], 'repositoryUrl': 'https://github.com/zhq910513/build_obs_1096.git', 'refName': 'main'}
    response = client.post('/api/v1/project-publish/pipelines', headers=headers, json=payload)
    assert response.status_code == 400
    body = response.json()
    data = body['data']
    assert body['message'] == 'Docker Engine API 构建失败'
    assert data['pipelineStatus'] == 'BLOCKED'
    build_step = next(item for item in data['steps'] if item['key'] == 'build')
    assert build_step['status'] == 'error'
    assert data['buildJob']['buildStatus'] == 'FAILED'
    assert data['buildJob']['buildLogs'][0]['message'] == 'mock docker build error'


def test_build_center_readiness_exposes_executor_diagnostics() -> None:
    migrate()
    with SessionLocal() as db:
        payload = BuildCenterService(db).spider_project_readiness().asdict()
    diagnostics = payload['diagnostics']
    for key in ['gitAvailable', 'dockerCliAvailable', 'dockerSocketPath', 'dockerSocketExists', 'dockerEngineApiAvailable', 'dockerExecutorAvailable', 'selectedExecutor', 'imageRepositoryPrefix', 'buildRoot']:
        assert key in diagnostics
