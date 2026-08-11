from __future__ import annotations

import os
from pathlib import Path
Path('/tmp/crawler_platform_running_center_1027.db').unlink(missing_ok=True)
os.environ['APP_ENV'] = 'test'
os.environ['DATABASE_URL'] = 'sqlite+pysqlite:////tmp/crawler_platform_running_center_1027.db'
os.environ['REDIS_URL'] = 'redis://localhost:6379/15'
os.environ['JWT_SECRET'] = 'pytest-jwt-secret-for-crawler-platform-1-0-27'
os.environ['SECRET_ENCRYPTION_KEY'] = 'pytest-secret-encryption-key-for-crawler-platform-1-0-27'

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.migration_main import main as migrate
from app.models import CrawlerCompany, CrawlerProject, CrawlerRunContainerSnapshot, CrawlerServer, CrawlerTask, CrawlerTaskRun, SysUser
from app.security import hash_password
from app.utils import utcnow


def _login(client: TestClient, username: str, password: str) -> dict:
    response = client.post('/api/v1/sessions', json={'userName': username, 'password': password})
    if response.json().get('code') == 40901:
        token = response.json()['data']['forceLoginToken']
        response = client.post('/api/v1/sessions', json={'userName': username, 'password': password, 'forceLoginToken': token})
    assert response.status_code == 200, response.text
    return {'Authorization': 'Bearer ' + response.json()['data']['accessToken']}


def test_running_center_uses_company_project_task_model_and_container_snapshot() -> None:
    migrate()
    client = TestClient(app)
    now = utcnow()
    with SessionLocal() as db:
        company = CrawlerCompany(company_code='tenant27', company_name='租户27', status='ENABLED')
        db.add(company)
        db.flush()
        user = SysUser(company_id=company.company_id, user_name='tenant27_ops', nick_name='租户27运维', password_hash=hash_password('Tenant@123456'), role_type='NORMAL_USER', status='ENABLED', password_updated_at=now)
        project = CrawlerProject(company_id=company.company_id, project_code='shop_project', project_name='店铺数据采集', project_key='shop_project', image_repository='registry/shop', status='ENABLED', online_status='READY')
        server = CrawlerServer(company_id=company.company_id, server_code='node27', server_name='执行节点27', server_ip='10.1.0.27', health_status='HEALTHY', capacity_status='NORMAL', metrics={'dockerStatus': 'OK', 'cpuUsage': 30, 'memoryUsage': 55, 'diskUsage': 60, 'availableSlots': 1, 'maxSlots': 2})
        db.add_all([user, project, server])
        db.flush()
        task = CrawlerTask(company_id=company.company_id, project_id=project.project_id, task_code='inventory', task_name='库存采集', entry_module='spiders.shop.inventory', entry_function='run', status='ENABLED')
        db.add(task)
        db.flush()
        run = CrawlerTaskRun(company_id=company.company_id, project_id=project.project_id, task_id=task.task_id, server_id=server.server_id, image_digest='sha256:abc', entry_module=task.entry_module, entry_function=task.entry_function, run_status='FAILED', routing_status='ROUTED', error_summary='容器异常退出')
        db.add(run)
        db.flush()
        snapshot = CrawlerRunContainerSnapshot(company_id=company.company_id, project_id=project.project_id, task_id=task.task_id, run_id=run.run_id, server_id=server.server_id, container_id='abc123', container_name='crawler_shop_inventory', image_digest='sha256:abc', container_status='FAILED', exit_code=1, oom_killed=False, restart_count=0, last_log_line='Traceback error', payload_json={}, observed_at=now)
        db.add(snapshot)
        db.commit()
    headers = _login(client, 'tenant27_ops', 'Tenant@123456')
    response = client.get('/api/v1/running-center', headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data['company']['companyName'] == '租户27'
    assert data['overview']['projectCount'] >= 1
    project = next(item for item in data['projects'] if item['projectCode'] == 'shop_project')
    assert project['singleTaskProject'] is True
    assert project['projectStatus'] == 'HAS_ISSUE'
    task_data = project['tasks'][0]
    assert task_data['taskName'] == '库存采集'
    assert task_data['container']['containerStatus'] == 'FAILED'
    assert task_data['server']['serverName'] == '执行节点27'
    assert task_data['primaryAction'] in {'查看容器', '查看日志'}
