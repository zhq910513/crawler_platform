from __future__ import annotations

import os
from pathlib import Path

os.environ['APP_ENV'] = 'development'
os.environ['DATABASE_URL'] = 'sqlite+pysqlite:////tmp/crawler_platform_account_status_pytest.db'
os.environ['REDIS_URL'] = 'redis://localhost:6379/15'
os.environ['ADMIN_USERNAME'] = 'admin'
os.environ['ADMIN_PASSWORD'] = 'Admin@123456'
os.environ['JWT_SECRET'] = 'pytest-jwt-secret-for-crawler-platform-1-0-20'
os.environ['SECRET_ENCRYPTION_KEY'] = 'pytest-secret-encryption-key-for-crawler-platform-1-0-20'
Path('/tmp/crawler_platform_account_status_pytest.db').unlink(missing_ok=True)

from fastapi.testclient import TestClient

from app.migration_main import main as migrate
from app.main import app


def login(client: TestClient) -> dict[str, str]:
    response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456'})
    if response.json()['code'] == 40901:
        token = response.json()['data']['forceLoginToken']
        response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456', 'forceLoginToken': token})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['data']['accessToken']}


def test_account_status_event_upsert_and_redaction() -> None:
    migrate()
    client = TestClient(app)
    headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'ulike', 'companyName': 'Ulike'}).json()['data']
    event = client.post('/api/v1/account-status-events', headers=headers, json={
        'companyCode': 'ulike',
        'platformCode': 'shopee',
        'credentialKey': 'shopee_ulike_id_local',
        'credentialName': 'Ulike 印尼本土店账号',
        'statusCode': 'COOKIE_EXPIRED',
        'severity': 'WARNING',
        'source': 'TASK_RUN',
        'message': 'cookie=abc token=def 已过期',
        'payload': {'cookieString': 'abc', 'safe': 'visible'},
        'eventUid': 'evt-fixed-1',
    })
    assert event.status_code == 200
    credentials = client.get('/api/v1/account-credentials', headers=headers, params={'companyId': company['companyId']}).json()['data']
    assert len(credentials) == 1
    item = credentials[0]
    assert item['companyCode'] == 'ulike'
    assert item['platformCode'] == 'shopee'
    assert item['credentialKey'] == 'shopee_ulike_id_local'
    assert item['healthStatus'] == 'EXPIRED'
    assert item['loginStatus'] == 'AUTH_EXPIRED'
    assert item['lastStatusCode'] == 'COOKIE_EXPIRED'
    events = client.get(f"/api/v1/account-credentials/{item['credentialId']}/status-events", headers=headers).json()['data']
    assert events[0]['messageSanitized'] == 'cookie=***REDACTED*** token=***REDACTED*** 已过期'
    assert events[0]['payloadSanitized']['cookieString'] == '***REDACTED***'
    assert events[0]['payloadSanitized']['safe'] == 'visible'
    duplicate = client.post('/api/v1/account-status-events', headers=headers, json={
        'companyCode': 'ulike', 'platformCode': 'shopee', 'credentialKey': 'shopee_ulike_id_local', 'statusCode': 'LOGIN_OK', 'eventUid': 'evt-fixed-1'
    }).json()['data']
    assert duplicate['statusEventId'] == events[0]['statusEventId']


def test_agent_account_status_event_scope_and_success_mapping() -> None:
    migrate()
    client = TestClient(app)
    headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'agentco', 'companyName': 'Agent Co'}).json()['data']
    client.post('/api/v1/servers', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'srv-a', 'serverName': 'A服务器'})
    agent = client.post('/api/v1/agents', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'srv-a', 'serverName': 'A服务器', 'agentCode': 'agent-a'}).json()['data']
    agent_headers = {'Authorization': 'Agent ' + agent['agentToken']}
    response = client.post('/api/v1/agent-account-status-events', headers=agent_headers, json={
        'companyCode': 'agentco', 'platformCode': 'oilchem', 'credentialKey': 'oilchem_main', 'statusCode': 'LOGIN_OK', 'source': 'TASK_RUN'
    })
    assert response.status_code == 200
    credentials = client.get('/api/v1/account-credentials', headers=headers, params={'companyId': company['companyId']}).json()['data']
    assert credentials[0]['healthStatus'] == 'HEALTHY'
    assert credentials[0]['loginStatus'] == 'AUTH_ACTIVE'
    assert credentials[0]['usageStatus'] == 'AVAILABLE'
    assert credentials[0]['lastVerifiedAgentCode'] == 'agent-a'
