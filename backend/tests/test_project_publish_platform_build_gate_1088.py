from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from test_rebuild_contract import app, login, migrate

ROOT = Path(__file__).resolve().parents[2]


def test_project_publish_build_blocker_exposes_platform_build_center_path() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'build_center_1088', 'companyName': '构建中心公司1088'}).json()['data']
    server = client.post('/api/v1/servers', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'build-center-srv', 'serverName': '构建中心节点'}).json()['data']
    agent = client.post('/api/v1/agents', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'build-center-srv', 'serverName': '构建中心节点', 'agentCode': 'build-center-agent', 'agentName': '构建中心 Agent'}).json()['data']
    client.post('/api/v1/agent-heartbeats', headers={'Authorization': 'Agent ' + agent['agentToken']}, json={'agentInstanceId': 'build-center-inst', 'dockerStatus': 'OK', 'availableSlots': 2, 'runningContainers': 0, 'hostIp': '10.88.0.10'})

    payload = {'companyId': company['companyId'], 'serverIds': [server['serverId']], 'repositoryUrl': 'https://github.com/zhq910513/unregistered_spider_1088.git', 'refName': 'main'}
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
    assert '构建器调用爬虫项目' in ''.join(build_step['data']['nextActions'])


def test_project_publish_page_surfaces_platform_build_center_blocker() -> None:
    page = (ROOT / 'frontend' / 'src' / 'views' / 'ProjectPublishPage.vue').read_text(encoding='utf-8')
    assert 'getSpiderProjectCicdOneClickGuide' not in page
    assert 'buildCenterBlocked' in page
    assert 'PLATFORM_BUILD_CENTER_NOT_READY' in page
    assert '查看外部 CI 接入指引' not in page
    assert '当前未登记 Release，平台构建中心需要完成自检' in page
    assert '平台会自动启用构建中心、准备构建目录、使用内置 registry 前缀并挂载 Docker Socket' in page


def test_projects_page_no_longer_exposes_active_external_ci_setup() -> None:
    page = (ROOT / 'frontend' / 'src' / 'views' / 'ProjectsPage.vue').read_text(encoding='utf-8')
    assert '外部构建设置' not in page
    assert '爬虫项目 CI 一键初始化' not in page
    assert 'getSpiderProjectCicdOneClickGuide' not in page
    assert '构建中心未就绪' in page


def test_companies_page_secret_copy_does_not_instruct_repository_token_storage() -> None:
    page = (ROOT / 'frontend' / 'src' / 'views' / 'CompaniesPage.vue').read_text(encoding='utf-8')
    assert 'GitHub 仓库的 CRAWLER_DISCOVERY_TOKEN' not in page
    assert '不建议写入爬虫项目仓库' in page
