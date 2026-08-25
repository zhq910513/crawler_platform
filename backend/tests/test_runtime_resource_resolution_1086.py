from __future__ import annotations

import json
import os
from pathlib import Path

Path('/tmp/crawler_platform_runtime_resource_1086.db').unlink(missing_ok=True)
os.environ['APP_ENV'] = 'test'
os.environ['DATABASE_URL'] = 'sqlite+pysqlite:////tmp/crawler_platform_runtime_resource_1086.db'
os.environ['REDIS_URL'] = 'redis://localhost:6379/15'
os.environ['JWT_SECRET'] = 'pytest-jwt-secret-for-crawler-platform-1-0-86'
os.environ['SECRET_ENCRYPTION_KEY'] = 'pytest-secret-encryption-key-for-crawler-platform-1-0-86'
os.environ['ADMIN_USERNAME'] = 'admin'
os.environ['ADMIN_PASSWORD'] = 'Admin@123456'

from app.db import SessionLocal
from app.errors import AppError
from app.migration_main import main as migrate
from app.models import (
    CompanyResourceConfig,
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
from app.security import encrypt_secret
from app.services.agent_service import AgentService
from app.services.run_service import RunService
from app.services.runtime_resource_service import RuntimeResourceResolver
from app.utils import utcnow


def _encrypted_config(data: dict) -> str:
    return encrypt_secret(json.dumps({'config': data}, ensure_ascii=False))


def _base_graph(db, suffix: str):
    company = CrawlerCompany(company_code=f'runtime86_{suffix}', company_name='运行资源公司', status='ENABLED')
    db.add(company)
    db.flush()
    project = CrawlerProject(
        company_id=company.company_id,
        project_code=f'runtime_resource_project_{suffix}',
        project_name=f'运行资源项目 {suffix}',
        project_key=f'runtime_resource_project_{suffix}',
        image_repository='registry/runtime-resource-project',
        status='ENABLED',
        online_status='READY',
    )
    db.add(project)
    db.flush()
    release = CrawlerProjectRelease(
        company_id=company.company_id,
        project_id=project.project_id,
        version='1.0.90',
        release_channel='stable',
        image_repository='registry/runtime-resource-project',
        image_digest='sha256:' + ('b' * 64),
        release_status='PUBLISHED',
        parse_status='SUCCESS',
    )
    db.add(release)
    db.flush()
    channel = CrawlerReleaseChannel(company_id=company.company_id, project_id=project.project_id, channel_name='stable', release_id=release.release_id, channel_status='ENABLED')
    server = CrawlerServer(
        company_id=company.company_id,
        server_code=f'runtime-resource-node-{suffix}',
        server_name='运行资源节点',
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
        agent_code=f'runtime-resource-agent-{suffix}',
        agent_name='运行资源 Agent',
        token_hash=f'runtime-resource-token-hash-{suffix}',
        agent_version='1.0.90',
        protocol_version='1.0',
        agent_instance_id='instance-runtime-86',
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
    db.add_all([agent, project_server])
    db.flush()
    return company, project, release, server, agent


def test_agent_claim_resolves_company_resource_configs_without_persisting_plaintext_to_run_snapshot() -> None:
    migrate()
    with SessionLocal() as db:
        company, project, _release, _server, agent = _base_graph(db, 'a')
        resource = CompanyResourceConfig(
            company_id=company.company_id,
            project_id=None,
            resource_name='京多多结果 Mongo',
            resource_code='jdd_result_mongo',
            resource_category='DOCUMENT_DB',
            resource_engine='MONGODB',
            resource_role='RESULT_DB',
            connection_mode='URI',
            config_encrypted=_encrypted_config({'uri': 'mongodb://user:secret@127.0.0.1:27017/jdd', 'database': 'jdd'}),
            config_masked_snapshot={'uri': '***REDACTED***', 'database': 'jdd'},
            config_summary={'database': 'jdd'},
            remark='测试资源',
            enabled=True,
            test_status='CONFIG_VALID',
            last_test_message='基础配置完整',
        )
        task = CrawlerTask(
            company_id=company.company_id,
            project_id=project.project_id,
            task_code='jdd_items_sync',
            task_name='京多多现货商品采集',
            entry_module='spiders.jdd.items',
            entry_function='run',
            parameters={'pageSize': 10},
            config_bindings={'mongo_jdd': {'resourceCode': 'jdd_result_mongo'}},
            credential_bindings={},
            contract_snapshot={'requiredConfigs': [{'slot': 'mongo_jdd', 'type': 'MONGO', 'required': True}]},
            status='ENABLED',
            release_channel='stable',
        )
        db.add_all([resource, task])
        db.flush()

        run = RunService(db).create_run(task, None, utcnow(), {'pageNum': 1}, trigger_type='MANUAL')
        assert run.parameters_snapshot['configBindings'] == {'mongo_jdd': {'resourceCode': 'jdd_result_mongo'}}
        assert 'configs' not in run.parameters_snapshot
        assert 'mongodb://user:secret' not in json.dumps(run.parameters_snapshot, ensure_ascii=False)
        db.commit()

        claim = AgentService(db).claim_run(agent, AgentRunClaim(agent_instance_id='instance-runtime-86'))
        assert claim is not None
        assert claim['configs']['mongo_jdd']['uri'] == 'mongodb://user:secret@127.0.0.1:27017/jdd'
        assert claim['configs']['mongo_jdd']['resourceEngine'] == 'MONGODB'
        assert claim['runtimeConfigs'] == claim['configs']
        assert 'configs' not in claim['parameters']
        db.refresh(run)
        assert 'mongodb://user:secret' not in json.dumps(run.parameters_snapshot, ensure_ascii=False)


def test_required_resource_binding_rejects_wrong_engine() -> None:
    migrate()
    with SessionLocal() as db:
        company, project, *_ = _base_graph(db, 'b')
        resource = CompanyResourceConfig(
            company_id=company.company_id,
            resource_name='错误 Redis',
            resource_code='jdd_result_mongo',
            resource_category='CACHE_DB',
            resource_engine='REDIS',
            resource_role='RESULT_DB',
            connection_mode='HOST_PORT',
            config_encrypted=_encrypted_config({'host': '127.0.0.1', 'port': '6379'}),
            remark='测试资源',
            enabled=True,
            test_status='CONFIG_VALID',
        )
        db.add(resource)
        db.flush()
        errors = RuntimeResourceResolver(db).validate_bindings(
            company_id=company.company_id,
            project_id=project.project_id,
            required_configs=[{'slot': 'mongo_jdd', 'type': 'MONGO', 'required': True}],
            config_bindings={'mongo_jdd': 'config:jdd_result_mongo'},
        )
        assert errors
        assert '类型不匹配' in errors[0]
