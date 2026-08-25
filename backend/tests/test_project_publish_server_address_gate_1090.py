from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from test_rebuild_contract import app, login, migrate

ROOT = Path(__file__).resolve().parents[2]


def test_project_publish_blocks_online_agent_without_reported_address() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'address_gate_1090', 'companyName': '地址门禁公司1090'}).json()['data']
    server = client.post('/api/v1/servers', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'address-gate-srv', 'serverName': '地址门禁节点'}).json()['data']
    agent = client.post('/api/v1/agents', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'address-gate-srv', 'serverName': '地址门禁节点', 'agentCode': 'address-gate-agent', 'agentName': '地址门禁 Agent'}).json()['data']
    client.post('/api/v1/agent-heartbeats', headers={'Authorization': 'Agent ' + agent['agentToken']}, json={'agentInstanceId': 'address-gate-inst', 'dockerStatus': 'OK', 'availableSlots': 2, 'runningContainers': 0})

    payload = {'companyId': company['companyId'], 'serverIds': [server['serverId']], 'repositoryUrl': 'https://github.com/zhq910513/unregistered_spider_1090.git', 'refName': 'main'}
    analysis = client.post('/api/v1/project-publish/pipeline-analyses', headers=headers, json=payload).json()['data']

    assert analysis['pipelineStatus'] == 'BLOCKED'
    servers_step = next(item for item in analysis['steps'] if item['key'] == 'servers')
    assert servers_step['status'] == 'error'
    assert servers_step['blocking'] is True
    assert servers_step['data']['unavailableServers'][0]['reason'] == '节点地址采集中'


def test_project_publish_accepts_server_after_agent_reports_host_ip() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'address_ready_1090', 'companyName': '地址就绪公司1090'}).json()['data']
    server = client.post('/api/v1/servers', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'address-ready-srv', 'serverName': '地址就绪节点'}).json()['data']
    agent = client.post('/api/v1/agents', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'address-ready-srv', 'serverName': '地址就绪节点', 'agentCode': 'address-ready-agent', 'agentName': '地址就绪 Agent'}).json()['data']
    client.post('/api/v1/agent-heartbeats', headers={'Authorization': 'Agent ' + agent['agentToken']}, json={'agentInstanceId': 'address-ready-inst', 'dockerStatus': 'OK', 'availableSlots': 2, 'runningContainers': 0, 'hostIp': '10.90.0.12'})

    payload = {'companyId': company['companyId'], 'serverIds': [server['serverId']], 'repositoryUrl': 'https://github.com/zhq910513/unregistered_spider_1090_ready.git', 'refName': 'main'}
    analysis = client.post('/api/v1/project-publish/pipeline-analyses', headers=headers, json=payload).json()['data']

    servers_step = next(item for item in analysis['steps'] if item['key'] == 'servers')
    assert servers_step['status'] == 'success'
    build_step = next(item for item in analysis['steps'] if item['key'] == 'build')
    assert build_step['data']['mode'] == 'PLATFORM_BUILD_CENTER_REQUIRED'


def test_project_publish_page_does_not_mark_address_collecting_node_as_deployable() -> None:
    page = (ROOT / 'frontend' / 'src' / 'views' / 'ProjectPublishPage.vue').read_text(encoding='utf-8')
    assert 'function serverAddressReady(server: ServerNode)' in page
    assert "if (!serverAddressReady(server)) return '节点地址采集中'" in page
    assert "serverDeployable(server) ? '可部署' : serverBlockReason(server)" in page
