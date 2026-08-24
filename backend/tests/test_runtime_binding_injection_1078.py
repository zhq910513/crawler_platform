from __future__ import annotations

import os
from pathlib import Path

Path('/tmp/crawler_platform_runtime_binding_1078.db').unlink(missing_ok=True)
os.environ['APP_ENV'] = 'test'
os.environ['DATABASE_URL'] = 'sqlite+pysqlite:////tmp/crawler_platform_runtime_binding_1078.db'
os.environ['REDIS_URL'] = 'redis://localhost:6379/15'
os.environ['JWT_SECRET'] = 'pytest-jwt-secret-for-crawler-platform-1-0-78'
os.environ['SECRET_ENCRYPTION_KEY'] = 'pytest-secret-encryption-key-for-crawler-platform-1-0-78'
os.environ['ADMIN_USERNAME'] = 'admin'
os.environ['ADMIN_PASSWORD'] = 'Admin@123456'

from app.db import SessionLocal
from app.migration_main import main as migrate
from app.models import (
    CrawlerAgent,
    CrawlerCompany,
    CrawlerProject,
    CrawlerProjectRelease,
    CrawlerProjectServer,
    CrawlerReleaseChannel,
    CrawlerServer,
    CrawlerTask,
)
from app.schemas import AgentRunClaim
from app.services.agent_service import AgentService
from app.services.run_service import RunService, build_runtime_parameters
from app.utils import utcnow


def test_build_runtime_parameters_injects_task_bindings_as_runtime_contract() -> None:
    task = CrawlerTask(
        company_id=1,
        project_id=2,
        task_code='contract_task',
        task_name='契约任务',
        entry_module='spiders.demo.task',
        entry_function='run',
        parameters={'businessFlag': True, 'accounts': {'bad': 'override_attempt'}},
        config_bindings={'mysql_main': 'config:mysql_main'},
        credential_bindings={'login': {'mode': 'fixed', 'platformCode': 'demo', 'credentialKey': 'demo_account'}},
        status='ENABLED',
    )

    payload = build_runtime_parameters(task, {'page': 1, 'configBindings': {'bad': 'override_attempt'}})

    assert payload['businessFlag'] is True
    assert payload['page'] == 1
    assert payload['configBindings'] == {'mysql_main': 'config:mysql_main'}
    assert payload['config_bindings'] == {'mysql_main': 'config:mysql_main'}
    assert payload['credentialBindings'] == {'login': {'mode': 'fixed', 'platformCode': 'demo', 'credentialKey': 'demo_account'}}
    assert payload['accounts'] == {'login': {'mode': 'fixed', 'platformCode': 'demo', 'credentialKey': 'demo_account'}}


def test_run_snapshot_and_agent_claim_deliver_config_and_account_slots() -> None:
    migrate()
    now = utcnow()
    with SessionLocal() as db:
        company = CrawlerCompany(company_code='runtime78', company_name='运行契约公司', status='ENABLED')
        db.add(company)
        db.flush()
        project = CrawlerProject(
            company_id=company.company_id,
            project_code='runtime_project',
            project_name='运行契约项目',
            project_key='runtime_project',
            image_repository='registry/runtime-project',
            status='ENABLED',
            online_status='READY',
        )
        db.add(project)
        db.flush()
        release = CrawlerProjectRelease(
            company_id=company.company_id,
            project_id=project.project_id,
            version='1.0.78',
            release_channel='stable',
            image_repository='registry/runtime-project',
            image_digest='sha256:' + ('a' * 64),
            release_status='PUBLISHED',
            parse_status='SUCCESS',
        )
        db.add(release)
        db.flush()
        channel = CrawlerReleaseChannel(company_id=company.company_id, project_id=project.project_id, channel_name='stable', release_id=release.release_id, channel_status='ENABLED')
        server = CrawlerServer(
            company_id=company.company_id,
            server_code='runtime-node',
            server_name='运行契约节点',
            server_ip='127.0.0.1',
            manage_status='ENABLED',
            desired_state='ONLINE',
            lifecycle_status='IDLE',
            health_status='HEALTHY',
            capacity_status='NORMAL',
            max_container_slots=2,
        )
        db.add_all([channel, server])
        db.flush()
        agent = CrawlerAgent(
            company_id=company.company_id,
            server_id=server.server_id,
            agent_code='runtime-agent',
            agent_name='运行契约 Agent',
            token_hash='runtime-token-hash',
            agent_version='1.0.78',
            protocol_version='1.0',
            agent_instance_id='instance-runtime-78',
            connection_status='ONLINE',
        )
        project_server = CrawlerProjectServer(
            company_id=company.company_id,
            project_id=project.project_id,
            server_id=server.server_id,
            deployment_status='DEPLOYED',
            scheduling_status='ENABLED',
            image_readiness_status='READY',
            server_role='ACTIVE',
            latest_release_id=release.release_id,
            latest_image_digest=release.image_digest,
        )
        task = CrawlerTask(
            company_id=company.company_id,
            project_id=project.project_id,
            task_code='runtime_task',
            task_name='运行契约任务',
            entry_module='spiders.demo.runtime_task',
            entry_function='run',
            parameters={'baseParam': 'task-default'},
            config_bindings={'mysql_main': 'config:mysql_main'},
            credential_bindings={'login': {'mode': 'fixed', 'platformCode': 'demo', 'credentialKey': 'demo_account'}},
            status='ENABLED',
            release_channel='stable',
        )
        db.add_all([agent, project_server, task])
        db.flush()

        run = RunService(db).create_run(task, None, now, {'manualParam': 'manual'}, trigger_type='MANUAL')
        assert run.routing_status == 'ROUTED'
        assert run.parameters_snapshot['configBindings']['mysql_main'] == 'config:mysql_main'
        assert run.parameters_snapshot['accounts']['login']['credentialKey'] == 'demo_account'
        db.commit()

        claim = AgentService(db).claim_run(agent, AgentRunClaim(agent_instance_id='instance-runtime-78'))
        assert claim is not None
        assert claim['parameters']['baseParam'] == 'task-default'
        assert claim['parameters']['manualParam'] == 'manual'
        assert claim['parameters']['configBindings'] == {'mysql_main': 'config:mysql_main'}
        assert claim['parameters']['accounts']['login']['credentialKey'] == 'demo_account'
        assert claim['configBindings'] == {'mysql_main': 'config:mysql_main'}
        assert claim['accounts']['login']['platformCode'] == 'demo'
