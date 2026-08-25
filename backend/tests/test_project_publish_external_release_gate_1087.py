from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from test_rebuild_contract import app, login, migrate

ROOT = Path(__file__).resolve().parents[2]


def test_project_publish_build_blocker_exposes_external_ci_registration_path() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'external_ci_1087', 'companyName': '外部CI公司1087'}).json()['data']
    server = client.post('/api/v1/servers', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'external-ci-srv', 'serverName': '外部CI节点'}).json()['data']
    agent = client.post('/api/v1/agents', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'external-ci-srv', 'serverName': '外部CI节点', 'agentCode': 'external-ci-agent', 'agentName': '外部CI Agent'}).json()['data']
    client.post('/api/v1/agent-heartbeats', headers={'Authorization': 'Agent ' + agent['agentToken']}, json={'agentInstanceId': 'external-ci-inst', 'dockerStatus': 'OK', 'availableSlots': 2, 'runningContainers': 0})

    payload = {'companyId': company['companyId'], 'serverIds': [server['serverId']], 'repositoryUrl': 'https://github.com/zhq910513/unregistered_spider_1087.git', 'refName': 'main'}
    analysis = client.post('/api/v1/project-publish/pipeline-analyses', headers=headers, json=payload).json()['data']

    assert analysis['pipelineStatus'] == 'BLOCKED'
    assert analysis['canContinue'] is False
    build_step = next(item for item in analysis['steps'] if item['key'] == 'build')
    assert build_step['status'] == 'error'
    assert build_step['blocking'] is True
    assert build_step['data']['mode'] == 'EXTERNAL_RELEASE_REQUIRED'
    assert build_step['data']['blockedReasonCode'] == 'PLATFORM_BUILD_CENTER_NOT_READY'
    assert build_step['data']['supportedReleasePath'] == 'EXTERNAL_CI_RELEASE_REGISTRATION'
    assert build_step['data']['cicdGuideEndpoint'] == '/api/v1/cicd/spider-projects/one-click-guide'
    assert build_step['data']['registerEndpoint'] == '/api/v1/discovered-projects'
    assert '外部 CI' in ''.join(build_step['data']['nextActions'])


def test_project_publish_page_surfaces_external_ci_guide_for_unregistered_releases() -> None:
    page = (ROOT / 'frontend' / 'src' / 'views' / 'ProjectPublishPage.vue').read_text(encoding='utf-8')
    assert 'getSpiderProjectCicdOneClickGuide' in page
    assert 'buildCenterBlocked' in page
    assert 'PLATFORM_BUILD_CENTER_NOT_READY' in page
    assert '查看外部 CI 接入指引' in page
    assert '当前未登记 Release，不能走平台内构建' in page
    assert '平台构建执行器、代码仓库读取凭据、镜像仓库推送凭据未完成' in page
