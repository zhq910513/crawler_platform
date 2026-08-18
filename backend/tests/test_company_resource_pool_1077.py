from __future__ import annotations

import os
from pathlib import Path

Path('/tmp/crawler_platform_resource_pool_1077.db').unlink(missing_ok=True)
os.environ['APP_ENV'] = 'test'
os.environ['DATABASE_URL'] = 'sqlite+pysqlite:////tmp/crawler_platform_resource_pool_1077.db'
os.environ['REDIS_URL'] = 'redis://localhost:6379/15'
os.environ['JWT_SECRET'] = 'pytest-jwt-secret-for-crawler-platform-1-0-77'
os.environ['SECRET_ENCRYPTION_KEY'] = 'pytest-secret-encryption-key-for-crawler-platform-1-0-77'
os.environ['ADMIN_USERNAME'] = 'admin'
os.environ['ADMIN_PASSWORD'] = 'Admin@123456'

from fastapi.testclient import TestClient

from app.main import app
from app.migration_main import main as migrate


def _login(client: TestClient) -> dict[str, str]:
    response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456'})
    if response.json().get('code') == 40901:
        token = response.json()['data']['forceLoginToken']
        response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456', 'forceLoginToken': token})
    assert response.status_code == 200
    return {'Authorization': 'Bearer ' + response.json()['data']['accessToken']}


def _payload(company_id: int, code: str, name: str, engine: str = 'MYSQL', role: str = 'RESULT_DB', category: str = 'RELATIONAL_DB', config: dict | None = None) -> dict:
    return {
        'companyId': company_id,
        'resourceName': name,
        'resourceCode': code,
        'resourceCategory': category,
        'resourceEngine': engine,
        'resourceRole': role,
        'connectionMode': 'HOST_PORT',
        'remark': f'{name} 的用途说明。',
        'enabled': True,
        'config': config or {'host': '127.0.0.1', 'port': 3306, 'database': code, 'username': 'u', 'password': 'secret'},
    }


def test_company_can_have_multiple_same_engine_resources_and_multiple_engines() -> None:
    migrate()
    client = TestClient(app)
    headers = _login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'resource77', 'companyName': '资源池公司'}).json()['data']

    first = client.post('/api/v1/company-resource-configs', headers=headers, json=_payload(company['companyId'], 'result_mysql', '采集结果 MySQL')).json()['data']
    second = client.post('/api/v1/company-resource-configs', headers=headers, json=_payload(company['companyId'], 'source_mysql', '客户源 MySQL', role='SOURCE_DB')).json()['data']
    redis = client.post('/api/v1/company-resource-configs', headers=headers, json=_payload(company['companyId'], 'cookie_redis', 'Cookie Redis', engine='REDIS', role='COOKIE_CACHE', category='CACHE_DB', config={'host': '127.0.0.1', 'port': 6379, 'database': 0, 'password': 'secret'})).json()['data']

    assert first['resourceEngine'] == second['resourceEngine'] == 'MYSQL'
    assert first['configId'] != second['configId']
    assert redis['resourceEngine'] == 'REDIS'
    rows = client.get('/api/v1/company-resource-configs', headers=headers, params={'companyId': company['companyId']}).json()['data']
    assert {item['resourceCode'] for item in rows} >= {'result_mysql', 'source_mysql', 'cookie_redis'}


def test_resource_code_is_unique_only_inside_same_company() -> None:
    migrate()
    client = TestClient(app)
    headers = _login(client)
    company_a = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'resource77a', 'companyName': '资源池公司A'}).json()['data']
    company_b = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'resource77b', 'companyName': '资源池公司B'}).json()['data']
    assert client.post('/api/v1/company-resource-configs', headers=headers, json=_payload(company_a['companyId'], 'shared_code', 'A库')).status_code == 200
    assert client.post('/api/v1/company-resource-configs', headers=headers, json=_payload(company_a['companyId'], 'shared_code', 'A库重复')).status_code == 400
    assert client.post('/api/v1/company-resource-configs', headers=headers, json=_payload(company_b['companyId'], 'shared_code', 'B库')).status_code == 200


def test_missing_engine_and_legacy_resource_type_are_rejected_for_new_save() -> None:
    migrate()
    client = TestClient(app)
    headers = _login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'resource77reject', 'companyName': '资源池拒绝公司'}).json()['data']
    legacy = client.post('/api/v1/company-resource-configs', headers=headers, json={'companyId': company['companyId'], 'resourceType': 'MYSQL_MAIN', 'resourceName': '旧主业务库', 'config': {'host': '127.0.0.1'}})
    assert legacy.status_code == 400
    missing_engine = _payload(company['companyId'], 'missing_engine', '缺少类型')
    missing_engine.pop('resourceEngine')
    assert client.post('/api/v1/company-resource-configs', headers=headers, json=missing_engine).status_code == 400


def test_basic_validation_is_not_connection_success() -> None:
    migrate()
    client = TestClient(app)
    headers = _login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'resource77validate', 'companyName': '资源池校验公司'}).json()['data']
    resource = client.post('/api/v1/company-resource-configs', headers=headers, json=_payload(company['companyId'], 'result_mysql_valid', '采集结果库')).json()['data']
    tested = client.post(f"/api/v1/company-resource-configs/{resource['configId']}/tests", headers=headers, json={}).json()['data']
    assert tested['testStatus'] == 'CONFIG_VALID'
    assert '尚未执行真实连通测试' in tested['lastTestMessage']
    manual = client.post(f"/api/v1/company-resource-configs/{resource['configId']}/tests", headers=headers, json={'forceSuccess': True}).json()['data']
    assert manual['testStatus'] == 'MANUAL_CONFIRMED'
