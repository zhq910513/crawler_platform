from __future__ import annotations

import os
from pathlib import Path

os.environ['APP_ENV'] = 'development'
os.environ['DATABASE_URL'] = 'sqlite+pysqlite:////tmp/crawler_platform_subject_binding_pytest.db'
os.environ['REDIS_URL'] = 'redis://localhost:6379/15'
os.environ['ADMIN_USERNAME'] = 'admin'
os.environ['ADMIN_PASSWORD'] = 'Admin@123456'
os.environ['JWT_SECRET'] = 'pytest-jwt-secret-for-crawler-platform-1-0-20'
os.environ['SECRET_ENCRYPTION_KEY'] = 'pytest-secret-encryption-key-for-crawler-platform-1-0-20'
Path('/tmp/crawler_platform_subject_binding_pytest.db').unlink(missing_ok=True)

from fastapi.testclient import TestClient

from app.migration_main import main as migrate
from app.main import app


def login(client: TestClient) -> dict[str, str]:
    response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456'})
    if response.json()['code'] == 40901:
        token = response.json()['data']['forceLoginToken']
        response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456', 'forceLoginToken': token})
    return {'Authorization': 'Bearer ' + response.json()['data']['accessToken']}


def test_subject_binding_created_from_status_event_and_conflict_is_recorded() -> None:
    migrate()
    client = TestClient(app)
    headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'subjectco', 'companyName': 'Subject Co'}).json()['data']
    event = client.post('/api/v1/account-status-events', headers=headers, json={
        'companyCode': 'subjectco',
        'platformCode': 'demo',
        'credentialKey': 'account_a',
        'statusCode': 'SUBJECT_QUERY_OK',
        'eventType': 'SUBJECT_BINDING',
        'subjectType': 'company',
        'subjectKey': 'company_001',
        'subjectName': '测试公司',
        'payload': {'cookie': 'secret-cookie', 'safe': 'ok'},
    })
    assert event.status_code == 200
    bindings = client.get('/api/v1/credential-subject-bindings', headers=headers, params={'companyId': company['companyId'], 'platformCode': 'demo'}).json()['data']
    assert len(bindings) == 1
    assert bindings[0]['subjectKey'] == 'company_001'
    assert bindings[0]['credentialKey'] == 'account_a'
    assert bindings[0]['bindingStatus'] == 'ACTIVE'

    conflict = client.post('/api/v1/account-status-events', headers=headers, json={
        'companyCode': 'subjectco', 'platformCode': 'demo', 'credentialKey': 'account_b', 'statusCode': 'SUBJECT_QUERY_OK', 'eventType': 'SUBJECT_BINDING', 'subjectType': 'company', 'subjectKey': 'company_001'
    }).json()['data']
    assert conflict['payloadSanitized']['subjectBindingConflict']['existingCredentialKey'] == 'account_a'
    bindings = client.get('/api/v1/credential-subject-bindings', headers=headers, params={'companyId': company['companyId']}).json()['data']
    assert bindings[0]['credentialKey'] == 'account_a'


def test_manual_subject_binding_rebind_with_audit_fields() -> None:
    migrate()
    client = TestClient(app)
    headers = login(client)
    client.post('/api/v1/companies', headers=headers, json={'companyCode': 'manualco', 'companyName': 'Manual Co'})
    binding = client.post('/api/v1/credential-subject-bindings', headers=headers, json={
        'companyCode': 'manualco', 'platformCode': 'demo', 'subjectType': 'company', 'subjectKey': 'company_x', 'credentialKey': 'account_old'
    }).json()['data']
    updated = client.patch(f"/api/v1/credential-subject-bindings/{binding['bindingId']}", headers=headers, json={'credentialKey': 'account_new', 'reason': '旧账号永久失效'}).json()['data']
    assert updated['credentialKey'] == 'account_new'
    assert updated['bindingStatus'] == 'REBOUND'
