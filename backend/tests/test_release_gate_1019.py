from __future__ import annotations

import os
from pathlib import Path

os.environ['APP_ENV'] = 'development'
os.environ['DATABASE_URL'] = 'sqlite+pysqlite:////tmp/crawler_platform_release_gate_1019.db'
os.environ['REDIS_URL'] = 'redis://localhost:6379/15'
os.environ['ADMIN_USERNAME'] = 'admin'
os.environ['ADMIN_PASSWORD'] = 'Admin@123456'
os.environ['JWT_SECRET'] = 'pytest-jwt-secret-for-crawler-platform-1-0-20'
os.environ['SECRET_ENCRYPTION_KEY'] = 'pytest-secret-encryption-key-for-crawler-platform-1-0-20'
Path('/tmp/crawler_platform_release_gate_1019.db').unlink(missing_ok=True)

from fastapi.testclient import TestClient

from app.migration_main import main as migrate
from app.main import app


def login(client: TestClient) -> dict[str, str]:
    response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456'})
    if response.json()['code'] == 40901:
        token = response.json()['data']['forceLoginToken']
        response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456', 'forceLoginToken': token})
    return {'Authorization': 'Bearer ' + response.json()['data']['accessToken']}


def _prepare_project(client: TestClient, headers: dict[str, str]) -> tuple[dict, dict]:
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'gateco', 'companyName': 'Gate Co'}).json()['data']
    server = client.post('/api/v1/servers', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'gate-node', 'serverName': 'Gate Node', 'serverIp': '10.19.0.10'}).json()['data']
    agent = client.post('/api/v1/agents', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'gate-node', 'serverName': 'Gate Node', 'agentCode': 'gate-agent', 'agentName': 'Gate Agent'}).json()['data']
    agent_headers = {'Authorization': 'Agent ' + agent['agentToken']}
    token = client.post(f"/api/v1/companies/{company['companyId']}/discovery-tokens", headers=headers).json()['data']['discoveryToken']
    manifest = {
        'manifestVersion': '1', 'projectKey': 'gate-project', 'projectName': '契约门禁项目', 'projectCode': 'gate_project',
        'imageRepository': 'repo/gate', 'imageDigest': 'sha256:' + ('9' * 64), 'releaseVersion': '1.0.19', 'releaseChannel': 'stable',
        'taskDefinitions': [{
            'definitionKey': 'company_info_query', 'taskName': '公司信息查询', 'platformCode': 'a_platform',
            'entryModule': 'spiders.a_platform.company_info_query', 'entryFunction': 'run',
            'requiredConfigs': [{'slot': 'mysql_main', 'type': 'MYSQL', 'required': True}],
            'requiredCredentials': [{'slot': 'queryAccount', 'platformCode': 'a_platform', 'credentialType': 'WEB_COOKIE', 'supportedModes': ['fixed', 'pool', 'affinity_pool', 'external_affinity_pool'], 'required': True}],
            'outputTables': [{'slot': 'companyInfoTable', 'defaultName': 'company_info', 'writeMethod': 'replace'}],
        }]
    }
    discovered = client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + token}, json={'companyId': company['companyId'], 'manifest': manifest}).json()['data']
    project = client.post('/api/v1/projects', headers=headers, json={'discoveredProjectId': discovered['discoveredProjectId']}).json()['data']
    client.put(f"/api/v1/projects/{project['projectId']}/servers", headers=headers, json={'servers': [{'serverId': server['serverId'], 'schedulingStatus': 'ENABLED', 'serverRole': 'ACTIVE', 'priority': 100, 'weight': 100, 'maxConcurrency': 4}]})
    client.post('/api/v1/agent-heartbeats', headers=agent_headers, json={'agentInstanceId': 'gate-instance', 'dockerStatus': 'OK', 'availableSlots': 2})
    deployment = client.post(f"/api/v1/projects/{project['projectId']}/release-deployments", headers=headers, json={'serverIds': [server['serverId']]}).json()['data']
    heartbeat = client.post('/api/v1/agent-heartbeats', headers=agent_headers, json={'agentInstanceId': 'gate-instance', 'dockerStatus': 'OK', 'availableSlots': 2}).json()['data']
    command = next(item for item in heartbeat['pendingAgentCommands'] if item['deploymentId'] == deployment['deploymentId'])
    ack = client.post('/api/v1/agent-command-results', headers=agent_headers, json={'commandId': command['commandId'], 'commandType': command['commandType'], 'projectId': project['projectId'], 'releaseId': command['releaseId'], 'deploymentId': command['deploymentId'], 'targetId': command['targetId'], 'success': True, 'message': 'smoke ok', 'result': {}})
    assert ack.status_code == 200, ack.text
    definition = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data'][0]
    return company, definition


def test_task_creation_requires_config_and_credential_bindings() -> None:
    migrate()
    client = TestClient(app)
    headers = login(client)
    _company, definition = _prepare_project(client, headers)

    # Orchestration is progressive: an incomplete definition can be accepted as DRAFT.
    draft = client.post('/api/v1/tasks', headers=headers, json={
        'definitionId': definition['definitionId'], 'taskCode': 'draft_task', 'taskName': '待补绑定任务', 'status': 'DRAFT'
    })
    assert draft.status_code == 200, draft.text
    task = draft.json()['data']
    assert task['status'] == 'DRAFT'

    # Runtime activation remains strict: the same task cannot be enabled without required bindings.
    enabled = client.patch(f"/api/v1/tasks/{task['taskId']}", headers=headers, json={'status': 'ENABLED'})
    assert enabled.status_code == 400
    body = enabled.json()
    assert body['code'] == 40090
    assert any('mysql_main' in item for item in body['data']['errors'])
    assert any('queryAccount' in item for item in body['data']['errors'])


def test_non_credential_event_does_not_refresh_verified_status_and_lease_lifecycle() -> None:
    migrate()
    client = TestClient(app)
    headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'leaseco', 'companyName': 'Lease Co'}).json()['data']
    first = client.post('/api/v1/account-status-events', headers=headers, json={
        'companyCode': 'leaseco', 'platformCode': 'demo', 'credentialKey': 'account_a', 'statusCode': 'LOGIN_OK', 'eventUid': 'evt-lease-ok'
    }).json()['data']
    cred = client.get('/api/v1/account-credentials', headers=headers, params={'companyId': company['companyId']}).json()['data'][0]
    verified_at = cred['lastVerifiedAt']
    second = client.post('/api/v1/account-status-events', headers=headers, json={
        'companyCode': 'leaseco', 'platformCode': 'demo', 'credentialKey': 'account_a', 'statusCode': 'PLATFORM_5XX', 'affectsCredential': False, 'eventUid': 'evt-non-credential'
    }).json()['data']
    cred2 = client.get('/api/v1/account-credentials', headers=headers, params={'companyId': company['companyId']}).json()['data'][0]
    assert cred2['healthStatus'] == 'HEALTHY'
    assert cred2['lastVerifiedAt'] == verified_at
    assert cred2['statusMetadata']['lastNonCredentialIssue'] == 'PLATFORM_5XX'

    acquired = client.post('/api/v1/credential-leases/acquire', headers=headers, json={
        'companyCode': 'leaseco', 'platformCode': 'demo', 'credentialKey': 'account_a', 'slot': 'worker', 'leaseSeconds': 600
    }).json()['data']
    assert acquired['lease']['leaseStatus'] == 'ACTIVE'
    duplicate = client.post('/api/v1/credential-leases/acquire', headers=headers, json={
        'companyCode': 'leaseco', 'platformCode': 'demo', 'credentialKey': 'account_a', 'slot': 'worker', 'leaseSeconds': 600
    })
    assert duplicate.status_code == 409
    released = client.post('/api/v1/credential-leases/release', headers=headers, json={'leaseId': acquired['lease']['leaseId'], 'leaseToken': acquired['leaseToken']}).json()['data']
    assert released['leaseStatus'] == 'RELEASED'
