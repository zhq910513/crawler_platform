from __future__ import annotations

import os
from pathlib import Path

os.environ['APP_ENV'] = 'development'
os.environ['DATABASE_URL'] = 'sqlite+pysqlite:////tmp/crawler_platform_task_contract_pytest.db'
os.environ['REDIS_URL'] = 'redis://localhost:6379/15'
os.environ['ADMIN_USERNAME'] = 'admin'
os.environ['ADMIN_PASSWORD'] = 'Admin@123456'
os.environ['JWT_SECRET'] = 'pytest-jwt-secret-for-crawler-platform-1-0-20-task'
os.environ['SECRET_ENCRYPTION_KEY'] = 'pytest-secret-encryption-key-for-crawler-platform-1-0-20-task'
Path('/tmp/crawler_platform_task_contract_pytest.db').unlink(missing_ok=True)

from fastapi.testclient import TestClient

from app.migration_main import main as migrate
from app.main import app


def login(client: TestClient) -> dict[str, str]:
    response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456'})
    if response.json()['code'] == 40901:
        token = response.json()['data']['forceLoginToken']
        response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456', 'forceLoginToken': token})
    return {'Authorization': 'Bearer ' + response.json()['data']['accessToken']}


def test_task_definition_contract_is_discovered_and_snapshot_on_task() -> None:
    migrate()
    client = TestClient(app)
    headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'contractco', 'companyName': 'Contract Co'}).json()['data']
    token = client.post(f"/api/v1/companies/{company['companyId']}/discovery-tokens", headers=headers).json()['data']['discoveryToken']
    manifest = {
        'manifestVersion': '1', 'projectKey': 'contract-project', 'projectName': '契约项目', 'projectCode': 'contract_project',
        'imageRepository': 'repo/contract', 'imageDigest': 'sha256:' + ('8' * 64), 'releaseVersion': '1.0.19', 'releaseChannel': 'stable',
        'taskDefinitions': [{
            'definitionKey': 'company_info_query', 'taskName': '公司信息查询', 'platformCode': 'a_platform',
            'entryModule': 'spiders.a_platform.company_info_query', 'entryFunction': 'run',
            'requiredConfigs': [{'slot': 'mysql_main', 'type': 'MYSQL', 'required': True}],
            'requiredCredentials': [{'slot': 'queryAccount', 'platformCode': 'a_platform', 'credentialType': 'WEB_COOKIE', 'supportedModes': ['fixed', 'pool', 'affinity_pool'], 'required': True}],
            'outputTables': [{'slot': 'companyInfoTable', 'defaultName': 'company_info', 'writeMethod': 'replace'}],
        }]
    }
    discovered = client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + token}, json={'companyId': company['companyId'], 'manifest': manifest}).json()['data']
    project = client.post('/api/v1/projects', headers=headers, json={'discoveredProjectId': discovered['discoveredProjectId']}).json()['data']
    server = client.post('/api/v1/servers', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'contract-node', 'serverName': 'Contract Node', 'serverIp': '10.18.0.10'}).json()['data']
    agent = client.post('/api/v1/agents', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'contract-node', 'serverName': 'Contract Node', 'agentCode': 'contract-agent', 'agentName': 'Contract Agent'}).json()['data']
    agent_headers = {'Authorization': 'Agent ' + agent['agentToken']}
    client.put(f"/api/v1/projects/{project['projectId']}/servers", headers=headers, json={'servers': [{'serverId': server['serverId'], 'schedulingStatus': 'ENABLED', 'serverRole': 'ACTIVE', 'priority': 100, 'weight': 100, 'maxConcurrency': 4}]})
    client.post('/api/v1/agent-heartbeats', headers=agent_headers, json={'agentInstanceId': 'contract-instance', 'dockerStatus': 'OK', 'availableSlots': 2})
    deployment = client.post(f"/api/v1/projects/{project['projectId']}/release-deployments", headers=headers, json={'serverIds': [server['serverId']]}).json()['data']
    heartbeat = client.post('/api/v1/agent-heartbeats', headers=agent_headers, json={'agentInstanceId': 'contract-instance', 'dockerStatus': 'OK', 'availableSlots': 2}).json()['data']
    command = next(item for item in heartbeat['pendingAgentCommands'] if item['deploymentId'] == deployment['deploymentId'])
    client.post('/api/v1/agent-command-results', headers=agent_headers, json={'commandId': command['commandId'], 'commandType': command['commandType'], 'projectId': project['projectId'], 'releaseId': command['releaseId'], 'deploymentId': command['deploymentId'], 'targetId': command['targetId'], 'success': True, 'message': 'smoke ok', 'result': {}})
    definition = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data'][0]
    assert definition['platformCode'] == 'a_platform'
    assert definition['contractStatus'] == 'OK'
    assert definition['requiredCredentials'][0]['slot'] == 'queryAccount'
    task = client.post('/api/v1/tasks', headers=headers, json={
        'definitionId': definition['definitionId'], 'taskCode': 'company_info_query', 'taskName': '公司信息查询',
        'credentialBindings': {'queryAccount': {'mode': 'affinity_pool', 'platformCode': 'a_platform', 'subjectType': 'company'}},
        'configBindings': {'mysql_main': 'config:mysql_main'}
    }).json()['data']
    assert task['credentialBindings']['queryAccount']['mode'] == 'affinity_pool'
    assert task['contractSnapshot']['platformCode'] == 'a_platform'
