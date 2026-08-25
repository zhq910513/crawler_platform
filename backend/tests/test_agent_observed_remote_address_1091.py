from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from test_rebuild_contract import app, login, migrate

ROOT = Path(__file__).resolve().parents[2]


def test_agent_heartbeat_uses_observed_remote_address_when_legacy_agent_does_not_report_host_identity() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'observed_remote_1091', 'companyName': '远端地址兜底公司1091'}).json()['data']
    server = client.post('/api/v1/servers', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'observed-remote-srv', 'serverName': '远端地址兜底节点'}).json()['data']
    agent = client.post('/api/v1/agents', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'observed-remote-srv', 'serverName': '远端地址兜底节点', 'agentCode': 'observed-remote-agent', 'agentName': '远端地址兜底 Agent'}).json()['data']

    client.post(
        '/api/v1/agent-heartbeats',
        headers={'Authorization': 'Agent ' + agent['agentToken'], 'X-Forwarded-For': '203.0.113.91, 10.0.0.9'},
        json={'agentInstanceId': 'observed-remote-inst', 'dockerStatus': 'OK', 'availableSlots': 2, 'runningContainers': 0},
    )

    rows = client.get('/api/v1/servers', headers=headers).json()['data']
    matched = next(item for item in rows if item['serverId'] == server['serverId'])
    assert matched['serverIp'] == '203.0.113.91'
    assert matched['metrics']['observedRemoteAddress'] == '203.0.113.91'
    assert matched['metrics']['reportedAddress'] == '203.0.113.91'

    payload = {'companyId': company['companyId'], 'serverIds': [server['serverId']], 'repositoryUrl': 'https://github.com/zhq910513/unregistered_spider_1091.git', 'refName': 'main'}
    analysis = client.post('/api/v1/project-publish/pipeline-analyses', headers=headers, json=payload).json()['data']
    servers_step = next(item for item in analysis['steps'] if item['key'] == 'servers')
    assert servers_step['status'] == 'success'


def test_agent_heartbeat_ignores_invalid_observed_remote_address_and_keeps_address_gate() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'invalid_remote_1091', 'companyName': '非法远端地址公司1091'}).json()['data']
    server = client.post('/api/v1/servers', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'invalid-remote-srv', 'serverName': '非法远端地址节点'}).json()['data']
    agent = client.post('/api/v1/agents', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'invalid-remote-srv', 'serverName': '非法远端地址节点', 'agentCode': 'invalid-remote-agent', 'agentName': '非法远端地址 Agent'}).json()['data']

    client.post('/api/v1/agent-heartbeats', headers={'Authorization': 'Agent ' + agent['agentToken'], 'X-Forwarded-For': 'not-an-ip'}, json={'agentInstanceId': 'invalid-remote-inst', 'dockerStatus': 'OK', 'availableSlots': 2, 'runningContainers': 0})

    payload = {'companyId': company['companyId'], 'serverIds': [server['serverId']], 'repositoryUrl': 'https://github.com/zhq910513/unregistered_spider_1091_invalid.git', 'refName': 'main'}
    analysis = client.post('/api/v1/project-publish/pipeline-analyses', headers=headers, json=payload).json()['data']
    servers_step = next(item for item in analysis['steps'] if item['key'] == 'servers')
    assert servers_step['status'] == 'error'
    assert servers_step['data']['unavailableServers'][0]['reason'] == '节点地址采集中'


def test_frontend_uses_observed_remote_address_as_publish_and_node_page_fallback() -> None:
    publish_page = (ROOT / 'frontend' / 'src' / 'views' / 'ProjectPublishPage.vue').read_text(encoding='utf-8')
    servers_page = (ROOT / 'frontend' / 'src' / 'views' / 'ServersPage.vue').read_text(encoding='utf-8')
    types_text = (ROOT / 'frontend' / 'src' / 'types' / 'api.ts').read_text(encoding='utf-8')
    assert 'server.metrics?.observedRemoteAddress' in publish_page
    assert 'row.metrics?.observedRemoteAddress' in servers_page
    assert 'observedRemoteAddress?: string' in types_text
