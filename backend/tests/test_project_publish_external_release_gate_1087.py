from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from test_rebuild_contract import app, login, migrate

ROOT = Path(__file__).resolve().parents[2]


def test_project_publish_build_blocker_legacy_1087_asserts_platform_build_center_path() -> None:
    """v1.0.89 keeps the old 1087 test filename as an upgrade guard.

    Some deployments applied v1.0.88 by overlaying files, leaving the old
    external-CI test in the repository.  The current release contract is
    platform-owned passive build/release, not spider-project-active CI.
    """
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'legacy_build_center_1087', 'companyName': '旧测试兼容公司1087'}).json()['data']
    server = client.post('/api/v1/servers', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'legacy-build-center-srv', 'serverName': '旧测试兼容节点'}).json()['data']
    agent = client.post('/api/v1/agents', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'legacy-build-center-srv', 'serverName': '旧测试兼容节点', 'agentCode': 'legacy-build-center-agent', 'agentName': '旧测试兼容 Agent'}).json()['data']
    client.post('/api/v1/agent-heartbeats', headers={'Authorization': 'Agent ' + agent['agentToken']}, json={'agentInstanceId': 'legacy-build-center-inst', 'dockerStatus': 'OK', 'availableSlots': 2, 'runningContainers': 0, 'hostIp': '10.87.0.10'})

    payload = {'companyId': company['companyId'], 'serverIds': [server['serverId']], 'repositoryUrl': 'https://github.com/zhq910513/unregistered_spider_1087.git', 'refName': 'main'}
    analysis = client.post('/api/v1/project-publish/pipeline-analyses', headers=headers, json=payload).json()['data']

    assert analysis['pipelineStatus'] == 'BLOCKED'
    assert analysis['canContinue'] is False
    build_step = next(item for item in analysis['steps'] if item['key'] == 'build')
    assert build_step['status'] == 'error'
    assert build_step['blocking'] is True
    assert build_step['data']['mode'] == 'PLATFORM_BUILD_CENTER_REQUIRED'
    assert build_step['data']['blockedReasonCode'] == 'PLATFORM_BUILD_CENTER_NOT_READY'
    assert build_step['data']['supportedReleasePath'] == 'PLATFORM_MANAGED_BUILD_RELEASE_REGISTRATION'
    assert build_step['data']['buildContractScript'] == 'scripts/platform_build_contract.sh'
    assert build_step['data']['releaseOwnership'] == 'crawler_platform'


def test_project_publish_page_legacy_1087_no_external_ci_guide() -> None:
    page = (ROOT / 'frontend' / 'src' / 'views' / 'ProjectPublishPage.vue').read_text(encoding='utf-8')
    assert 'getSpiderProjectCicdOneClickGuide' not in page
    assert '查看外部 CI 接入指引' not in page
    assert 'PLATFORM_BUILD_CENTER_NOT_READY' in page
    assert '平台构建中心尚未就绪' in page
