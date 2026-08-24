from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

os.environ['APP_ENV'] = 'development'
os.environ['DATABASE_URL'] = 'sqlite+pysqlite:////tmp/crawler_platform_pytest.db'
os.environ['REDIS_URL'] = 'redis://localhost:6379/15'
os.environ['ADMIN_USERNAME'] = 'admin'
os.environ['ADMIN_PASSWORD'] = 'Admin@123456'
os.environ['JWT_SECRET'] = 'pytest-jwt-secret-for-crawler-platform-1-0-1'
os.environ['SECRET_ENCRYPTION_KEY'] = 'pytest-secret-encryption-key-for-crawler-platform-1-0-1'
Path('/tmp/crawler_platform_pytest.db').unlink(missing_ok=True)

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.migration_main import main as migrate
from app.main import app
from app.models import CrawlerAgentJoinToken
from app.utils import sha256_text, utcnow


def login(client: TestClient) -> tuple[dict, dict]:
    response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456'})
    if response.json()['code'] == 40901:
        token = response.json()['data']['forceLoginToken']
        response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456', 'forceLoginToken': token})
    assert response.status_code == 200
    data = response.json()['data']
    return data, {'Authorization': 'Bearer ' + data['accessToken']}


def _create_join(client: TestClient, headers: dict, company_id: int, suffix: str) -> dict:
    response = client.post('/api/v1/servers/agent-join-tokens', headers=headers, json={
        'companyId': company_id,
        'serverCode': f'resume-guard-srv-{suffix}',
        'serverName': f'续跑保护节点{suffix}',
        'agentCode': f'resume-guard-agent-{suffix}',
        'agentName': f'续跑保护Agent{suffix}',
        'maxContainerSlots': 2,
        'workDir': '/data/crawler-agent',
        'controlPlaneUrl': 'http://127.0.0.1:8080',
        'installTarget': 'LOCAL',
    })
    assert response.status_code == 200
    return response.json()['data']


def test_resume_env_rejects_mismatched_current_join_token_and_keeps_new_token_usable() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'resume_guard_1082', 'companyName': '续跑保护公司'}).json()['data']

    old_join = _create_join(client, headers, company['companyId'], 'old')
    old_env = client.post('/api/v1/agent-bootstrap/env', json={'joinToken': old_join['joinToken'], 'hostname': 'old-host'})
    assert old_env.status_code == 200
    old_agent_token = next(line for line in old_env.text.splitlines() if line.startswith('AGENT_AGENT_TOKEN=')).split('=', 1)[1].strip("'")

    new_join = _create_join(client, headers, company['companyId'], 'new')
    resume = client.get('/api/v1/agent-bootstrap/resume-env', params={'joinToken': new_join['joinToken']}, headers={'Authorization': 'Agent ' + old_agent_token})
    assert resume.status_code == 409
    assert resume.json()['code'] == 40933

    new_env = client.post('/api/v1/agent-bootstrap/env', json={'joinToken': new_join['joinToken'], 'hostname': 'new-host'})
    assert new_env.status_code == 200
    assert "AGENT_AGENT_CODE='resume-guard-agent-new'" in new_env.text
    assert "AGENT_SERVER_CODE='resume-guard-srv-new'" in new_env.text


def test_config_issued_join_record_times_out_when_first_heartbeat_is_missing() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'join_timeout_1082', 'companyName': '接入超时公司'}).json()['data']

    join = _create_join(client, headers, company['companyId'], 'timeout')
    env = client.post('/api/v1/agent-bootstrap/env', json={'joinToken': join['joinToken'], 'hostname': 'timeout-host'})
    assert env.status_code == 200

    with SessionLocal() as db:
        token = db.scalar(select(CrawlerAgentJoinToken).where(CrawlerAgentJoinToken.token_hash == sha256_text(join['joinToken'])))
        assert token is not None
        token.used_at = utcnow() - timedelta(minutes=6)
        token.updated_at = token.used_at
        db.commit()

    rows = client.get('/api/v1/servers/agent-join-tokens', headers=headers, params={'companyId': company['companyId']}).json()['data']
    record = next(row for row in rows if row['agentCode'] == 'resume-guard-agent-timeout')
    assert record['invitationStatus'] == 'FAILED'
    assert record['failureStage'] == 'FIRST_HEARTBEAT_TIMEOUT'
    assert 'docker logs --tail 200 crawler-agent' in record['failureReason']
