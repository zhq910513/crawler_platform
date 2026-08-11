from __future__ import annotations

import os
from pathlib import Path

os.environ['APP_ENV'] = 'development'
os.environ['DATABASE_URL'] = 'sqlite+pysqlite:////tmp/crawler_platform_pytest.db'
os.environ['REDIS_URL'] = 'redis://localhost:6379/15'
os.environ['ADMIN_USERNAME'] = 'admin'
os.environ['ADMIN_PASSWORD'] = 'Admin@123456'
os.environ['JWT_SECRET'] = 'pytest-jwt-secret-for-crawler-platform-1-0-27'
os.environ['SECRET_ENCRYPTION_KEY'] = 'pytest-secret-encryption-key-for-crawler-platform-1-0-27'
Path('/tmp/crawler_platform_pytest.db').unlink(missing_ok=True)

from fastapi.testclient import TestClient

from app.main import app
from app.migration_main import main as migrate


def login(client: TestClient) -> dict:
    response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456'})
    if response.json()['code'] == 40901:
        token = response.json()['data']['forceLoginToken']
        response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456', 'forceLoginToken': token})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['data']['accessToken']}


def test_setup_assistant_status_and_resource_config() -> None:
    migrate()
    client = TestClient(app)
    headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'setup25', 'companyName': '配置助手公司'}).json()['data']

    status = client.get(f"/api/v1/companies/{company['companyId']}/setup-status", headers=headers).json()['data']
    assert status['mode'] == 'FIRST_SETUP'
    assert any(item['key'] == 'database' and item['status'] == 'MISSING' for item in status['steps'])

    settings = client.patch('/api/v1/system-settings', headers=headers, json={'controlPlanePublicBaseUrl': 'http://10.1.0.13:8080'}).json()['data']
    assert settings['controlPlanePublicBaseUrl'] == 'http://10.1.0.13:8080'

    resource = client.post('/api/v1/company-resource-configs', headers=headers, json={'companyId': company['companyId'], 'resourceType': 'MYSQL_MAIN', 'resourceName': '主业务数据库', 'config': {'host': '127.0.0.1', 'port': '3306', 'database': 'biz', 'username': 'u', 'password': 'secret'}}).json()['data']
    assert resource['configMasked']['password'] == '******'
    tested = client.post(f"/api/v1/company-resource-configs/{resource['configId']}/tests", headers=headers, json={}).json()['data']
    assert tested['testStatus'] == 'PASSED'

    status = client.get(f"/api/v1/companies/{company['companyId']}/setup-status", headers=headers).json()['data']
    database_step = [item for item in status['steps'] if item['key'] == 'database'][0]
    assert database_step['status'] == 'DONE'
    assert status['controlPlanePublicBaseUrlConfigured'] is True
