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
    discovered = client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery_token}, json={'companyId': company['companyId'], 'serverCode': 'srv-b', 'manifest': manifest}).json()['data']
    assert discovered['discoveryStatus'] == 'READY_TO_IMPORT'

    project = client.post('/api/v1/projects', headers=headers, json={'discoveredProjectId': discovered['discoveredProjectId']}).json()['data']
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
    for code in server_codes:
        client.post('/api/v1/servers', headers=headers, json={'companyId': company['companyId'], 'serverCode': code, 'serverName': f'{code}服务器'}).json()['data']
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
        discovered = client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery_token}, json={'companyId': company['companyId'], 'serverCode': code, 'manifest': manifest}).json()['data']
    project = client.post('/api/v1/projects', headers=headers, json={'discoveredProjectId': discovered['discoveredProjectId'], 'dispatchMode': 'LOAD_BALANCE'}).json()['data']
    return company, project, agent_tokens, {'token': discovery_token, 'manifest': manifest}


def test_permissions_release_and_dashboard_scope() -> None:
    migrate()
    client = TestClient(app)
    _, admin_headers = login(client)
    company, project, _, _ = create_flow(client, admin_headers, 'perm')
    user = client.post('/api/v1/users', headers=admin_headers, json={'companyId': company['companyId'], 'userName': 'normal_perm', 'nickName': '普通用户', 'password': 'Normal@123456', 'roleType': 'NORMAL_USER'}).json()['data']
    normal_login = client.post('/api/v1/sessions', json={'userName': 'normal_perm', 'password': 'Normal@123456'}).json()['data']
    normal_headers = {'Authorization': 'Bearer ' + normal_login['accessToken']}
    assert client.get('/api/v1/dashboard-summaries', headers=normal_headers).status_code == 403
    assert client.get('/api/v1/releases', headers=normal_headers).json()['data'] == []


def test_formal_project_release_sync_after_cicd_report() -> None:
    migrate()
    client = TestClient(app)
    _, headers = login(client)
    company, project, _, discovery = create_flow(client, headers, 'sync')
    manifest = {**discovery['manifest'], 'releaseVersion': '1.1.0', 'imageDigest': 'sha256:' + ('c' * 64), 'taskDefinitions': [
        {'definitionKey': 'task_one', 'taskName': '任务一新版', 'entryModule': 'spiders.task_one', 'entryFunction': 'run'},
        {'definitionKey': 'task_two', 'taskName': '任务二', 'entryModule': 'spiders.task_two', 'entryFunction': 'run'},
    ]}
    client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery['token']}, json={'companyId': company['companyId'], 'serverCode': 'srv-sync', 'manifest': manifest})
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
    client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery['token']}, json={'companyId': company['companyId'], 'serverCode': 'srv-shard', 'manifest': manifest})
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
    client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery['token']}, json={'companyId': company['companyId'], 'serverCode': 'srv-schedshard', 'manifest': manifest})
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
    client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery['token']}, json={'companyId': company['companyId'], 'serverCode': 'srv-sharedenv', 'manifest': manifest})
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
    client.post('/api/v1/discovered-projects', headers={'Authorization': 'Discovery ' + discovery['token']}, json={'companyId': company['companyId'], 'serverCode': 'srv-lock', 'manifest': manifest})
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
    reset = client.post(f"/api/v1/users/{user['userId']}/password-resets", headers=admin_headers, json={'newPassword': 'Reset@987654', 'mustChangePassword': True}).json()['data']
    assert reset['mustChangePassword'] is True


def test_102_frontend_run_log_routes_match_backend_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    api_source = (root / 'frontend' / 'src' / 'api' / 'platform.ts').read_text(encoding='utf-8')
    assert '/log-tails' in api_source
    assert '/diagnoses' in api_source
    assert '/logs/tail' not in api_source
    assert '/diagnosis`' not in api_source
