from __future__ import annotations

import os
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

from app.migration_main import main as migrate
from app.main import app


def login(client: TestClient) -> tuple[dict, dict]:
    response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456'})
    if response.json()['code'] == 40901:
        token = response.json()['data']['forceLoginToken']
        response = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456', 'forceLoginToken': token})
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {'code', 'message', 'data'}
    return body['data'], {'Authorization': 'Bearer ' + body['data']['accessToken']}


def test_full_platform_flow() -> None:
    migrate()
    client = TestClient(app)
    data, headers = login(client)
    assert data['user']['isSuperAdmin'] is True

    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'hc', 'companyName': 'H公司'}).json()['data']
    assert company['companyName'] == 'H公司'

    server = client.post('/api/v1/servers', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'srv-b', 'serverName': 'B服务器'}).json()['data']
    assert server['serverCode'] == 'srv-b'

    agent_payload = {'companyId': company['companyId'], 'serverCode': 'srv-b', 'serverName': 'B服务器', 'agentCode': 'agent-b', 'agentName': 'B Agent'}
    agent = client.post('/api/v1/agents', headers=headers, json=agent_payload).json()['data']
    assert 'tokenHash' not in str(agent)
    agent_headers = {'Authorization': 'Agent ' + agent['agentToken']}

    discovery_token = client.post(f"/api/v1/companies/{company['companyId']}/discovery-tokens", headers=headers).json()['data']['discoveryToken']
    manifest = {
        'manifestVersion': '1',
        'projectKey': 'project-a',
        'projectName': '项目A',
        'projectCode': 'project_a',
        'repositoryUrl': 'git@example/project-a',
        'imageRepository': 'repo/project-a',
        'imageDigest': 'sha256:' + 'a' * 64,
        'releaseVersion': '1.0.1',
        'releaseChannel': 'stable',
        'taskDefinitions': [{'definitionKey': 'task_one', 'taskName': '任务一', 'entryModule': 'spiders.task_one', 'entryFunction': 'run'}],
    }
    discovered = client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery_token}, json={'companyId': company['companyId'], 'manifest': manifest}).json()['data']
    assert discovered['discoveryStatus'] == 'READY_TO_IMPORT'

    project = client.post('/api/v1/projects', headers=headers, json={'discoveredProjectId': discovered['discoveredProjectId']}).json()['data']
    client.put(f"/api/v1/projects/{project['projectId']}/servers", headers=headers, json={'servers': [{'serverId': server['serverId'], 'schedulingStatus': 'ENABLED', 'serverRole': 'ACTIVE', 'priority': 100, 'weight': 100, 'maxConcurrency': 4, 'autoEjectEnabled': True, 'autoRecoverEnabled': True}]})
    definitions = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    assert definitions[0]['definitionStatus'] == 'AVAILABLE'

    task = client.post('/api/v1/tasks', headers=headers, json={'definitionId': definitions[0]['definitionId'], 'taskCode': 'task_one', 'taskName': '任务一', 'status': 'ENABLED'}).json()['data']
    run = client.post('/api/v1/runs', headers=headers, json={'taskId': task['taskId'], 'parameters': {}}).json()['data']
    assert run['routingStatus'] == 'WAITING_RESOURCE'

    heartbeat = {'agentInstanceId': 'inst-1', 'dockerStatus': 'OK', 'availableSlots': 2}
    client.post('/api/v1/agent-heartbeats', headers=agent_headers, json=heartbeat)
    claim = client.post('/api/v1/agent-run-claims', headers=agent_headers).json()['data']
    assert claim['runId'] == run['runId']
    assert claim['imageDigest'] == manifest['imageDigest']


def test_single_session_conflict() -> None:
    migrate()
    client = TestClient(app)
    first = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456'})
    if first.json()['code'] == 40901:
        token = first.json()['data']['forceLoginToken']
        first = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456', 'forceLoginToken': token})
    second = client.post('/api/v1/sessions', json={'userName': 'admin', 'password': 'Admin@123456'})
    assert second.status_code == 400
    assert second.json()['code'] == 40901
    assert 'forceLoginToken' in second.json()['data']


def create_flow(client: TestClient, headers: dict, suffix: str, server_codes: list[str] | None = None) -> tuple[dict, dict, list[dict], dict]:
    server_codes = server_codes or [f'srv-{suffix}']
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': f'hc_{suffix}', 'companyName': f'H公司{suffix}'}).json()['data']
    agent_tokens = []
    server_items = []
    for code in server_codes:
        server = client.post('/api/v1/servers', headers=headers, json={'companyId': company['companyId'], 'serverCode': code, 'serverName': f'{code}服务器'}).json()['data']
        server_items.append(server)
        agent = client.post('/api/v1/agents', headers=headers, json={'companyId': company['companyId'], 'serverCode': code, 'serverName': f'{code}服务器', 'agentCode': f'agent-{code}', 'agentName': f'{code} Agent'}).json()['data']
        agent_tokens.append({'serverCode': code, 'headers': {'Authorization': 'Agent ' + agent['agentToken']}})
    discovery_token = client.post(f"/api/v1/companies/{company['companyId']}/discovery-tokens", headers=headers).json()['data']['discoveryToken']
    manifest = {
        'manifestVersion': '1', 'projectKey': f'project-{suffix}', 'projectName': f'项目{suffix}', 'projectCode': f'project_{suffix}',
        'repositoryUrl': 'git@example/project', 'imageRepository': f'repo/project-{suffix}', 'imageDigest': 'sha256:' + ('b' * 64),
        'releaseVersion': '1.0.1', 'releaseChannel': 'stable',
        'taskDefinitions': [{'definitionKey': 'task_one', 'taskName': '任务一', 'entryModule': 'spiders.task_one', 'entryFunction': 'run'}],
    }
    discovered = None
    for code in server_codes:
        discovered = client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery_token}, json={'companyId': company['companyId'], 'manifest': manifest}).json()['data']
    project = client.post('/api/v1/projects', headers=headers, json={'discoveredProjectId': discovered['discoveredProjectId'], 'dispatchMode': 'LOAD_BALANCE'}).json()['data']
    pool_payload = {'servers': [{'serverId': item['serverId'], 'schedulingStatus': 'ENABLED', 'serverRole': 'ACTIVE' if len(server_items) > 1 else 'ACTIVE', 'priority': 100 + idx, 'weight': 100, 'maxConcurrency': 4, 'autoEjectEnabled': True, 'autoRecoverEnabled': True} for idx, item in enumerate(server_items)]}
    client.put(f"/api/v1/projects/{project['projectId']}/servers", headers=headers, json=pool_payload)
    return company, project, agent_tokens, {'token': discovery_token, 'manifest': manifest}


def test_permissions_release_and_dashboard_scope() -> None:
    migrate()
    client = TestClient(app)
    _, admin_headers = login(client)
    company, project, _, _ = create_flow(client, admin_headers, 'perm')
    user = client.post('/api/v1/users', headers=admin_headers, json={'companyId': company['companyId'], 'userName': 'normal_perm', 'nickName': '普通用户', 'password': 'Normal@123456', 'roleType': 'NORMAL_USER'}).json()['data']
    normal_login = client.post('/api/v1/sessions', json={'userName': 'normal_perm', 'password': 'Normal@123456'}).json()['data']
    normal_headers = {'Authorization': 'Bearer ' + normal_login['accessToken']}
    client.patch('/api/v1/users/me/password', headers=normal_headers, json={'oldPassword': 'Normal@123456', 'newPassword': 'Normal@234567', 'confirmPassword': 'Normal@234567'})
    normal_login = client.post('/api/v1/sessions', json={'userName': 'normal_perm', 'password': 'Normal@234567'}).json()['data']
    normal_headers = {'Authorization': 'Bearer ' + normal_login['accessToken']}
    assert client.get('/api/v1/dashboard-summaries', headers=normal_headers).status_code == 403
    releases = client.get('/api/v1/releases', headers=normal_headers).json()['data']
    assert len(releases) == 1
    assert releases[0]['companyId'] == company['companyId']


def test_formal_project_release_sync_after_cicd_report() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, _, discovery = create_flow(client, headers, 'sync')
    manifest = {**discovery['manifest'], 'releaseVersion': '1.1.0', 'imageDigest': 'sha256:' + ('c' * 64), 'taskDefinitions': [
        {'definitionKey': 'task_one', 'taskName': '任务一新版', 'entryModule': 'spiders.task_one', 'entryFunction': 'run'},
        {'definitionKey': 'task_two', 'taskName': '任务二', 'entryModule': 'spiders.task_two', 'entryFunction': 'run'},
    ]}
    client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery['token']}, json={'companyId': company['companyId'], 'manifest': manifest})
    releases = client.get('/api/v1/releases', headers=headers, params={'projectId': project['projectId']}).json()['data']
    assert releases[0]['version'] == '1.1.0'
    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    keys = {item['definitionKey']: item for item in defs}
    assert keys['task_two']['definitionStatus'] == 'AVAILABLE'
    run_task = client.post('/api/v1/tasks', headers=headers, json={'definitionId': keys['task_two']['definitionId'], 'taskCode': 'task_two', 'taskName': '任务二', 'status': 'ENABLED'}).json()['data']
    run = client.post('/api/v1/runs', headers=headers, json={'taskId': run_task['taskId'], 'parameters': {'x': 1}}).json()['data']
    assert run['imageDigest'] == manifest['imageDigest']


def test_agent_claim_entry_and_auto_eject_reroute() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, agents, _ = create_flow(client, headers, 'route', ['srv-route-b', 'srv-route-c'])
    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    task = client.post('/api/v1/tasks', headers=headers, json={'definitionId': defs[0]['definitionId'], 'taskCode': 'task_one_route', 'taskName': '任务一路由', 'status': 'ENABLED'}).json()['data']
    # B 先上报资源耗尽，C 正常，运行应自动路由到 C。
    for _ in range(3):
        client.post('/api/v1/agent-heartbeats', headers=agents[0]['headers'], json={'agentInstanceId': 'inst-b', 'dockerStatus': 'OK', 'availableSlots': 0})
    client.post('/api/v1/agent-heartbeats', headers=agents[1]['headers'], json={'agentInstanceId': 'inst-c', 'dockerStatus': 'OK', 'availableSlots': 2})
    run = client.post('/api/v1/runs', headers=headers, json={'taskId': task['taskId'], 'parameters': {'site': 'US'}}).json()['data']
    assert run['routingStatus'] == 'ROUTED'
    claim = client.post('/api/v1/agent-run-claims', headers=agents[1]['headers'], json={'agentInstanceId': 'inst-c'}).json()['data']
    assert claim['entryModule'] == 'spiders.task_one'
    assert claim['entryFunction'] == 'run'
    assert claim['parameters']['site'] == 'US'


def test_non_idempotent_lost_does_not_auto_retry_and_p0_created() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, agents, _ = create_flow(client, headers, 'lost')
    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    from app.db import SessionLocal
    from app.models import CrawlerProjectTaskDefinition, CrawlerTaskRun, SysAlertEvent
    with SessionLocal() as db:
        definition = db.get(CrawlerProjectTaskDefinition, defs[0]['definitionId'])
        definition.idempotency_policy = 'NON_IDEMPOTENT'
        db.commit()
    task = client.post('/api/v1/tasks', headers=headers, json={'definitionId': defs[0]['definitionId'], 'taskCode': 'task_one_lost', 'taskName': '任务一失联', 'status': 'ENABLED', 'maxRetryCount': 2}).json()['data']
    client.post('/api/v1/agent-heartbeats', headers=agents[0]['headers'], json={'agentInstanceId': 'inst-lost', 'dockerStatus': 'OK', 'availableSlots': 2})
    client.post('/api/v1/runs', headers=headers, json={'taskId': task['taskId']}).json()['data']
    claim = client.post('/api/v1/agent-run-claims', headers=agents[0]['headers'], json={'agentInstanceId': 'inst-lost'}).json()['data']
    with SessionLocal() as db:
        run = db.get(CrawlerTaskRun, claim['runId'])
        run.lease_expires_at = __import__('datetime').datetime(2000, 1, 1)
        db.commit()
        from app.services.run_service import RunService
        RunService(db).mark_lost_runs()
        retry_count = db.query(CrawlerTaskRun).filter(CrawlerTaskRun.task_id == task['taskId']).count()
        alert_count = db.query(SysAlertEvent).filter(SysAlertEvent.severity == 'P0').count()
    assert retry_count == 1
    assert alert_count >= 1


def test_sharded_task_creates_child_runs() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, agents, discovery = create_flow(client, headers, 'shard')
    manifest = {**discovery['manifest'], 'releaseVersion': '1.1.0', 'imageDigest': 'sha256:' + ('d' * 64), 'taskDefinitions': [
        {'definitionKey': 'task_shard', 'taskName': '分片任务', 'entryModule': 'spiders.shard', 'entryFunction': 'run', 'executionMode': 'SHARDED', 'resourceRequirements': {'requiredNodeCount': 2, 'maxParallelNodes': 2}},
    ]}
    client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery['token']}, json={'companyId': company['companyId'], 'manifest': manifest})
    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    shard_def = [item for item in defs if item['definitionKey'] == 'task_shard'][0]
    task = client.post('/api/v1/tasks', headers=headers, json={'definitionId': shard_def['definitionId'], 'taskCode': 'task_shard', 'taskName': '分片任务', 'status': 'ENABLED'}).json()['data']
    run = client.post('/api/v1/runs', headers=headers, json={'taskId': task['taskId']}).json()['data']
    from app.db import SessionLocal
    from app.models import CrawlerTaskRun
    with SessionLocal() as db:
        children = db.query(CrawlerTaskRun).filter(CrawlerTaskRun.parent_run_id == run['runId']).count()
    assert children == 2


def test_queue_overlap_waits_and_releases_after_active_finish() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, agents, _ = create_flow(client, headers, 'queue')
    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    task = client.post('/api/v1/tasks', headers=headers, json={'definitionId': defs[0]['definitionId'], 'taskCode': 'task_queue', 'taskName': '排队任务', 'status': 'ENABLED', 'scheduleStatus': 'ENABLED', 'scheduleType': 'CRON', 'cronExpression': '* * * * *', 'overlapPolicy': 'QUEUE'}).json()['data']
    client.post('/api/v1/agent-heartbeats', headers=agents[0]['headers'], json={'agentInstanceId': 'inst-q', 'dockerStatus': 'OK', 'availableSlots': 2})
    from app.db import SessionLocal
    from app.models import CrawlerProject, CrawlerTaskRun, CrawlerTaskSchedule
    from app.services.scheduler_service import SchedulerService
    from app.services.run_service import RunService
    from app.utils import utcnow
    with SessionLocal() as db:
        db.get(CrawlerProject, project['projectId']).online_status = 'ONLINE'
        schedule = db.query(CrawlerTaskSchedule).filter(CrawlerTaskSchedule.task_id == task['taskId']).one()
        schedule.next_run_at = utcnow()
        db.commit()
        SchedulerService(db).dispatch_due_schedules()
        active = db.query(CrawlerTaskRun).filter(CrawlerTaskRun.task_id == task['taskId']).one()
        active.run_status = 'RUNNING'
        active.routing_status = 'ROUTED'
        schedule.next_run_at = utcnow()
        db.commit()
        SchedulerService(db).dispatch_due_schedules()
        queued = db.query(CrawlerTaskRun).filter(CrawlerTaskRun.task_id == task['taskId'], CrawlerTaskRun.run_status == 'QUEUED').one()
        assert queued.routing_status == 'WAITING_RESOURCE'
        active.run_status = 'SUCCEEDED'
        active.finished_at = utcnow()
        db.commit()
        from app.services.routing_service import RoutingService
        RoutingService(db).reroute_or_wait_unclaimed()
        db.refresh(queued)
        assert queued.routing_status == 'ROUTED'


def test_capability_routing_operation_log_and_alert_ack() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, agents, _ = create_flow(client, headers, 'cap', ['srv-cap-a', 'srv-cap-b'])
    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    from app.db import SessionLocal
    from app.models import CrawlerProjectTaskDefinition, SysAlertEvent, SysOperationLog
    with SessionLocal() as db:
        definition = db.get(CrawlerProjectTaskDefinition, defs[0]['definitionId'])
        definition.required_capabilities = {'browser': True}
        db.add(SysAlertEvent(severity='P0', alert_status='OPEN', alert_type='TEST', title='测试P0', content='能力测试', fingerprint='test_capability_alert'))
        db.commit()
    task = client.post('/api/v1/tasks', headers=headers, json={'definitionId': defs[0]['definitionId'], 'taskCode': 'task_cap', 'taskName': '能力任务', 'status': 'ENABLED'}).json()['data']
    client.post('/api/v1/agent-heartbeats', headers=agents[0]['headers'], json={'agentInstanceId': 'inst-cap-a', 'dockerStatus': 'OK', 'availableSlots': 2, 'capabilities': {'browser': False}})
    client.post('/api/v1/agent-heartbeats', headers=agents[1]['headers'], json={'agentInstanceId': 'inst-cap-b', 'dockerStatus': 'OK', 'availableSlots': 2, 'capabilities': {'browser': True}})
    run = client.post('/api/v1/runs', headers=headers, json={'taskId': task['taskId']}).json()['data']
    claim = client.post('/api/v1/agent-run-claims', headers=agents[1]['headers'], json={'agentInstanceId': 'inst-cap-b'}).json()['data']
    assert claim['runId'] == run['runId']
    alerts = client.get('/api/v1/alerts', headers=headers).json()['data']
    alert_id = [item['alertId'] for item in alerts if item['fingerprint'] == 'test_capability_alert'][0]
    assert client.patch(f'/api/v1/alerts/{alert_id}/acknowledgement', headers=headers).json()['data']['alertStatus'] == 'ACKED'
    with SessionLocal() as db:
        assert db.query(SysOperationLog).count() > 0


def test_scheduled_sharded_unique_key_and_parent_aggregation() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, agents, discovery = create_flow(client, headers, 'schedshard')
    manifest = {**discovery['manifest'], 'releaseVersion': '1.1.0', 'imageDigest': 'sha256:' + ('e' * 64), 'taskDefinitions': [
        {'definitionKey': 'task_sched_shard', 'taskName': '定时分片任务', 'entryModule': 'spiders.shard', 'entryFunction': 'run', 'executionMode': 'SHARDED', 'resourceRequirements': {'requiredNodeCount': 2, 'maxParallelNodes': 2}},
    ]}
    client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery['token']}, json={'companyId': company['companyId'], 'manifest': manifest})
    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    shard_def = [item for item in defs if item['definitionKey'] == 'task_sched_shard'][0]
    task = client.post('/api/v1/tasks', headers=headers, json={'definitionId': shard_def['definitionId'], 'taskCode': 'task_sched_shard', 'taskName': '定时分片任务', 'status': 'ENABLED', 'scheduleStatus': 'ENABLED', 'scheduleType': 'CRON', 'cronExpression': '* * * * *'}).json()['data']
    from app.db import SessionLocal
    from app.models import CrawlerProject, CrawlerTaskRun, CrawlerTaskSchedule
    from app.services.scheduler_service import SchedulerService
    from app.services.run_service import RunService
    from app.utils import utcnow
    with SessionLocal() as db:
        db.get(CrawlerProject, project['projectId']).online_status = 'ONLINE'
        schedule = db.query(CrawlerTaskSchedule).filter(CrawlerTaskSchedule.task_id == task['taskId']).one()
        schedule.next_run_at = utcnow()
        db.commit()
        SchedulerService(db).dispatch_due_schedules()
        parent = db.query(CrawlerTaskRun).filter(CrawlerTaskRun.task_id == task['taskId'], CrawlerTaskRun.parent_run_id.is_(None)).one()
        children = db.query(CrawlerTaskRun).filter(CrawlerTaskRun.parent_run_id == parent.run_id).all()
        assert len(children) == 2
        for child in children:
            child.run_status = 'SUCCEEDED'
            child.finished_at = utcnow()
        db.commit()
        children2 = db.query(CrawlerTaskRun).filter(CrawlerTaskRun.parent_run_id == parent.run_id).all()
        assert {c.run_status for c in children2} == {'SUCCEEDED'}
        RunService(db).aggregate_sharded_parent(parent.run_id)
        db.refresh(parent)
        assert parent.run_status == 'SUCCEEDED'


def test_cron_preview_validation_and_schedule_update() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    ok_resp = client.post('/api/v1/cron-previews', headers=headers, json={'cronExpression': '*/30 * * * *', 'timezone': 'Asia/Shanghai', 'count': 5})
    assert ok_resp.status_code == 200
    assert len(ok_resp.json()['data']['nextTimes']) == 5
    bad_resp = client.post('/api/v1/cron-previews', headers=headers, json={'cronExpression': '0 0/5 * * * ?', 'timezone': 'Asia/Shanghai', 'count': 5})
    assert bad_resp.status_code == 400
    assert bad_resp.json()['code'] == 40081


def test_static_sch_parser_rejects_dynamic_tasks(tmp_path) -> None:
    import subprocess, sys
    root = Path(__file__).resolve().parents[2]
    sch = tmp_path / 'sch.py'
    sch.write_text('def make():\n    raise RuntimeError("should not run")\nTASKS = make()\n', encoding='utf-8')
    result = subprocess.run([
        sys.executable,
        str(root / 'cicd' / 'parse_sch_manifest.py'),
        '--sch', str(sch),
        '--output', str(tmp_path / 'manifest.json'),
        '--project-key', 'p', '--project-code', 'p', '--project-name', '项目',
        '--image-repository', 'repo/p', '--image-digest', 'sha256:' + '1' * 64,
        '--release-version', '1.0.1',
    ], text=True, capture_output=True)
    assert result.returncode != 0
    assert 'TASKS 必须是纯静态字面量' in result.stderr


def test_static_sch_parser_accepts_literal_tasks_and_agent_capabilities(monkeypatch, tmp_path) -> None:
    import importlib, subprocess, sys
    root = Path(__file__).resolve().parents[2]
    sch = tmp_path / 'sch.py'
    sch.write_text('TASKS = [{"definitionKey":"t","taskName":"任务","entryModule":"spiders.t","entryFunction":"run","requiredCapabilities":{"browser": True}}]\n', encoding='utf-8')
    manifest_path = tmp_path / 'manifest.json'
    result = subprocess.run([
        sys.executable,
        str(root / 'cicd' / 'parse_sch_manifest.py'),
        '--sch', str(sch),
        '--output', str(manifest_path),
        '--project-key', 'p', '--project-code', 'p', '--project-name', '项目',
        '--image-repository', 'repo/p', '--image-digest', 'sha256:' + '2' * 64,
        '--release-version', '1.0.1',
    ], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert manifest_path.exists()
    monkeypatch.setenv('AGENT_CAPABILITIES_JSON', '{"browser":true,"proxy":false}')
    sys.path.insert(0, str(root / 'agent'))
    module = importlib.import_module('crawler_agent.config')
    cfg = module.AgentConfig()
    assert cfg.capabilities() == {'browser': True, 'proxy': False}


def test_shared_environment_task_runtime_policy_and_claim_payload() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, agents, discovery = create_flow(client, headers, 'sharedenv')
    manifest = {**discovery['manifest'], 'releaseVersion': '1.2.0', 'imageDigest': 'sha256:' + ('f' * 64), 'taskDefinitions': [
        {'definitionKey': 'task_shared', 'taskName': '共享环境任务', 'entryModule': 'spiders.shared', 'entryFunction': 'run', 'runtimeMode': 'SHARED_ENV_ISOLATED', 'taskGroup': 'api', 'taskMaxConcurrency': 2, 'groupMaxConcurrency': 3, 'shmSizeMb': 128, 'logLimitMb': 20, 'resourceLocks': ['account:demo']},
    ]}
    client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery['token']}, json={'companyId': company['companyId'], 'manifest': manifest})
    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    definition = [item for item in defs if item['definitionKey'] == 'task_shared'][0]
    assert definition['runtimeMode'] == 'SHARED_ENV_ISOLATED'
    task = client.post('/api/v1/tasks', headers=headers, json={'definitionId': definition['definitionId'], 'taskCode': 'task_shared', 'taskName': '共享环境任务', 'status': 'ENABLED'}).json()['data']
    assert task['taskGroup'] == 'api'
    client.post('/api/v1/agent-heartbeats', headers=agents[0]['headers'], json={'agentInstanceId': 'inst-shared', 'dockerStatus': 'OK', 'availableSlots': 2})
    run = client.post('/api/v1/runs', headers=headers, json={'taskId': task['taskId']}).json()['data']
    claim = client.post('/api/v1/agent-run-claims', headers=agents[0]['headers'], json={'agentInstanceId': 'inst-shared'}).json()['data']
    assert claim['runId'] == run['runId']
    assert claim['projectCode'] == project['projectCode']
    assert claim['taskCode'] == 'task_shared'
    assert claim['runtimeMode'] == 'SHARED_ENV_ISOLATED'
    assert claim['taskGroup'] == 'api'
    assert claim['shmSizeMb'] == 128
    assert claim['logLimitMb'] == 20
    assert claim['resourceLocks'] == ['account:demo']


def test_resource_lock_blocks_conflicting_runs() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, agents, discovery = create_flow(client, headers, 'lock')
    manifest = {**discovery['manifest'], 'releaseVersion': '1.2.0', 'imageDigest': 'sha256:' + ('9' * 64), 'taskDefinitions': [
        {'definitionKey': 'task_lock_a', 'taskName': '锁任务A', 'entryModule': 'spiders.a', 'entryFunction': 'run', 'taskMaxConcurrency': 10, 'groupMaxConcurrency': 10, 'resourceLocks': ['account:x']},
        {'definitionKey': 'task_lock_b', 'taskName': '锁任务B', 'entryModule': 'spiders.b', 'entryFunction': 'run', 'taskMaxConcurrency': 10, 'groupMaxConcurrency': 10, 'resourceLocks': ['account:x']},
    ]}
    client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery['token']}, json={'companyId': company['companyId'], 'manifest': manifest})
    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    by_key = {item['definitionKey']: item for item in defs}
    a = client.post('/api/v1/tasks', headers=headers, json={'definitionId': by_key['task_lock_a']['definitionId'], 'taskCode': 'task_lock_a', 'taskName': '锁任务A', 'status': 'ENABLED'}).json()['data']
    b = client.post('/api/v1/tasks', headers=headers, json={'definitionId': by_key['task_lock_b']['definitionId'], 'taskCode': 'task_lock_b', 'taskName': '锁任务B', 'status': 'ENABLED'}).json()['data']
    client.post('/api/v1/agent-heartbeats', headers=agents[0]['headers'], json={'agentInstanceId': 'inst-lock', 'dockerStatus': 'OK', 'availableSlots': 3})
    first = client.post('/api/v1/runs', headers=headers, json={'taskId': a['taskId']}).json()['data']
    assert first['routingStatus'] == 'ROUTED'
    second = client.post('/api/v1/runs', headers=headers, json={'taskId': b['taskId']}).json()['data']
    assert second['routingStatus'] == 'WAITING_RESOURCE'
    assert '资源锁被占用' in second['routingReason']


def test_102_password_change_reset_and_camel_contract() -> None:
    migrate()
    client = TestClient(app)
    _, admin_headers = login(client)
    company = client.post('/api/v1/companies', headers=admin_headers, json={'companyCode': 'pwd102', 'companyName': '密码公司'}).json()['data']
    user = client.post('/api/v1/users', headers=admin_headers, json={'companyId': company['companyId'], 'userName': 'normal_pwd_102', 'nickName': '密码用户', 'password': 'Normal@123456', 'roleType': 'NORMAL_USER'}).json()['data']
    assert user['mustChangePassword'] is True
    normal_login = client.post('/api/v1/sessions', json={'userName': 'normal_pwd_102', 'password': 'Normal@123456'}).json()['data']
    assert normal_login['passwordChangeRequired'] is True
    normal_headers = {'Authorization': 'Bearer ' + normal_login['accessToken']}
    blocked = client.get('/api/v1/projects', headers=normal_headers).json()
    assert blocked['code'] == 40320
    assert blocked['data']['passwordChangeRequired'] is True
    profile = client.get(f"/api/v1/sessions/{normal_login['sessionId']}", headers=normal_headers).json()
    assert profile['code'] == 200
    changed = client.patch('/api/v1/users/current/passwords', headers=normal_headers, json={'oldPassword': 'Normal@123456', 'newPassword': 'Normal@654321', 'confirmPassword': 'Normal@654321'}).json()['data']
    assert changed['reloginRequired'] is True
    reset = client.post(f"/api/v1/users/{user['userId']}/password-resets", headers=admin_headers, json={'newPassword': 'Reset@123456', 'mustChangePassword': True}).json()['data']
    assert reset['mustChangePassword'] is True
    from app.db import SessionLocal
    from app.models import SysOperationLog
    with SessionLocal() as db:
        payload_text = '\n'.join(str(row.after_data) for row in db.query(SysOperationLog).all())
        assert 'Normal@654321' not in payload_text
        assert 'Reset@123456' not in payload_text


def test_108_admin_self_password_reset_does_not_require_password_change_loop() -> None:
    migrate()
    client = TestClient(app)
    _, admin_headers = login(client)
    company = client.post("/api/v1/companies", headers=admin_headers, json={"companyCode": "selfpwd108", "companyName": "自重置密码公司"}).json()["data"]
    self_admin = client.post("/api/v1/users", headers=admin_headers, json={"companyId": company["companyId"], "userName": "self_admin_108", "nickName": "自重置管理员", "password": "SelfAdmin@123456", "roleType": "SUPER_ADMIN"}).json()["data"]
    self_login = client.post("/api/v1/sessions", json={"userName": "self_admin_108", "password": "SelfAdmin@123456"}).json()["data"]
    self_headers = {"Authorization": "Bearer " + self_login["accessToken"]}
    first_change = client.patch("/api/v1/users/me/password", headers=self_headers, json={"oldPassword": "SelfAdmin@123456", "newPassword": "SelfAdmin@234567", "confirmPassword": "SelfAdmin@234567"}).json()
    assert first_change["code"] == 200
    self_login = client.post("/api/v1/sessions", json={"userName": "self_admin_108", "password": "SelfAdmin@234567"}).json()["data"]
    self_headers = {"Authorization": "Bearer " + self_login["accessToken"]}
    reset = client.post("/api/v1/users/{}/password-resets".format(self_admin["userId"]), headers=self_headers, json={"newPassword": "SelfAdmin@765432", "mustChangePassword": True}).json()
    assert reset["code"] == 200
    assert reset["data"]["mustChangePassword"] is False
    relogin = client.post("/api/v1/sessions", json={"userName": "self_admin_108", "password": "SelfAdmin@765432"}).json()["data"]
    assert relogin["passwordChangeRequired"] is False
    assert relogin["user"]["passwordChangeRequired"] is False
    from app.db import SessionLocal
    from app.models import SysUser
    with SessionLocal() as db:
        saved = db.query(SysUser).filter(SysUser.user_name == "self_admin_108").one()
        assert saved.must_change_password is False


def test_102_daily_times_preview_contract() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    payload = {'scheduleConfig': {'mode': 'daily_times', 'times': ['12:00', '07:00', '09:00', '07:00'], 'timezone': 'Asia/Shanghai'}, 'timezone': 'Asia/Shanghai', 'count': 5}
    body = client.post('/api/v1/cron-previews', headers=headers, json=payload).json()['data']
    assert body['cronExpression'] == '0 7,9,12 * * *'
    assert body['scheduleConfig']['times'] == ['07:00', '09:00', '12:00']
    assert len(body['nextTimes']) == 5


def test_102_run_log_v2_and_audit_filter_contract() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, agents, _ = create_flow(client, headers, 'log102')
    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    task = client.post('/api/v1/tasks', headers=headers, json={'definitionId': defs[0]['definitionId'], 'taskCode': 'task_log_102', 'taskName': '日志任务', 'status': 'ENABLED'}).json()['data']
    run = client.post('/api/v1/runs', headers=headers, json={'taskId': task['taskId']}).json()['data']
    client.post('/api/v1/agent-heartbeats', headers=agents[0]['headers'], json={'agentInstanceId': 'inst-log-102', 'dockerStatus': 'OK', 'availableSlots': 2, 'cpuUsage': 10, 'memoryUsage': 20, 'diskUsage': 30, 'inodeUsage': 5, 'maxSlots': 4, 'projectDataRootWritable': True, 'dockerSockAccessible': True})
    claim = client.post('/api/v1/agent-run-claims', headers=agents[0]['headers'], json={'agentInstanceId': 'inst-log-102'}).json()['data']
    from app.db import SessionLocal
    from app.models import SysOperationLog
    with SessionLocal() as db:
        before_count = db.query(SysOperationLog).count()
    event_payload = {'runId': run['runId'], 'leaseToken': claim['leaseToken'], 'eventType': 'SPIDER_STARTED', 'eventLevel': 'INFO', 'stage': 'BOOT', 'message': 'started', 'agentInstanceId': 'inst-log-102'}
    client.post('/api/v1/agent-run-events', headers=agents[0]['headers'], json=event_payload)
    client.post('/api/v1/agent-run-log-chunks', headers=agents[0]['headers'], json={'runId': run['runId'], 'leaseToken': claim['leaseToken'], 'stream': 'stdout', 'seq': 1, 'offsetStart': 0, 'offsetEnd': 12, 'content': 'hello log\n', 'agentInstanceId': 'inst-log-102'})
    client.post('/api/v1/agent-run-log-finalizations', headers=agents[0]['headers'], json={'runId': run['runId'], 'leaseToken': claim['leaseToken'], 'logStatus': 'COMPLETE', 'logPath': '/logs/run.log', 'logTruncated': False, 'agentInstanceId': 'inst-log-102'})
    events = client.get(f"/api/v1/runs/{run['runId']}/events", headers=headers).json()['data']
    tail = client.get(f"/api/v1/runs/{run['runId']}/log-tails", headers=headers).json()['data']
    diagnosis = client.get(f"/api/v1/runs/{run['runId']}/diagnoses", headers=headers).json()['data']
    assert any(item['eventType'] == 'SPIDER_STARTED' for item in events)
    assert tail['chunks'][0]['content'] == 'hello log\n'
    assert diagnosis['logStatus'] == 'COMPLETE'
    with SessionLocal() as db:
        after_count = db.query(SysOperationLog).count()
        assert after_count == before_count


def test_102_business_multi_time_cron_supports_distinct_minutes_and_weekly_monthly() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)

    daily = client.post('/api/v1/cron-previews', headers=headers, json={
        'scheduleConfig': {'mode': 'daily_times', 'times': ['09:45', '07:15', '12:00', '07:15']},
        'timezone': 'Asia/Shanghai',
        'count': 5,
    }).json()['data']
    assert daily['cronExpression'] == '15 7 * * * ; 45 9 * * * ; 0 12 * * *'
    assert daily['scheduleConfig']['times'] == ['07:15', '09:45', '12:00']
    assert len(daily['nextTimes']) == 5

    weekly = client.post('/api/v1/cron-previews', headers=headers, json={
        'scheduleConfig': {'mode': 'weekly_times', 'weekdays': [5, 1, 1], 'times': ['08:10', '20:40']},
        'timezone': 'Asia/Shanghai',
        'count': 5,
    }).json()['data']
    assert weekly['scheduleConfig']['mode'] == 'weekly_times'
    assert weekly['scheduleConfig']['weekdays'] == [1, 5]
    assert weekly['cronExpression'] == '10 8 * * 1,5 ; 40 20 * * 1,5'

    monthly = client.post('/api/v1/cron-previews', headers=headers, json={
        'scheduleConfig': {'mode': 'monthly_times', 'days': [15, 1, 1], 'times': ['06:00', '18:30']},
        'timezone': 'Asia/Shanghai',
        'count': 5,
    }).json()['data']
    assert monthly['scheduleConfig']['mode'] == 'monthly_times'
    assert monthly['scheduleConfig']['days'] == [1, 15]
    assert monthly['cronExpression'] == '0 6 1,15 * * ; 30 18 1,15 * *'


def test_128_account_session_path_and_create_password_policy_contract() -> None:
    migrate()
    client = TestClient(app)
    _, admin_headers = login(client)
    wrong_session = client.get('/api/v1/sessions/not-current-session', headers=admin_headers)
    assert wrong_session.status_code == 403
    assert wrong_session.json()['code'] == 40321
    company = client.post('/api/v1/companies', headers=admin_headers, json={'companyCode': 'pwdpolicy128', 'companyName': '密码策略公司'}).json()['data']
    weak = client.post('/api/v1/users', headers=admin_headers, json={'companyId': company['companyId'], 'userName': 'weak_pwd_128', 'nickName': '弱密码用户', 'password': 'password1', 'roleType': 'NORMAL_USER'}).json()
    assert weak['code'] == 40024


def test_102_password_change_canonical_me_route_and_old_token_revoked() -> None:
    migrate()
    client = TestClient(app)
    _, admin_headers = login(client)
    company = client.post('/api/v1/companies', headers=admin_headers, json={'companyCode': 'pwdme102', 'companyName': '密码路由公司'}).json()['data']
    user = client.post('/api/v1/users', headers=admin_headers, json={'companyId': company['companyId'], 'userName': 'normal_pwd_me_102', 'nickName': '密码路由用户', 'password': 'Normal@123456', 'roleType': 'NORMAL_USER'}).json()['data']
    login_body = client.post('/api/v1/sessions', json={'userName': 'normal_pwd_me_102', 'password': 'Normal@123456'}).json()['data']
    normal_headers = {'Authorization': 'Bearer ' + login_body['accessToken']}
    changed = client.patch('/api/v1/users/me/password', headers=normal_headers, json={'oldPassword': 'Normal@123456', 'newPassword': 'Normal@987654', 'confirmPassword': 'Normal@987654'}).json()
    assert changed['code'] == 200
    assert changed['data']['reloginRequired'] is True
    # 修改密码会撤销当前 token，旧 token 不应再能访问业务接口。
    assert client.get('/api/v1/projects', headers=normal_headers).status_code == 401
    relogin_body = client.post('/api/v1/sessions', json={'userName': 'normal_pwd_me_102', 'password': 'Normal@987654'}).json()['data']
    assert relogin_body['passwordChangeRequired'] is False
    assert relogin_body['user']['passwordChangeRequired'] is False
    reset = client.post(f"/api/v1/users/{user['userId']}/password-resets", headers=admin_headers, json={'newPassword': 'Reset@987654', 'mustChangePassword': True}).json()['data']
    assert reset['mustChangePassword'] is True


def test_128_frontend_forced_password_change_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / 'frontend' / 'src' / 'layouts' / 'MainLayout.vue').read_text(encoding='utf-8')
    assert 'apiErrorData' in source
    assert 'payload?.message' in source
    assert 'passwordError' in source
    assert 'passwordFormProblem' in source
    assert '<router-view v-else />' in source
    assert ':close-on-press-escape="!passwordRequired"' in source
    assert '新密码至少 8 位' in source


def test_128_frontend_user_admin_password_error_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / 'frontend' / 'src' / 'views' / 'UsersPage.vue').read_text(encoding='utf-8')
    assert 'apiErrorData' in source
    assert 'showApiError' in source
    assert '密码至少 8 位' in source
    assert '首次登录后仍会被要求再次修改' in source


def test_102_frontend_run_log_routes_match_backend_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    api_source = (root / 'frontend' / 'src' / 'api' / 'platform.ts').read_text(encoding='utf-8')
    assert '/log-tails' in api_source
    assert '/diagnoses' in api_source
    assert '/logs/tail' not in api_source
    assert '/diagnosis`' not in api_source


def test_pinned_release_must_belong_to_task_project() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company_a, project_a, _, _ = create_flow(client, headers, 'pin_a')
    company_b, project_b, _, _ = create_flow(client, headers, 'pin_b')
    defs_a = client.get(f"/api/v1/projects/{project_a['projectId']}/task-definitions", headers=headers).json()['data']
    from app.db import SessionLocal
    from app.models import CrawlerProjectRelease
    with SessionLocal() as db:
        foreign_release = db.query(CrawlerProjectRelease).filter(CrawlerProjectRelease.project_id == project_b['projectId']).order_by(CrawlerProjectRelease.release_id.desc()).first()
        foreign_release_id = foreign_release.release_id
    rejected = client.post('/api/v1/tasks', headers=headers, json={
        'definitionId': defs_a[0]['definitionId'],
        'taskCode': 'task_foreign_release',
        'taskName': '跨项目镜像任务',
        'status': 'ENABLED',
        'imagePolicy': 'PINNED',
        'fixedReleaseId': foreign_release_id,
    })
    assert rejected.status_code == 400
    assert rejected.json()['code'] == 40055
    task = client.post('/api/v1/tasks', headers=headers, json={
        'definitionId': defs_a[0]['definitionId'],
        'taskCode': 'task_valid_release_scope',
        'taskName': '合法镜像任务',
        'status': 'ENABLED',
    }).json()['data']
    update_rejected = client.patch(f"/api/v1/tasks/{task['taskId']}", headers=headers, json={
        'imagePolicy': 'PINNED',
        'fixedReleaseId': foreign_release_id,
    })
    assert update_rejected.status_code == 400
    assert update_rejected.json()['code'] == 40055
    from app.db import SessionLocal
    from app.models import CrawlerTask
    with SessionLocal() as db:
        stored = db.get(CrawlerTask, task['taskId'])
        stored.image_policy = 'PINNED'
        stored.fixed_release_id = None
        db.commit()
    run_rejected = client.post('/api/v1/runs', headers=headers, json={'taskId': task['taskId']})
    assert run_rejected.status_code == 400
    assert run_rejected.json()['code'] == 40064


def test_scheduler_duplicate_trigger_does_not_rollback_previous_schedule() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, _, discovery = create_flow(client, headers, 'scheddup')
    manifest = {**discovery['manifest'], 'releaseVersion': '1.1.0', 'imageDigest': 'sha256:' + ('f' * 64), 'taskDefinitions': [
        {'definitionKey': 'task_dup_a', 'taskName': '重复A', 'entryModule': 'spiders.dup_a', 'entryFunction': 'run'},
        {'definitionKey': 'task_dup_b', 'taskName': '重复B', 'entryModule': 'spiders.dup_b', 'entryFunction': 'run'},
    ]}
    client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery['token']}, json={'companyId': company['companyId'], 'manifest': manifest})
    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    defs_by_key = {row['definitionKey']: row for row in defs}
    task_a = client.post('/api/v1/tasks', headers=headers, json={'definitionId': defs_by_key['task_dup_a']['definitionId'], 'taskCode': 'task_dup_a', 'taskName': '重复A', 'status': 'ENABLED', 'scheduleStatus': 'ENABLED', 'scheduleType': 'CRON', 'cronExpression': '* * * * *'}).json()['data']
    task_b = client.post('/api/v1/tasks', headers=headers, json={'definitionId': defs_by_key['task_dup_b']['definitionId'], 'taskCode': 'task_dup_b', 'taskName': '重复B', 'status': 'ENABLED', 'scheduleStatus': 'ENABLED', 'scheduleType': 'CRON', 'cronExpression': '* * * * *'}).json()['data']
    from datetime import datetime
    from app.db import SessionLocal
    from app.models import CrawlerProject, CrawlerTaskRun, CrawlerTaskSchedule
    from app.services.scheduler_service import SchedulerService
    scheduled_at = datetime(2000, 1, 1, 0, 0, 0)
    with SessionLocal() as db:
        db.get(CrawlerProject, project['projectId']).online_status = 'ONLINE'
        schedule_a = db.query(CrawlerTaskSchedule).filter(CrawlerTaskSchedule.task_id == task_a['taskId']).one()
        schedule_b = db.query(CrawlerTaskSchedule).filter(CrawlerTaskSchedule.task_id == task_b['taskId']).one()
        # dispatch_due_schedules() scans all due schedules in the database.  This
        # contract test validates only the duplicate-trigger behavior for the two
        # schedules created here, so older schedules left by previous tests must not
        # participate and make the created counter time-dependent in CI.
        db.query(CrawlerTaskSchedule).filter(
            CrawlerTaskSchedule.schedule_id.notin_([schedule_a.schedule_id, schedule_b.schedule_id])
        ).update({CrawlerTaskSchedule.schedule_status: 'DISABLED'}, synchronize_session=False)
        schedule_a.next_run_at = scheduled_at
        schedule_b.next_run_at = scheduled_at
        db.add(CrawlerTaskRun(
            company_id=company['companyId'], project_id=project['projectId'], task_id=task_b['taskId'], schedule_id=schedule_b.schedule_id,
            scheduled_at=scheduled_at, trigger_key=f"schedule:{schedule_b.schedule_id}:{scheduled_at.isoformat()}:single",
            run_status='SKIPPED', routing_status='ROUTE_CANCELLED', trigger_type='SCHEDULE',
            entry_module='spiders.dup_b', entry_function='run', execution_mode='SINGLE', idempotency_policy='IDEMPOTENT',
        ))
        db.commit()
        created = SchedulerService(db).dispatch_due_schedules(limit=10)
        assert created == 1
        created_a = db.query(CrawlerTaskRun).filter(CrawlerTaskRun.task_id == task_a['taskId'], CrawlerTaskRun.trigger_key.like(f"schedule:{schedule_a.schedule_id}:%:single")).count()
        assert created_a == 1
        db.refresh(schedule_a)
        db.refresh(schedule_b)
        assert schedule_a.next_run_at is not None and schedule_a.next_run_at > scheduled_at
        assert schedule_b.next_run_at is not None and schedule_b.next_run_at > scheduled_at


def test_task_schedule_panel_uses_sharded_parent_as_latest_run() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, _, discovery = create_flow(client, headers, 'panelshard')
    manifest = {**discovery['manifest'], 'releaseVersion': '1.1.0', 'imageDigest': 'sha256:' + ('1' * 64), 'taskDefinitions': [
        {'definitionKey': 'task_panel_shard', 'taskName': '面板分片任务', 'entryModule': 'spiders.panel_shard', 'entryFunction': 'run', 'executionMode': 'SHARDED', 'resourceRequirements': {'requiredNodeCount': 2, 'maxParallelNodes': 2}},
    ]}
    client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery['token']}, json={'companyId': company['companyId'], 'manifest': manifest})
    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    shard_def = [item for item in defs if item['definitionKey'] == 'task_panel_shard'][0]
    task = client.post('/api/v1/tasks', headers=headers, json={'definitionId': shard_def['definitionId'], 'taskCode': 'task_panel_shard', 'taskName': '面板分片任务', 'status': 'ENABLED'}).json()['data']
    parent = client.post('/api/v1/runs', headers=headers, json={'taskId': task['taskId']}).json()['data']
    from app.db import SessionLocal
    from app.models import CrawlerTaskRun
    from app.services.run_service import RunService
    from app.utils import utcnow
    with SessionLocal() as db:
        children = db.query(CrawlerTaskRun).filter(CrawlerTaskRun.parent_run_id == parent['runId']).order_by(CrawlerTaskRun.run_id.asc()).all()
        children[0].run_status = 'SUCCEEDED'
        children[0].finished_at = utcnow()
        children[1].run_status = 'FAILED'
        children[1].finished_at = utcnow()
        db.commit()
        RunService(db).aggregate_sharded_parent(parent['runId'])
        db.commit()
    response = client.get('/api/v1/task-schedule-panels', headers=headers, params={'taskCode': 'task_panel_shard'}).json()['data']
    assert response['total'] == 1
    item = response['items'][0]
    assert item['lastRunId'] == parent['runId']
    assert item['lastRunStatus'] == 'PARTIAL_SUCCESS'


def test_task_delete_physical_or_archive_and_panel_hides_archived() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, _, _ = create_flow(client, headers, 'taskdel')
    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    definition_id = defs[0]['definitionId']

    task = client.post('/api/v1/tasks', headers=headers, json={
        'definitionId': definition_id,
        'taskCode': 'task_delete_plain',
        'taskName': '待物理删除任务',
        'status': 'ENABLED',
    }).json()['data']
    deleted = client.delete(f"/api/v1/tasks/{task['taskId']}", headers=headers).json()['data']
    assert deleted['deleted'] is True
    assert deleted['archived'] is False

    defs_after_delete = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    assert defs_after_delete[0]['definitionStatus'] == 'AVAILABLE'

    task_with_run = client.post('/api/v1/tasks', headers=headers, json={
        'definitionId': definition_id,
        'taskCode': 'task_delete_archive',
        'taskName': '待归档删除任务',
        'status': 'ENABLED',
    }).json()['data']
    run = client.post('/api/v1/runs', headers=headers, json={'taskId': task_with_run['taskId']}).json()['data']

    from app.db import SessionLocal
    from app.models import CrawlerTaskRun
    from app.utils import utcnow
    with SessionLocal() as db:
        run_row = db.get(CrawlerTaskRun, run['runId'])
        run_row.run_status = 'SUCCEEDED'
        run_row.routing_status = 'ROUTED'
        run_row.finished_at = utcnow()
        db.commit()

    archived = client.delete(f"/api/v1/tasks/{task_with_run['taskId']}", headers=headers).json()['data']
    assert archived['deleted'] is False
    assert archived['archived'] is True
    assert archived['runCount'] == 1

    default_panel = client.get('/api/v1/task-schedule-panels', headers=headers, params={'projectId': project['projectId']}).json()['data']
    assert task_with_run['taskId'] not in {item['taskId'] for item in default_panel['items']}

    archived_panel = client.get('/api/v1/task-schedule-panels', headers=headers, params={'projectId': project['projectId'], 'taskStatus': 'ARCHIVED'}).json()['data']
    assert task_with_run['taskId'] in {item['taskId'] for item in archived_panel['items']}


def test_cicd_release_registration_without_server_and_multi_agent_pool() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'hc_cicd_multi', 'companyName': 'H公司多节点CI'}).json()['data']
    server_a = client.post('/api/v1/servers', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'srv-cicd-a', 'serverName': 'CI A服务器'}).json()['data']
    server_b = client.post('/api/v1/servers', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'srv-cicd-b', 'serverName': 'CI B服务器'}).json()['data']
    agent_a = client.post('/api/v1/agents', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'srv-cicd-a', 'serverName': 'CI A服务器', 'agentCode': 'agent-cicd-a', 'agentName': 'CI A Agent'}).json()['data']
    agent_b = client.post('/api/v1/agents', headers=headers, json={'companyId': company['companyId'], 'serverCode': 'srv-cicd-b', 'serverName': 'CI B服务器', 'agentCode': 'agent-cicd-b', 'agentName': 'CI B Agent'}).json()['data']
    token = client.post(f"/api/v1/companies/{company['companyId']}/discovery-tokens", headers=headers).json()['data']['discoveryToken']
    manifest = {
        'manifestVersion': '1',
        'projectKey': 'crawler_platform_spiders_cicd_multi',
        'projectName': '通用爬虫项目基建CI多节点',
        'projectCode': 'crawler_spiders_cicd_multi',
        'repositoryUrl': 'git@example/crawler-platform-spiders',
        'imageRepository': 'registry.example.com/crawler_platform_spiders',
        'imageDigest': 'sha256:' + ('2' * 64),
        'releaseVersion': '1.0.6',
        'releaseChannel': 'stable',
        'taskDefinitions': [{'definitionKey': 'oilchem_login_check', 'taskName': 'Oilchem登录校验', 'entryModule': 'spiders.oilchem.login', 'entryFunction': 'run'}],
    }
    discovered = client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + token}, json={'companyId': company['companyId'], 'manifest': manifest}).json()['data']
    assert discovered['latestImageDigest'] == manifest['imageDigest']
    project = client.post('/api/v1/projects', headers=headers, json={'discoveredProjectId': discovered['discoveredProjectId'], 'dispatchMode': 'LOAD_BALANCE'}).json()['data']
    assert client.get(f"/api/v1/projects/{project['projectId']}/servers", headers=headers).json()['data'] == []

    analysis = client.post(f"/api/v1/projects/{project['projectId']}/server-pool-analyses", headers=headers, json={'servers': [
        {'serverId': server_a['serverId'], 'schedulingStatus': 'ENABLED', 'serverRole': 'ACTIVE', 'priority': 10, 'weight': 100, 'maxConcurrency': 2},
        {'serverId': server_b['serverId'], 'schedulingStatus': 'ENABLED', 'serverRole': 'ACTIVE', 'priority': 20, 'weight': 100, 'maxConcurrency': 2},
    ]}).json()['data']
    assert analysis['canSave'] is True
    assert all(item['willCreateDeployment'] is True for item in analysis['details'])

    pool = client.put(f"/api/v1/projects/{project['projectId']}/servers", headers=headers, json={'servers': [
        {'serverId': server_a['serverId'], 'schedulingStatus': 'ENABLED', 'serverRole': 'ACTIVE', 'priority': 10, 'weight': 100, 'maxConcurrency': 2},
        {'serverId': server_b['serverId'], 'schedulingStatus': 'ENABLED', 'serverRole': 'ACTIVE', 'priority': 20, 'weight': 100, 'maxConcurrency': 2},
    ]}).json()['data']
    assert {item['serverId'] for item in pool} == {server_a['serverId'], server_b['serverId']}
    assert {item['latestImageDigest'] for item in pool} == {manifest['imageDigest']}
    assert {item['imageReadinessStatus'] for item in pool} == {'OUTDATED'}

    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    task = client.post('/api/v1/tasks', headers=headers, json={'definitionId': defs[0]['definitionId'], 'taskCode': 'oilchem_login_check_cicd', 'taskName': 'Oilchem登录校验CI', 'status': 'ENABLED'}).json()['data']
    run = client.post('/api/v1/runs', headers=headers, json={'taskId': task['taskId'], 'parameters': {'account': {'username': 'demo', 'cookieString': '_member_user_tonken_=dummy'}}}).json()['data']
    assert run['imageDigest'] == manifest['imageDigest']

    for agent in (agent_a, agent_b):
        client.post('/api/v1/agent-heartbeats', headers={'Authorization': 'Agent ' + agent['agentToken']}, json={'agentInstanceId': 'inst-' + agent['agent']['agentCode'], 'dockerStatus': 'OK', 'availableSlots': 2})
    claim_a = client.post('/api/v1/agent-run-claims', headers={'Authorization': 'Agent ' + agent_a['agentToken']}).json()['data']
    claim_b = client.post('/api/v1/agent-run-claims', headers={'Authorization': 'Agent ' + agent_b['agentToken']}).json()['data']
    claim = claim_a or claim_b
    assert claim['runId'] == run['runId']
    assert claim['companyId'] == company['companyId']
    assert claim['releaseId'] == run['releaseId']
    assert claim['imageRepository'] == manifest['imageRepository']
    assert claim['imageDigest'] == manifest['imageDigest']


def test_cicd_release_registration_marks_existing_pool_outdated() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, _, discovery = create_flow(client, headers, 'cicdout', ['srv-cicdout-a'])
    pool = client.get(f"/api/v1/projects/{project['projectId']}/servers", headers=headers).json()['data']
    assert pool[0]['latestImageDigest'] == discovery['manifest']['imageDigest']
    manifest = {**discovery['manifest'], 'releaseVersion': '1.0.6', 'imageDigest': 'sha256:' + ('3' * 64)}
    client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery['token']}, json={'companyId': company['companyId'], 'manifest': manifest})
    updated_pool = client.get(f"/api/v1/projects/{project['projectId']}/servers", headers=headers).json()['data']
    assert updated_pool[0]['latestImageDigest'] == manifest['imageDigest']
    assert updated_pool[0]['imageReadinessStatus'] == 'OUTDATED'
    releases = client.get('/api/v1/releases', headers=headers, params={'projectId': project['projectId']}).json()['data']
    assert releases[0]['imageDigest'] == manifest['imageDigest']


def test_agent_heartbeat_advertises_image_updates_and_pull_result_updates_readiness() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, agents, discovery = create_flow(client, headers, 'imgupd', ['srv-imgupd-a'])
    agent_headers = agents[0]['headers']
    pool = client.get(f"/api/v1/projects/{project['projectId']}/servers", headers=headers).json()['data']
    assert pool[0]['imageReadinessStatus'] == 'OUTDATED'

    heartbeat = client.post('/api/v1/agent-heartbeats', headers=agent_headers, json={'agentInstanceId': 'inst-imgupd-a', 'dockerStatus': 'OK', 'availableSlots': 2, 'runningContainers': 0, 'currentRuns': {'runIds': []}}).json()['data']
    pending = [item for item in heartbeat['pendingImagePulls'] if item['projectId'] == project['projectId']]
    assert len(pending) == 1
    assert pending[0]['safeToPrewarm'] is True
    assert pending[0]['action'] == 'PREWARM_NOW'
    assert pending[0]['imageDigest'] == discovery['manifest']['imageDigest']

    failed = client.post('/api/v1/agent-image-pull-results', headers=agent_headers, json={'projectId': project['projectId'], 'releaseId': pending[0]['releaseId'], 'imageRepository': pending[0]['imageRepository'], 'imageDigest': pending[0]['imageDigest'], 'pullStatus': 'FAILED', 'message': 'registry timeout'}).json()['data']
    assert failed['imageReadinessStatus'] == 'FAILED'
    failed_pool = client.get(f"/api/v1/projects/{project['projectId']}/servers", headers=headers).json()['data']
    assert failed_pool[0]['imageReadinessStatus'] == 'FAILED'
    assert 'registry timeout' in failed_pool[0]['disabledReason']

    ready = client.post('/api/v1/agent-image-pull-results', headers=agent_headers, json={'projectId': project['projectId'], 'releaseId': pending[0]['releaseId'], 'imageRepository': pending[0]['imageRepository'], 'imageDigest': pending[0]['imageDigest'], 'pullStatus': 'READY', 'message': 'ok'}).json()['data']
    assert ready['imageReadinessStatus'] == 'READY'
    ready_pool = client.get(f"/api/v1/projects/{project['projectId']}/servers", headers=headers).json()['data']
    assert ready_pool[0]['imageReadinessStatus'] == 'READY'

    heartbeat_after = client.post('/api/v1/agent-heartbeats', headers=agent_headers, json={'agentInstanceId': 'inst-imgupd-a', 'dockerStatus': 'OK', 'availableSlots': 2, 'runningContainers': 0, 'currentRuns': {'runIds': []}}).json()['data']
    assert not [item for item in heartbeat_after['pendingImagePulls'] if item['projectId'] == project['projectId']]


def test_new_release_does_not_interrupt_running_run_and_waits_idle_prewarm() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, agents, discovery = create_flow(client, headers, 'nointerrupt', ['srv-nointerrupt-a'])
    agent_headers = agents[0]['headers']
    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    task = client.post('/api/v1/tasks', headers=headers, json={'definitionId': defs[0]['definitionId'], 'taskCode': 'task_nointerrupt', 'taskName': '不中断任务', 'status': 'ENABLED'}).json()['data']
    run = client.post('/api/v1/runs', headers=headers, json={'taskId': task['taskId'], 'parameters': {}}).json()['data']

    client.post('/api/v1/agent-heartbeats', headers=agent_headers, json={'agentInstanceId': 'inst-nointerrupt-a', 'dockerStatus': 'OK', 'availableSlots': 1, 'runningContainers': 0, 'currentRuns': {'runIds': []}})
    claim = client.post('/api/v1/agent-run-claims', headers=agent_headers, json={'agentInstanceId': 'inst-nointerrupt-a'}).json()['data']
    assert claim['runId'] == run['runId']
    client.post('/api/v1/agent-run-heartbeats', headers=agent_headers, json={'runId': run['runId'], 'leaseToken': claim['leaseToken'], 'message': 'starting', 'agentInstanceId': 'inst-nointerrupt-a'})
    client.post('/api/v1/agent-run-heartbeats', headers=agent_headers, json={'runId': run['runId'], 'leaseToken': claim['leaseToken'], 'message': 'running', 'agentInstanceId': 'inst-nointerrupt-a'})

    manifest = {**discovery['manifest'], 'releaseVersion': '1.0.19', 'imageDigest': 'sha256:' + ('4' * 64)}
    client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery['token']}, json={'companyId': company['companyId'], 'manifest': manifest})
    pool = client.get(f"/api/v1/projects/{project['projectId']}/servers", headers=headers).json()['data']
    assert pool[0]['latestImageDigest'] == manifest['imageDigest']
    assert pool[0]['imageReadinessStatus'] == 'OUTDATED'

    heartbeat = client.post('/api/v1/agent-heartbeats', headers=agent_headers, json={'agentInstanceId': 'inst-nointerrupt-a', 'dockerStatus': 'OK', 'availableSlots': 0, 'runningContainers': 1, 'currentRuns': {'runIds': [run['runId']]}}).json()['data']
    pending = [item for item in heartbeat['pendingImagePulls'] if item['projectId'] == project['projectId']]
    assert len(pending) == 1
    assert pending[0]['safeToPrewarm'] is False
    assert pending[0]['action'] == 'PREWARM_WHEN_IDLE'
    assert pending[0]['imageDigest'] == manifest['imageDigest']

    from app.db import SessionLocal
    from app.models import CrawlerTaskRun
    with SessionLocal() as db:
        running = db.get(CrawlerTaskRun, run['runId'])
        assert running.run_status == 'RUNNING'
        assert running.image_digest == discovery['manifest']['imageDigest']


def test_cicd_release_version_is_immutable_and_semver_only() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, _, discovery = create_flow(client, headers, 'immutable')

    conflict = {**discovery['manifest'], 'imageDigest': 'sha256:' + ('9' * 64)}
    response = client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery['token']}, json={'companyId': company['companyId'], 'manifest': conflict})
    assert response.status_code == 409
    body = response.json()
    assert body['code'] == 40046
    assert '不可变' in body['message']

    floating = {**discovery['manifest'], 'releaseVersion': 'main', 'imageDigest': 'sha256:' + ('8' * 64)}
    bad = client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery['token']}, json={'companyId': company['companyId'], 'manifest': floating})
    assert bad.status_code == 400
    assert bad.json()['code'] == 40045


def test_agent_restart_keeps_detected_running_container_alive() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, agents, discovery = create_flow(client, headers, 'restartkeep', ['srv-restartkeep-a'])
    agent_headers = agents[0]['headers']
    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    task = client.post('/api/v1/tasks', headers=headers, json={'definitionId': defs[0]['definitionId'], 'taskCode': 'task_restart_keep', 'taskName': 'Agent重启保持任务', 'status': 'ENABLED'}).json()['data']
    run = client.post('/api/v1/runs', headers=headers, json={'taskId': task['taskId']}).json()['data']

    client.post('/api/v1/agent-heartbeats', headers=agent_headers, json={'agentInstanceId': 'agent-old', 'dockerStatus': 'OK', 'availableSlots': 1, 'runningContainers': 0, 'currentRuns': {'runIds': []}})
    claim = client.post('/api/v1/agent-run-claims', headers=agent_headers, json={'agentInstanceId': 'agent-old'}).json()['data']
    client.post('/api/v1/agent-run-heartbeats', headers=agent_headers, json={'runId': run['runId'], 'leaseToken': claim['leaseToken'], 'message': 'running', 'agentInstanceId': 'agent-old'})
    client.post('/api/v1/agent-run-heartbeats', headers=agent_headers, json={'runId': run['runId'], 'leaseToken': claim['leaseToken'], 'message': 'running', 'agentInstanceId': 'agent-old'})

    heartbeat = client.post('/api/v1/agent-heartbeats', headers=agent_headers, json={
        'agentInstanceId': 'agent-new',
        'dockerStatus': 'OK',
        'availableSlots': 0,
        'runningContainers': 1,
        'currentRuns': {'runIds': [run['runId']], 'dockerRunIds': [run['runId']], 'orphanRunIds': [run['runId']]},
    }).json()['data']
    assert heartbeat['replacedPreviousInstance'] is True
    from app.db import SessionLocal
    from app.models import CrawlerTaskRun
    with SessionLocal() as db:
        row = db.get(CrawlerTaskRun, run['runId'])
        assert row.run_status == 'RUNNING'
        assert row.finished_at is None
        assert row.lease_expires_at is not None


def test_agent_join_token_bootstrap_and_install_script() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'joinco', 'companyName': '接入公司'}).json()['data']
    token_body = client.post('/api/v1/servers/agent-join-tokens', headers=headers, json={
        'companyId': company['companyId'],
        'serverCode': 'join-srv-01',
        'serverName': '接入服务器01',
        'agentCode': 'join-agent-01',
        'agentName': '接入Agent01',
        'maxContainerSlots': 3,
        'workDir': '/tmp/crawler-agent-join',
        'labels': {'region': 'cn', 'browser': 'false'},
        'capabilities': {'docker': True, 'browser': False},
    }).json()['data']
    assert token_body['joinToken']
    assert '--join-token' in token_body['installCommand']
    assert token_body['controlPlaneUrl'].startswith(('http://', 'https://'))
    assert 'connectivityCommand' in token_body
    bad_remote = client.post('/api/v1/servers/agent-join-tokens', headers=headers, json={
        'companyId': company['companyId'],
        'serverCode': 'join-srv-loopback',
        'serverName': '远程服务器',
        'agentCode': 'join-agent-loopback',
        'controlPlaneUrl': 'http://127.0.0.1:8080',
        'installTarget': 'REMOTE',
    })
    assert bad_remote.status_code == 400
    local_token = client.post('/api/v1/servers/agent-join-tokens', headers=headers, json={
        'companyId': company['companyId'],
        'serverCode': 'join-srv-local',
        'serverName': '本机测试服务器',
        'agentCode': 'join-agent-local',
        'controlPlaneUrl': 'http://127.0.0.1:8080',
        'installTarget': 'LOCAL',
    }).json()['data']
    assert '127.0.0.1:8080' in local_token['installCommand']
    script = client.get('/api/v1/agent-installers/linux.sh')
    assert script.status_code == 200
    assert '控制端连通' in script.text and 'Docker' in script.text
    env_resp = client.post('/api/v1/agent-bootstrap/env', json={'joinToken': token_body['joinToken'], 'hostname': 'test-host', 'installReport': {'pass': 5}})
    assert env_resp.status_code == 200
    assert 'AGENT_AGENT_TOKEN=' in env_resp.text
    assert "AGENT_AGENT_CODE='join-agent-01'" in env_resp.text
    servers = client.get('/api/v1/servers', headers=headers, params={'companyId': company['companyId']}).json()['data']
    server = next(row for row in servers if row['serverCode'] == 'join-srv-01')
    assert server['labels']['region'] == 'cn'
    assert server['capabilities']['docker'] is True
    second = client.post('/api/v1/agent-bootstrap/env', json={'joinToken': token_body['joinToken'], 'hostname': 'test-host'})
    assert second.status_code == 401


def test_project_release_deployment_to_multiple_agents() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, agents, discovery = create_flow(client, headers, 'deploymulti', server_codes=['srv-dep-a', 'srv-dep-b'])
    deployment = client.post(f"/api/v1/projects/{project['projectId']}/release-deployments", headers=headers, json={
        'serverIds': [],
    })
    assert deployment.status_code == 400
    for idx, agent in enumerate(agents):
        client.post('/api/v1/agent-heartbeats', headers=agent['headers'], json={
            'agentInstanceId': f'inst-deploy-precheck-{idx}',
            'dockerStatus': 'OK',
            'availableSlots': 2,
            'runningContainers': 0,
            'currentRuns': {'runIds': []},
        })
    servers = client.get('/api/v1/servers', headers=headers, params={'companyId': company['companyId']}).json()['data']
    server_ids = [row['serverId'] for row in servers if row['serverCode'] in {'srv-dep-a', 'srv-dep-b'}]
    deployment = client.post(f"/api/v1/projects/{project['projectId']}/release-deployments", headers=headers, json={'serverIds': server_ids, 'reason': '部署到两台服务器'}).json()['data']
    assert deployment['releaseVersion'] == '1.0.1'
    assert deployment['deploymentStatus'] == 'DEPLOYING'
    assert len(deployment['targets']) == 2
    assert {target['commandId'] for target in deployment['targets']}
    pool = client.get(f"/api/v1/projects/{project['projectId']}/servers", headers=headers).json()['data']
    assert {item['serverId'] for item in pool} >= set(server_ids)
    for item in pool:
        if item['serverId'] in server_ids:
            assert item['latestImageDigest'] == discovery['manifest']['imageDigest']
            assert item['deploymentStatus'] == 'DEPLOYING'
            assert item['imageReadinessStatus'] == 'DEPLOYING'
            assert item['schedulingStatus'] == 'PAUSED'
    history = client.get(f"/api/v1/projects/{project['projectId']}/release-deployments", headers=headers).json()['data']
    assert history and history[0]['deploymentStatus'] == 'DEPLOYING'
    assert history[0]['strategy']['steps'][-1]['key'] == 'AGENT_DEPLOY_PREPARE'

    heartbeat = client.post('/api/v1/agent-heartbeats', headers=agents[0]['headers'], json={
        'agentInstanceId': 'inst-deploy-a',
        'dockerStatus': 'OK',
        'availableSlots': 2,
        'runningContainers': 0,
        'currentRuns': {'runIds': []},
    }).json()['data']
    pending = [item for item in heartbeat['pendingAgentCommands'] if item['projectId'] == project['projectId']]
    assert len(pending) == 1
    assert pending[0]['commandType'] == 'PROJECT_DEPLOY_PREPARE'
    assert heartbeat['pendingImagePulls'] == []

    ack = client.post('/api/v1/agent-command-results', headers=agents[0]['headers'], json={
        'commandId': pending[0]['commandId'],
        'commandType': 'PROJECT_DEPLOY_PREPARE',
        'projectId': project['projectId'],
        'releaseId': pending[0]['releaseId'],
        'deploymentId': pending[0]['deploymentId'],
        'targetId': pending[0]['targetId'],
        'success': True,
        'message': 'ok',
        'result': {'imageRef': discovery['manifest']['imageRepository'] + '@' + discovery['manifest']['imageDigest']},
    }).json()['data']
    assert ack['accepted'] is True
    pool_after_ack = client.get(f"/api/v1/projects/{project['projectId']}/servers", headers=headers).json()['data']
    deployed = [item for item in pool_after_ack if item['serverId'] == pending[0]['serverId']][0]
    assert deployed['deploymentStatus'] == 'DEPLOYED'
    assert deployed['imageReadinessStatus'] == 'READY'
    assert deployed['schedulingStatus'] == 'ENABLED'



def test_delete_task_enqueues_agent_container_cleanup_and_ack_clears_queue() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, agents, _ = create_flow(client, headers, 'clean_task', ['srv-clean-task'])
    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    task = client.post('/api/v1/tasks', headers=headers, json={
        'definitionId': defs[0]['definitionId'],
        'taskCode': 'clean_task_one',
        'taskName': '待清理容器任务',
        'status': 'ENABLED',
    }).json()['data']

    deleted = client.delete(f"/api/v1/tasks/{task['taskId']}", headers=headers).json()['data']
    assert deleted['deleted'] is True
    assert deleted['containerCleanupCommands']

    heartbeat = client.post('/api/v1/agent-heartbeats', headers=agents[0]['headers'], json={
        'agentInstanceId': 'inst-clean-task',
        'dockerStatus': 'OK',
        'availableSlots': 2,
        'runningContainers': 0,
        'currentRuns': {'runIds': []},
    }).json()['data']
    pending = [item for item in heartbeat['pendingContainerCleanups'] if item['taskId'] == task['taskId']]
    assert len(pending) == 1
    assert pending[0]['cleanupScope'] == 'TASK'
    assert pending[0]['projectId'] == project['projectId']

    ack = client.post('/api/v1/agent-container-cleanup-results', headers=agents[0]['headers'], json={
        'cleanupId': pending[0]['cleanupId'],
        'cleanupScope': 'TASK',
        'projectId': project['projectId'],
        'taskId': task['taskId'],
        'success': True,
        'stoppedCount': 0,
        'removedCount': 0,
        'failedCount': 0,
        'message': 'ok',
    }).json()['data']
    assert ack['accepted'] is True

    heartbeat_after_ack = client.post('/api/v1/agent-heartbeats', headers=agents[0]['headers'], json={
        'agentInstanceId': 'inst-clean-task',
        'dockerStatus': 'OK',
        'availableSlots': 2,
        'runningContainers': 0,
        'currentRuns': {'runIds': []},
    }).json()['data']
    assert not [item for item in heartbeat_after_ack['pendingContainerCleanups'] if item.get('cleanupId') == pending[0]['cleanupId']]


def test_delete_project_cleans_project_servers_and_archives_when_runs_exist() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, agents, _ = create_flow(client, headers, 'clean_project', ['srv-clean-project'])
    defs = client.get(f"/api/v1/projects/{project['projectId']}/task-definitions", headers=headers).json()['data']
    task = client.post('/api/v1/tasks', headers=headers, json={
        'definitionId': defs[0]['definitionId'],
        'taskCode': 'clean_project_task',
        'taskName': '项目清理任务',
        'status': 'ENABLED',
    }).json()['data']
    run = client.post('/api/v1/runs', headers=headers, json={'taskId': task['taskId']}).json()['data']

    from app.db import SessionLocal
    from app.models import CrawlerTaskRun
    from app.utils import utcnow
    with SessionLocal() as db:
        run_row = db.get(CrawlerTaskRun, run['runId'])
        run_row.run_status = 'SUCCEEDED'
        run_row.routing_status = 'ROUTED'
        run_row.finished_at = utcnow()
        db.commit()

    archived = client.delete(f"/api/v1/projects/{project['projectId']}", headers=headers).json()['data']
    assert archived['deleted'] is False
    assert archived['archived'] is True
    assert archived['runCount'] == 1
    assert archived['containerCleanupCommands']

    projects_after_delete = client.get('/api/v1/projects', headers=headers, params={'companyId': company['companyId']}).json()['data']
    assert project['projectId'] not in {item['projectId'] for item in projects_after_delete}

    heartbeat = client.post('/api/v1/agent-heartbeats', headers=agents[0]['headers'], json={
        'agentInstanceId': 'inst-clean-project',
        'dockerStatus': 'OK',
        'availableSlots': 2,
        'runningContainers': 0,
        'currentRuns': {'runIds': []},
    }).json()['data']
    pending = [item for item in heartbeat['pendingContainerCleanups'] if item['projectId'] == project['projectId']]
    assert len(pending) == 1
    assert pending[0]['cleanupScope'] == 'PROJECT'
    assert pending[0]['taskId'] is None


def test_company_page_can_generate_one_time_discovery_secret() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company = client.post('/api/v1/companies', headers=headers, json={'companyCode': 'secretco', 'companyName': '密钥公司'}).json()['data']
    generated = client.post(f"/api/v1/companies/{company['companyId']}/discovery-tokens", headers=headers).json()['data']
    assert generated['tokenId'] > 0
    assert generated['discoveryToken']

    repo_root = Path(__file__).resolve().parents[2]
    page = (repo_root / 'frontend/src/views/CompaniesPage.vue').read_text(encoding='utf-8')
    assert 'generateSecret' in page
    assert 'createDiscoveryToken' in page
    assert '生成接入密钥' in page
    assert '只显示这一次' in page
    assert 'CRAWLER_DISCOVERY_TOKEN' in page
    assert 'CRAWLER_PLATFORM_DISCOVERY_TOKEN' not in page
