from __future__ import annotations

import os
from pathlib import Path
Path('/tmp/crawler_platform_tenant_1026.db').unlink(missing_ok=True)
os.environ['APP_ENV'] = 'test'
os.environ['DATABASE_URL'] = 'sqlite+pysqlite:////tmp/crawler_platform_tenant_1026.db'
os.environ['REDIS_URL'] = 'redis://localhost:6379/15'
os.environ['JWT_SECRET'] = 'pytest-jwt-secret-for-crawler-platform-1-0-27'
os.environ['SECRET_ENCRYPTION_KEY'] = 'pytest-secret-encryption-key-for-crawler-platform-1-0-27'
os.environ['ADMIN_USERNAME'] = 'admin'
os.environ['ADMIN_PASSWORD'] = 'Admin@123456'

from fastapi.testclient import TestClient

from app.main import app
from app.migration_main import main as migrate
from app.security import hash_password
from app.models import SysUser
from app.db import SessionLocal
from app.utils import utcnow
def _admin_login(client: TestClient) -> dict:
    response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456'})
    if response.json().get('code') == 40901:
        token = response.json()['data']['forceLoginToken']
        response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456', 'forceLoginToken': token})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['data']['accessToken']}


def _login(client: TestClient, username: str, password: str) -> dict:
    response = client.post('/api/v1/sessions', json={'userName': username, 'password': password})
    if response.json().get('code') == 40901:
        token = response.json()['data']['forceLoginToken']
        response = client.post('/api/v1/sessions', json={'userName': username, 'password': password, 'forceLoginToken': token})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['data']['accessToken']}


def test_normal_user_is_company_scoped_for_settings_and_agent_join() -> None:
    migrate()
    client = TestClient(app)
    admin_headers = _admin_login(client)
    company_a = client.post('/api/v1/companies', headers=admin_headers, json={'companyCode': 'tenant26a', 'companyName': '租户A'}).json()['data']
    company_b = client.post('/api/v1/companies', headers=admin_headers, json={'companyCode': 'tenant26b', 'companyName': '租户B'}).json()['data']
    with SessionLocal() as db:
        user = SysUser(
            company_id=company_a['companyId'],
            user_name='tenant_a_ops',
            nick_name='租户A运维',
            password_hash=hash_password('Tenant@123456'),
            password_updated_at=utcnow(),
            role_type='NORMAL_USER',
            status='ENABLED',
        )
        db.add(user)
        db.commit()
    user_headers = _login(client, 'tenant_a_ops', 'Tenant@123456')

    companies = client.get('/api/v1/companies', headers=user_headers).json()['data']
    assert [item['companyId'] for item in companies] == [company_a['companyId']]

    own_resource = client.post('/api/v1/company-resource-configs', headers=user_headers, json={'companyId': company_a['companyId'], 'resourceType': 'MYSQL_MAIN', 'resourceName': '主业务数据库', 'config': {'host': '127.0.0.1', 'port': '3306', 'database': 'biz', 'username': 'u'}})
    assert own_resource.status_code == 200
    cross_resource = client.post('/api/v1/company-resource-configs', headers=user_headers, json={'companyId': company_b['companyId'], 'resourceType': 'MYSQL_MAIN', 'resourceName': '越权数据库', 'config': {'host': '127.0.0.1', 'port': '3306', 'database': 'biz', 'username': 'u'}})
    assert cross_resource.status_code == 404

    join = client.post('/api/v1/servers/agent-join-tokens', headers=user_headers, json={'companyId': company_a['companyId'], 'serverCode': 'tenant26a-node', 'serverName': '租户A节点', 'agentCode': 'tenant26a-agent', 'maxContainerSlots': 2, 'controlPlaneUrl': 'http://127.0.0.1:8080', 'installTarget': 'LOCAL'})
    assert join.status_code == 200
    assert join.json()['data']['companyId'] == company_a['companyId']
    cross_join = client.post('/api/v1/servers/agent-join-tokens', headers=user_headers, json={'companyId': company_b['companyId'], 'serverCode': 'tenant26b-node', 'serverName': '租户B节点', 'agentCode': 'tenant26b-agent', 'maxContainerSlots': 2, 'controlPlaneUrl': 'http://127.0.0.1:8080', 'installTarget': 'LOCAL'})
    assert cross_join.status_code == 404
