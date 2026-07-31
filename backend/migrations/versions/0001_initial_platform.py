"""initial platform baseline

Revision ID: 0001_initial_platform
Revises:
Create Date: 2026-07-31
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_platform"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table('sys_user',
        sa.Column('user_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=True),
        sa.Column('user_name', sa.String(50), nullable=False),
        sa.Column('nick_name', sa.String(50), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role_type', sa.String(30), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('last_login_ip', sa.String(128), nullable=False),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.Column('current_session_id', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    op.create_table('sys_user_session',
        sa.Column('session_id', sa.String(64), primary_key=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=True),
        sa.Column('token_jti', sa.String(64), nullable=False),
        sa.Column('session_status', sa.String(30), nullable=False),
        sa.Column('login_time', sa.DateTime(), nullable=False),
        sa.Column('last_active_at', sa.DateTime(), nullable=False),
        sa.Column('logout_time', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('revoke_reason', sa.String(200), nullable=False),
        sa.Column('login_ip', sa.String(128), nullable=False),
        sa.Column('user_agent', sa.String(500), nullable=False),
        sa.Column('device_name', sa.String(200), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    op.create_table('sys_login_log',
        sa.Column('login_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('user_name', sa.String(50), nullable=False),
        sa.Column('ip_address', sa.String(128), nullable=False),
        sa.Column('user_agent', sa.String(500), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('message', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    op.create_table('sys_operation_log',
        sa.Column('operation_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('user_name', sa.String(50), nullable=False),
        sa.Column('operation_type', sa.String(50), nullable=False),
        sa.Column('resource_type', sa.String(50), nullable=False),
        sa.Column('resource_id', sa.String(100), nullable=False),
        sa.Column('request_method', sa.String(10), nullable=False),
        sa.Column('request_path', sa.String(500), nullable=False),
        sa.Column('before_data', sa.JSON(), nullable=True),
        sa.Column('after_data', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(128), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    op.create_table('sys_config',
        sa.Column('config_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('config_key', sa.String(100), nullable=False),
        sa.Column('config_name', sa.String(100), nullable=False),
        sa.Column('config_value', sa.Text(), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('config_key', name='uq_sys_config_config_key'),
    )

    op.create_table('sys_secret',
        sa.Column('secret_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=True),
        sa.Column('project_id', sa.BigInteger(), nullable=True),
        sa.Column('secret_code', sa.String(100), nullable=False),
        sa.Column('secret_name', sa.String(100), nullable=False),
        sa.Column('encrypted_value', sa.Text(), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('secret_code', name='uq_sys_secret_secret_code'),
    )

    op.create_table('crawler_company',
        sa.Column('company_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_code', sa.String(100), nullable=False),
        sa.Column('company_name', sa.String(150), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('timezone', sa.String(100), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    op.create_table('crawler_server',
        sa.Column('server_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('server_code', sa.String(100), nullable=False),
        sa.Column('server_name', sa.String(100), nullable=False),
        sa.Column('server_ip', sa.String(128), nullable=False),
        sa.Column('environment', sa.String(30), nullable=False),
        sa.Column('max_container_slots', sa.Integer(), nullable=False),
        sa.Column('manage_status', sa.String(20), nullable=False),
        sa.Column('health_status', sa.String(20), nullable=False),
        sa.Column('capacity_status', sa.String(20), nullable=False),
        sa.Column('metrics', sa.JSON(), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    op.create_table('crawler_agent',
        sa.Column('agent_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('server_id', sa.BigInteger(), nullable=False),
        sa.Column('agent_code', sa.String(100), nullable=False),
        sa.Column('agent_name', sa.String(100), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('agent_version', sa.String(50), nullable=False),
        sa.Column('protocol_version', sa.String(30), nullable=False),
        sa.Column('agent_instance_id', sa.String(100), nullable=False),
        sa.Column('connection_status', sa.String(20), nullable=False),
        sa.Column('last_heartbeat_at', sa.DateTime(), nullable=True),
        sa.Column('heartbeat_interval_seconds', sa.Integer(), nullable=False),
        sa.Column('capabilities', sa.JSON(), nullable=False),
        sa.Column('current_runs', sa.JSON(), nullable=False),
        sa.Column('last_error', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('token_hash', name='uq_crawler_agent_token_hash'),
    )

    op.create_table('crawler_company_discovery_token',
        sa.Column('token_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('token_name', sa.String(120), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('token_hash', name='uq_crawler_company_discovery_token_token_hash'),
    )

    op.create_table('crawler_discovered_project',
        sa.Column('discovered_project_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('project_key', sa.String(200), nullable=False),
        sa.Column('project_code', sa.String(100), nullable=False),
        sa.Column('project_name', sa.String(150), nullable=False),
        sa.Column('repository_url', sa.String(500), nullable=False),
        sa.Column('image_repository', sa.String(500), nullable=False),
        sa.Column('latest_release_id', sa.BigInteger(), nullable=True),
        sa.Column('latest_version', sa.String(100), nullable=False),
        sa.Column('latest_image_digest', sa.String(100), nullable=False),
        sa.Column('discovery_status', sa.String(30), nullable=False),
        sa.Column('parse_status', sa.String(30), nullable=False),
        sa.Column('parse_error', sa.Text(), nullable=False),
        sa.Column('first_deployed_at', sa.DateTime(), nullable=True),
        sa.Column('last_deployed_at', sa.DateTime(), nullable=True),
        sa.Column('formal_project_id', sa.BigInteger(), nullable=True),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('company_id', 'project_key', name='uk_discovered_company_project_key'),
    )

    op.create_table('crawler_discovered_project_server',
        sa.Column('discovered_project_server_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('discovered_project_id', sa.BigInteger(), nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('server_id', sa.BigInteger(), nullable=False),
        sa.Column('deployment_status', sa.String(30), nullable=False),
        sa.Column('latest_image_digest', sa.String(100), nullable=False),
        sa.Column('last_deployed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('discovered_project_id', 'server_id', name='uk_discovered_project_server'),
    )

    op.create_table('crawler_project',
        sa.Column('project_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('discovered_project_id', sa.BigInteger(), nullable=True),
        sa.Column('project_key', sa.String(200), nullable=False),
        sa.Column('project_code', sa.String(100), nullable=False),
        sa.Column('project_name', sa.String(150), nullable=False),
        sa.Column('remark', sa.String(500), nullable=False),
        sa.Column('repository_url', sa.String(500), nullable=False),
        sa.Column('image_repository', sa.String(500), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('online_status', sa.String(30), nullable=False),
        sa.Column('dispatch_mode', sa.String(30), nullable=False),
        sa.Column('min_available_servers', sa.Integer(), nullable=False),
        sa.Column('max_active_servers', sa.Integer(), nullable=False),
        sa.Column('allow_deployed_fallback', sa.Boolean(), nullable=False),
        sa.Column('allow_company_pool_fallback', sa.Boolean(), nullable=False),
        sa.Column('default_runtime_mode', sa.String(40), nullable=False),
        sa.Column('default_task_max_concurrency', sa.Integer(), nullable=False),
        sa.Column('default_group_max_concurrency', sa.Integer(), nullable=False),
        sa.Column('default_shm_size_mb', sa.Integer(), nullable=False),
        sa.Column('default_log_limit_mb', sa.Integer(), nullable=False),
        sa.Column('container_config', sa.JSON(), nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('company_id', 'project_code', name='uk_project_company_code'),
    )

    op.create_table('crawler_project_member',
        sa.Column('member_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('project_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('project_id', 'user_id', name='uk_project_user'),
    )

    op.create_table('crawler_project_server',
        sa.Column('project_server_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('project_id', sa.BigInteger(), nullable=False),
        sa.Column('server_id', sa.BigInteger(), nullable=False),
        sa.Column('deployment_status', sa.String(30), nullable=False),
        sa.Column('scheduling_status', sa.String(30), nullable=False),
        sa.Column('image_readiness_status', sa.String(30), nullable=False),
        sa.Column('server_role', sa.String(20), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('weight', sa.Integer(), nullable=False),
        sa.Column('max_concurrency', sa.Integer(), nullable=False),
        sa.Column('auto_eject_enabled', sa.Boolean(), nullable=False),
        sa.Column('auto_recover_enabled', sa.Boolean(), nullable=False),
        sa.Column('latest_release_id', sa.BigInteger(), nullable=True),
        sa.Column('latest_image_digest', sa.String(100), nullable=False),
        sa.Column('last_deployed_at', sa.DateTime(), nullable=True),
        sa.Column('disabled_reason', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('project_id', 'server_id', name='uk_project_server'),
    )

    op.create_table('crawler_image_artifact',
        sa.Column('artifact_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('image_repository', sa.String(500), nullable=False),
        sa.Column('image_tag', sa.String(255), nullable=False),
        sa.Column('image_digest', sa.String(100), nullable=False),
        sa.Column('supported_arch', sa.String(100), nullable=False),
        sa.Column('git_commit', sa.String(100), nullable=False),
        sa.Column('build_time', sa.DateTime(), nullable=True),
        sa.Column('artifact_metadata', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('image_repository', 'image_digest', name='uk_image_repository_digest'),
    )

    op.create_table('crawler_project_release',
        sa.Column('release_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('project_id', sa.BigInteger(), nullable=True),
        sa.Column('discovered_project_id', sa.BigInteger(), nullable=True),
        sa.Column('artifact_id', sa.BigInteger(), nullable=True),
        sa.Column('version', sa.String(100), nullable=False),
        sa.Column('release_channel', sa.String(50), nullable=False),
        sa.Column('image_repository', sa.String(500), nullable=False),
        sa.Column('image_digest', sa.String(100), nullable=False),
        sa.Column('git_branch', sa.String(100), nullable=False),
        sa.Column('git_commit', sa.String(100), nullable=False),
        sa.Column('manifest_version', sa.String(30), nullable=False),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.Column('release_status', sa.String(30), nullable=False),
        sa.Column('parse_status', sa.String(30), nullable=False),
        sa.Column('parse_error', sa.Text(), nullable=False),
        sa.Column('published_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('discovered_project_id', 'version', name='uk_discovered_release_version'),
        sa.UniqueConstraint('project_id', 'version', name='uk_project_release_version'),
    )

    op.create_table('crawler_release_channel',
        sa.Column('channel_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('project_id', sa.BigInteger(), nullable=False),
        sa.Column('channel_name', sa.String(50), nullable=False),
        sa.Column('release_id', sa.BigInteger(), nullable=True),
        sa.Column('channel_status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('project_id', 'channel_name', name='uk_project_channel'),
    )

    op.create_table('crawler_project_task_definition',
        sa.Column('definition_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('project_id', sa.BigInteger(), nullable=False),
        sa.Column('latest_release_id', sa.BigInteger(), nullable=True),
        sa.Column('definition_key', sa.String(200), nullable=False),
        sa.Column('task_name', sa.String(200), nullable=False),
        sa.Column('entry_module', sa.String(300), nullable=False),
        sa.Column('entry_function', sa.String(120), nullable=False),
        sa.Column('source_file', sa.String(300), nullable=False),
        sa.Column('source_fingerprint', sa.String(100), nullable=False),
        sa.Column('default_params', sa.JSON(), nullable=False),
        sa.Column('suggested_cron', sa.String(100), nullable=False),
        sa.Column('execution_mode', sa.String(20), nullable=False),
        sa.Column('idempotency_policy', sa.String(30), nullable=False),
        sa.Column('resource_requirements', sa.JSON(), nullable=False),
        sa.Column('required_capabilities', sa.JSON(), nullable=False),
        sa.Column('runtime_mode', sa.String(40), nullable=False),
        sa.Column('task_group', sa.String(100), nullable=False),
        sa.Column('task_max_concurrency', sa.Integer(), nullable=False),
        sa.Column('group_max_concurrency', sa.Integer(), nullable=False),
        sa.Column('exclusive_mode', sa.Boolean(), nullable=False),
        sa.Column('io_class', sa.String(30), nullable=False),
        sa.Column('shm_size_mb', sa.Integer(), nullable=False),
        sa.Column('log_limit_mb', sa.Integer(), nullable=False),
        sa.Column('resource_locks', sa.JSON(), nullable=False),
        sa.Column('secret_refs', sa.JSON(), nullable=False),
        sa.Column('definition_status', sa.String(30), nullable=False),
        sa.Column('parse_message', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('project_id', 'definition_key', name='uk_project_definition_key'),
    )

    op.create_table('crawler_task',
        sa.Column('task_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('project_id', sa.BigInteger(), nullable=False),
        sa.Column('definition_id', sa.BigInteger(), nullable=True),
        sa.Column('task_code', sa.String(120), nullable=False),
        sa.Column('task_name', sa.String(200), nullable=False),
        sa.Column('entry_module', sa.String(300), nullable=False),
        sa.Column('entry_function', sa.String(120), nullable=False),
        sa.Column('parameters', sa.JSON(), nullable=False),
        sa.Column('execution_mode', sa.String(20), nullable=False),
        sa.Column('shard_strategy', sa.JSON(), nullable=False),
        sa.Column('required_node_count', sa.Integer(), nullable=False),
        sa.Column('max_parallel_nodes', sa.Integer(), nullable=False),
        sa.Column('required_capabilities', sa.JSON(), nullable=False),
        sa.Column('runtime_mode', sa.String(40), nullable=False),
        sa.Column('task_group', sa.String(100), nullable=False),
        sa.Column('task_max_concurrency', sa.Integer(), nullable=False),
        sa.Column('group_max_concurrency', sa.Integer(), nullable=False),
        sa.Column('exclusive_mode', sa.Boolean(), nullable=False),
        sa.Column('io_class', sa.String(30), nullable=False),
        sa.Column('shm_size_mb', sa.Integer(), nullable=False),
        sa.Column('log_limit_mb', sa.Integer(), nullable=False),
        sa.Column('resource_locks', sa.JSON(), nullable=False),
        sa.Column('idempotency_policy', sa.String(30), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('image_policy', sa.String(30), nullable=False),
        sa.Column('release_channel', sa.String(50), nullable=False),
        sa.Column('fixed_release_id', sa.BigInteger(), nullable=True),
        sa.Column('cpu_limit', sa.Float(), nullable=False),
        sa.Column('memory_limit_mb', sa.Integer(), nullable=False),
        sa.Column('timeout_seconds', sa.Integer(), nullable=False),
        sa.Column('max_retry_count', sa.Integer(), nullable=False),
        sa.Column('description', sa.String(1000), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('project_id', 'definition_id', name='uk_project_definition_task'),
        sa.UniqueConstraint('project_id', 'task_code', name='uk_project_task_code'),
    )

    op.create_table('crawler_task_schedule',
        sa.Column('schedule_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('project_id', sa.BigInteger(), nullable=False),
        sa.Column('task_id', sa.BigInteger(), nullable=False),
        sa.Column('schedule_status', sa.String(20), nullable=False),
        sa.Column('schedule_type', sa.String(20), nullable=False),
        sa.Column('cron_expression', sa.String(100), nullable=False),
        sa.Column('schedule_timezone', sa.String(100), nullable=False),
        sa.Column('overlap_policy', sa.String(30), nullable=False),
        sa.Column('schedule_config', sa.JSON(), nullable=False),
        sa.Column('schedule_label', sa.String(200), nullable=False),
        sa.Column('next_run_at', sa.DateTime(), nullable=True),
        sa.Column('last_triggered_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    op.create_table('crawler_task_server_target',
        sa.Column('target_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('task_id', sa.BigInteger(), nullable=False),
        sa.Column('server_id', sa.BigInteger(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('weight', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('task_id', 'server_id', name='uk_task_server_target'),
    )

    op.create_table('crawler_task_run',
        sa.Column('run_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('project_id', sa.BigInteger(), nullable=False),
        sa.Column('task_id', sa.BigInteger(), nullable=False),
        sa.Column('schedule_id', sa.BigInteger(), nullable=True),
        sa.Column('parent_run_id', sa.BigInteger(), nullable=True),
        sa.Column('root_run_id', sa.BigInteger(), nullable=True),
        sa.Column('server_id', sa.BigInteger(), nullable=True),
        sa.Column('agent_id', sa.BigInteger(), nullable=True),
        sa.Column('release_id', sa.BigInteger(), nullable=True),
        sa.Column('image_repository', sa.String(500), nullable=False),
        sa.Column('image_digest', sa.String(100), nullable=False),
        sa.Column('entry_module', sa.String(300), nullable=False),
        sa.Column('entry_function', sa.String(120), nullable=False),
        sa.Column('execution_mode', sa.String(20), nullable=False),
        sa.Column('shard_index', sa.Integer(), nullable=True),
        sa.Column('shard_count', sa.Integer(), nullable=True),
        sa.Column('trigger_type', sa.String(30), nullable=False),
        sa.Column('idempotency_policy', sa.String(30), nullable=False),
        sa.Column('cpu_limit', sa.Float(), nullable=False),
        sa.Column('memory_limit_mb', sa.Integer(), nullable=False),
        sa.Column('timeout_seconds', sa.Integer(), nullable=False),
        sa.Column('runtime_mode', sa.String(40), nullable=False),
        sa.Column('task_group', sa.String(100), nullable=False),
        sa.Column('task_max_concurrency', sa.Integer(), nullable=False),
        sa.Column('group_max_concurrency', sa.Integer(), nullable=False),
        sa.Column('exclusive_mode', sa.Boolean(), nullable=False),
        sa.Column('io_class', sa.String(30), nullable=False),
        sa.Column('shm_size_mb', sa.Integer(), nullable=False),
        sa.Column('log_limit_mb', sa.Integer(), nullable=False),
        sa.Column('resource_locks', sa.JSON(), nullable=False),
        sa.Column('run_status', sa.String(30), nullable=False),
        sa.Column('routing_status', sa.String(30), nullable=False),
        sa.Column('routing_reason', sa.String(500), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(), nullable=True),
        sa.Column('trigger_key', sa.String(220), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('attempt', sa.Integer(), nullable=False),
        sa.Column('max_attempts', sa.Integer(), nullable=False),
        sa.Column('lease_token', sa.String(64), nullable=False),
        sa.Column('lease_expires_at', sa.DateTime(), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(), nullable=True),
        sa.Column('parameters_snapshot', sa.JSON(), nullable=False),
        sa.Column('result_payload', sa.JSON(), nullable=False),
        sa.Column('retry_reason', sa.String(500), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('task_id', 'trigger_key', name='uk_task_trigger_key'),
    )

    op.create_table('crawler_run_log',
        sa.Column('log_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=False),
        sa.Column('run_id', sa.BigInteger(), nullable=False),
        sa.Column('log_level', sa.String(20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )

    op.create_table('sys_notification_channel',
        sa.Column('channel_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('scope_type', sa.String(20), nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=True),
        sa.Column('project_id', sa.BigInteger(), nullable=True),
        sa.Column('channel_name', sa.String(100), nullable=False),
        sa.Column('channel_type', sa.String(30), nullable=False),
        sa.Column('channel_status', sa.String(20), nullable=False),
        sa.Column('config_encrypted', sa.Text(), nullable=False),
        sa.Column('p0_only', sa.Boolean(), nullable=False),
        sa.Column('last_test_at', sa.DateTime(), nullable=True),
        sa.Column('last_test_result', sa.String(500), nullable=False),
        sa.Column('cooldown_seconds', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    op.create_table('sys_alert_event',
        sa.Column('alert_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('company_id', sa.BigInteger(), nullable=True),
        sa.Column('project_id', sa.BigInteger(), nullable=True),
        sa.Column('severity', sa.String(10), nullable=False),
        sa.Column('alert_status', sa.String(20), nullable=False),
        sa.Column('alert_type', sa.String(100), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('fingerprint', sa.String(100), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), nullable=False),
        sa.Column('notified_at', sa.DateTime(), nullable=True),
        sa.Column('notify_after_at', sa.DateTime(), nullable=True),
        sa.Column('occurrence_count', sa.Integer(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('alert_metadata', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('fingerprint', 'alert_status', name='uk_alert_fingerprint_status'),
    )

    op.create_table('sys_alert_delivery',
        sa.Column('delivery_id', sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('alert_id', sa.BigInteger(), nullable=False),
        sa.Column('channel_id', sa.BigInteger(), nullable=False),
        sa.Column('delivery_status', sa.String(20), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.Text(), nullable=False),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )

    op.create_index('ix_sys_user_company_id', 'sys_user', ['company_id'], unique=False)
    op.create_index('ix_sys_user_current_session_id', 'sys_user', ['current_session_id'], unique=False)
    op.create_index('ix_sys_user_role_type', 'sys_user', ['role_type'], unique=False)
    op.create_index('ix_sys_user_status', 'sys_user', ['status'], unique=False)
    op.create_index('ix_sys_user_user_name', 'sys_user', ['user_name'], unique=True)
    op.create_index('idx_session_user_status', 'sys_user_session', ['user_id', 'session_status', 'last_active_at'], unique=False)
    op.create_index('ix_sys_user_session_company_id', 'sys_user_session', ['company_id'], unique=False)
    op.create_index('ix_sys_user_session_last_active_at', 'sys_user_session', ['last_active_at'], unique=False)
    op.create_index('ix_sys_user_session_session_status', 'sys_user_session', ['session_status'], unique=False)
    op.create_index('ix_sys_user_session_user_id', 'sys_user_session', ['user_id'], unique=False)
    op.create_index('ix_sys_login_log_created_at', 'sys_login_log', ['created_at'], unique=False)
    op.create_index('ix_sys_login_log_status', 'sys_login_log', ['status'], unique=False)
    op.create_index('ix_sys_login_log_user_id', 'sys_login_log', ['user_id'], unique=False)
    op.create_index('ix_sys_operation_log_created_at', 'sys_operation_log', ['created_at'], unique=False)
    op.create_index('ix_sys_operation_log_operation_type', 'sys_operation_log', ['operation_type'], unique=False)
    op.create_index('ix_sys_operation_log_resource_type', 'sys_operation_log', ['resource_type'], unique=False)
    op.create_index('ix_sys_operation_log_status', 'sys_operation_log', ['status'], unique=False)
    op.create_index('ix_sys_operation_log_user_id', 'sys_operation_log', ['user_id'], unique=False)
    op.create_index('ix_sys_secret_company_id', 'sys_secret', ['company_id'], unique=False)
    op.create_index('ix_sys_secret_project_id', 'sys_secret', ['project_id'], unique=False)
    op.create_index('ix_crawler_company_company_code', 'crawler_company', ['company_code'], unique=True)
    op.create_index('ix_crawler_company_status', 'crawler_company', ['status'], unique=False)
    op.create_index('idx_server_company_manage', 'crawler_server', ['company_id', 'manage_status'], unique=False)
    op.create_index('ix_crawler_server_capacity_status', 'crawler_server', ['capacity_status'], unique=False)
    op.create_index('ix_crawler_server_company_id', 'crawler_server', ['company_id'], unique=False)
    op.create_index('ix_crawler_server_environment', 'crawler_server', ['environment'], unique=False)
    op.create_index('ix_crawler_server_health_status', 'crawler_server', ['health_status'], unique=False)
    op.create_index('ix_crawler_server_manage_status', 'crawler_server', ['manage_status'], unique=False)
    op.create_index('ix_crawler_server_server_code', 'crawler_server', ['server_code'], unique=True)
    op.create_index('ix_crawler_agent_agent_code', 'crawler_agent', ['agent_code'], unique=True)
    op.create_index('ix_crawler_agent_agent_instance_id', 'crawler_agent', ['agent_instance_id'], unique=False)
    op.create_index('ix_crawler_agent_company_id', 'crawler_agent', ['company_id'], unique=False)
    op.create_index('ix_crawler_agent_connection_status', 'crawler_agent', ['connection_status'], unique=False)
    op.create_index('ix_crawler_agent_server_id', 'crawler_agent', ['server_id'], unique=True)
    op.create_index('ix_crawler_company_discovery_token_company_id', 'crawler_company_discovery_token', ['company_id'], unique=False)
    op.create_index('ix_crawler_company_discovery_token_status', 'crawler_company_discovery_token', ['status'], unique=False)
    op.create_index('ix_crawler_discovered_project_company_id', 'crawler_discovered_project', ['company_id'], unique=False)
    op.create_index('ix_crawler_discovered_project_discovery_status', 'crawler_discovered_project', ['discovery_status'], unique=False)
    op.create_index('ix_crawler_discovered_project_formal_project_id', 'crawler_discovered_project', ['formal_project_id'], unique=False)
    op.create_index('ix_crawler_discovered_project_latest_release_id', 'crawler_discovered_project', ['latest_release_id'], unique=False)
    op.create_index('ix_crawler_discovered_project_parse_status', 'crawler_discovered_project', ['parse_status'], unique=False)
    op.create_index('ix_crawler_discovered_project_project_code', 'crawler_discovered_project', ['project_code'], unique=False)
    op.create_index('ix_crawler_discovered_project_server_company_id', 'crawler_discovered_project_server', ['company_id'], unique=False)
    op.create_index('ix_crawler_discovered_project_server_deployment_status', 'crawler_discovered_project_server', ['deployment_status'], unique=False)
    op.create_index('ix_crawler_discovered_project_server_discovered_project_id', 'crawler_discovered_project_server', ['discovered_project_id'], unique=False)
    op.create_index('ix_crawler_discovered_project_server_server_id', 'crawler_discovered_project_server', ['server_id'], unique=False)
    op.create_index('idx_project_company_status', 'crawler_project', ['company_id', 'status', 'online_status'], unique=False)
    op.create_index('ix_crawler_project_company_id', 'crawler_project', ['company_id'], unique=False)
    op.create_index('ix_crawler_project_discovered_project_id', 'crawler_project', ['discovered_project_id'], unique=False)
    op.create_index('ix_crawler_project_dispatch_mode', 'crawler_project', ['dispatch_mode'], unique=False)
    op.create_index('ix_crawler_project_default_runtime_mode', 'crawler_project', ['default_runtime_mode'], unique=False)
    op.create_index('ix_crawler_project_online_status', 'crawler_project', ['online_status'], unique=False)
    op.create_index('ix_crawler_project_project_code', 'crawler_project', ['project_code'], unique=False)
    op.create_index('ix_crawler_project_status', 'crawler_project', ['status'], unique=False)
    op.create_index('ix_crawler_project_member_project_id', 'crawler_project_member', ['project_id'], unique=False)
    op.create_index('ix_crawler_project_member_role', 'crawler_project_member', ['role'], unique=False)
    op.create_index('ix_crawler_project_member_user_id', 'crawler_project_member', ['user_id'], unique=False)
    op.create_index('idx_project_server_route', 'crawler_project_server', ['project_id', 'scheduling_status', 'image_readiness_status'], unique=False)
    op.create_index('ix_crawler_project_server_company_id', 'crawler_project_server', ['company_id'], unique=False)
    op.create_index('ix_crawler_project_server_deployment_status', 'crawler_project_server', ['deployment_status'], unique=False)
    op.create_index('ix_crawler_project_server_image_readiness_status', 'crawler_project_server', ['image_readiness_status'], unique=False)
    op.create_index('ix_crawler_project_server_latest_release_id', 'crawler_project_server', ['latest_release_id'], unique=False)
    op.create_index('ix_crawler_project_server_project_id', 'crawler_project_server', ['project_id'], unique=False)
    op.create_index('ix_crawler_project_server_scheduling_status', 'crawler_project_server', ['scheduling_status'], unique=False)
    op.create_index('ix_crawler_project_server_server_id', 'crawler_project_server', ['server_id'], unique=False)
    op.create_index('ix_crawler_project_server_server_role', 'crawler_project_server', ['server_role'], unique=False)
    op.create_index('ix_crawler_image_artifact_image_digest', 'crawler_image_artifact', ['image_digest'], unique=False)
    op.create_index('ix_crawler_image_artifact_image_repository', 'crawler_image_artifact', ['image_repository'], unique=False)
    op.create_index('ix_crawler_project_release_artifact_id', 'crawler_project_release', ['artifact_id'], unique=False)
    op.create_index('ix_crawler_project_release_company_id', 'crawler_project_release', ['company_id'], unique=False)
    op.create_index('ix_crawler_project_release_discovered_project_id', 'crawler_project_release', ['discovered_project_id'], unique=False)
    op.create_index('ix_crawler_project_release_image_digest', 'crawler_project_release', ['image_digest'], unique=False)
    op.create_index('ix_crawler_project_release_parse_status', 'crawler_project_release', ['parse_status'], unique=False)
    op.create_index('ix_crawler_project_release_project_id', 'crawler_project_release', ['project_id'], unique=False)
    op.create_index('ix_crawler_project_release_published_at', 'crawler_project_release', ['published_at'], unique=False)
    op.create_index('ix_crawler_project_release_release_channel', 'crawler_project_release', ['release_channel'], unique=False)
    op.create_index('ix_crawler_project_release_release_status', 'crawler_project_release', ['release_status'], unique=False)
    op.create_index('ix_crawler_project_release_version', 'crawler_project_release', ['version'], unique=False)
    op.create_index('ix_crawler_release_channel_channel_status', 'crawler_release_channel', ['channel_status'], unique=False)
    op.create_index('ix_crawler_release_channel_company_id', 'crawler_release_channel', ['company_id'], unique=False)
    op.create_index('ix_crawler_release_channel_project_id', 'crawler_release_channel', ['project_id'], unique=False)
    op.create_index('ix_crawler_release_channel_release_id', 'crawler_release_channel', ['release_id'], unique=False)
    op.create_index('ix_crawler_project_task_definition_company_id', 'crawler_project_task_definition', ['company_id'], unique=False)
    op.create_index('ix_crawler_project_task_definition_definition_status', 'crawler_project_task_definition', ['definition_status'], unique=False)
    op.create_index('ix_crawler_project_task_definition_execution_mode', 'crawler_project_task_definition', ['execution_mode'], unique=False)
    op.create_index('ix_crawler_project_task_definition_runtime_mode', 'crawler_project_task_definition', ['runtime_mode'], unique=False)
    op.create_index('ix_crawler_project_task_definition_task_group', 'crawler_project_task_definition', ['task_group'], unique=False)
    op.create_index('ix_crawler_project_task_definition_io_class', 'crawler_project_task_definition', ['io_class'], unique=False)
    op.create_index('ix_crawler_project_task_definition_idempotency_policy', 'crawler_project_task_definition', ['idempotency_policy'], unique=False)
    op.create_index('ix_crawler_project_task_definition_latest_release_id', 'crawler_project_task_definition', ['latest_release_id'], unique=False)
    op.create_index('ix_crawler_project_task_definition_project_id', 'crawler_project_task_definition', ['project_id'], unique=False)
    op.create_index('idx_task_company_status', 'crawler_task', ['company_id', 'status'], unique=False)
    op.create_index('idx_task_group_limits', 'crawler_task', ['company_id', 'project_id', 'task_group'], unique=False)
    op.create_index('ix_crawler_task_company_id', 'crawler_task', ['company_id'], unique=False)
    op.create_index('ix_crawler_task_definition_id', 'crawler_task', ['definition_id'], unique=False)
    op.create_index('ix_crawler_task_execution_mode', 'crawler_task', ['execution_mode'], unique=False)
    op.create_index('ix_crawler_task_runtime_mode', 'crawler_task', ['runtime_mode'], unique=False)
    op.create_index('ix_crawler_task_task_group', 'crawler_task', ['task_group'], unique=False)
    op.create_index('ix_crawler_task_io_class', 'crawler_task', ['io_class'], unique=False)
    op.create_index('ix_crawler_task_fixed_release_id', 'crawler_task', ['fixed_release_id'], unique=False)
    op.create_index('ix_crawler_task_idempotency_policy', 'crawler_task', ['idempotency_policy'], unique=False)
    op.create_index('ix_crawler_task_project_id', 'crawler_task', ['project_id'], unique=False)
    op.create_index('ix_crawler_task_status', 'crawler_task', ['status'], unique=False)
    op.create_index('ix_crawler_task_task_code', 'crawler_task', ['task_code'], unique=False)
    op.create_index('ix_crawler_task_schedule_company_id', 'crawler_task_schedule', ['company_id'], unique=False)
    op.create_index('ix_crawler_task_schedule_next_run_at', 'crawler_task_schedule', ['next_run_at'], unique=False)
    op.create_index('ix_crawler_task_schedule_project_id', 'crawler_task_schedule', ['project_id'], unique=False)
    op.create_index('ix_crawler_task_schedule_schedule_status', 'crawler_task_schedule', ['schedule_status'], unique=False)
    op.create_index('ix_crawler_task_schedule_task_id', 'crawler_task_schedule', ['task_id'], unique=True)
    op.create_index('ix_crawler_task_server_target_company_id', 'crawler_task_server_target', ['company_id'], unique=False)
    op.create_index('ix_crawler_task_server_target_server_id', 'crawler_task_server_target', ['server_id'], unique=False)
    op.create_index('ix_crawler_task_server_target_task_id', 'crawler_task_server_target', ['task_id'], unique=False)
    op.create_index('idx_run_route', 'crawler_task_run', ['run_status', 'routing_status', 'server_id'], unique=False)
    op.create_index('idx_run_task_group_active', 'crawler_task_run', ['project_id', 'task_group', 'run_status'], unique=False)
    op.create_index('ix_crawler_task_run_agent_id', 'crawler_task_run', ['agent_id'], unique=False)
    op.create_index('ix_crawler_task_run_company_id', 'crawler_task_run', ['company_id'], unique=False)
    op.create_index('ix_crawler_task_run_execution_mode', 'crawler_task_run', ['execution_mode'], unique=False)
    op.create_index('ix_crawler_task_run_runtime_mode', 'crawler_task_run', ['runtime_mode'], unique=False)
    op.create_index('ix_crawler_task_run_task_group', 'crawler_task_run', ['task_group'], unique=False)
    op.create_index('ix_crawler_task_run_io_class', 'crawler_task_run', ['io_class'], unique=False)
    op.create_index('ix_crawler_task_run_idempotency_policy', 'crawler_task_run', ['idempotency_policy'], unique=False)
    op.create_index('ix_crawler_task_run_lease_expires_at', 'crawler_task_run', ['lease_expires_at'], unique=False)
    op.create_index('ix_crawler_task_run_lease_token', 'crawler_task_run', ['lease_token'], unique=False)
    op.create_index('ix_crawler_task_run_parent_run_id', 'crawler_task_run', ['parent_run_id'], unique=False)
    op.create_index('ix_crawler_task_run_project_id', 'crawler_task_run', ['project_id'], unique=False)
    op.create_index('ix_crawler_task_run_release_id', 'crawler_task_run', ['release_id'], unique=False)
    op.create_index('ix_crawler_task_run_root_run_id', 'crawler_task_run', ['root_run_id'], unique=False)
    op.create_index('ix_crawler_task_run_routing_status', 'crawler_task_run', ['routing_status'], unique=False)
    op.create_index('ix_crawler_task_run_run_status', 'crawler_task_run', ['run_status'], unique=False)
    op.create_index('ix_crawler_task_run_schedule_id', 'crawler_task_run', ['schedule_id'], unique=False)
    op.create_index('ix_crawler_task_run_scheduled_at', 'crawler_task_run', ['scheduled_at'], unique=False)
    op.create_index('ix_crawler_task_run_server_id', 'crawler_task_run', ['server_id'], unique=False)
    op.create_index('ix_crawler_task_run_task_id', 'crawler_task_run', ['task_id'], unique=False)
    op.create_index('ix_crawler_task_run_trigger_key', 'crawler_task_run', ['trigger_key'], unique=False)
    op.create_index('ix_crawler_task_run_trigger_type', 'crawler_task_run', ['trigger_type'], unique=False)
    op.create_index('ix_crawler_run_log_company_id', 'crawler_run_log', ['company_id'], unique=False)
    op.create_index('ix_crawler_run_log_created_at', 'crawler_run_log', ['created_at'], unique=False)
    op.create_index('ix_crawler_run_log_log_level', 'crawler_run_log', ['log_level'], unique=False)
    op.create_index('ix_crawler_run_log_run_id', 'crawler_run_log', ['run_id'], unique=False)
    op.create_index('ix_sys_notification_channel_channel_status', 'sys_notification_channel', ['channel_status'], unique=False)
    op.create_index('ix_sys_notification_channel_channel_type', 'sys_notification_channel', ['channel_type'], unique=False)
    op.create_index('ix_sys_notification_channel_company_id', 'sys_notification_channel', ['company_id'], unique=False)
    op.create_index('ix_sys_notification_channel_project_id', 'sys_notification_channel', ['project_id'], unique=False)
    op.create_index('ix_sys_notification_channel_scope_type', 'sys_notification_channel', ['scope_type'], unique=False)
    op.create_index('ix_sys_alert_event_alert_status', 'sys_alert_event', ['alert_status'], unique=False)
    op.create_index('ix_sys_alert_event_alert_type', 'sys_alert_event', ['alert_type'], unique=False)
    op.create_index('ix_sys_alert_event_company_id', 'sys_alert_event', ['company_id'], unique=False)
    op.create_index('ix_sys_alert_event_fingerprint', 'sys_alert_event', ['fingerprint'], unique=False)
    op.create_index('ix_sys_alert_event_notify_after_at', 'sys_alert_event', ['notify_after_at'], unique=False)
    op.create_index('ix_sys_alert_event_project_id', 'sys_alert_event', ['project_id'], unique=False)
    op.create_index('ix_sys_alert_event_severity', 'sys_alert_event', ['severity'], unique=False)
    op.create_index('ix_sys_alert_delivery_alert_id', 'sys_alert_delivery', ['alert_id'], unique=False)
    op.create_index('ix_sys_alert_delivery_channel_id', 'sys_alert_delivery', ['channel_id'], unique=False)
    op.create_index('ix_sys_alert_delivery_delivery_status', 'sys_alert_delivery', ['delivery_status'], unique=False)

    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key('fk_sys_user_company_id_crawler_company', 'sys_user', 'crawler_company', ['company_id'], ['company_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_sys_user_session_user_id_sys_user', 'sys_user_session', 'sys_user', ['user_id'], ['user_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_sys_user_session_company_id_crawler_company', 'sys_user_session', 'crawler_company', ['company_id'], ['company_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_sys_login_log_user_id_sys_user', 'sys_login_log', 'sys_user', ['user_id'], ['user_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_sys_operation_log_user_id_sys_user', 'sys_operation_log', 'sys_user', ['user_id'], ['user_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_sys_secret_company_id_crawler_company', 'sys_secret', 'crawler_company', ['company_id'], ['company_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_sys_secret_project_id_crawler_project', 'sys_secret', 'crawler_project', ['project_id'], ['project_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_company_created_by_sys_user', 'crawler_company', 'sys_user', ['created_by'], ['user_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_crawler_server_company_id_crawler_company', 'crawler_server', 'crawler_company', ['company_id'], ['company_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_agent_server_id_crawler_server', 'crawler_agent', 'crawler_server', ['server_id'], ['server_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_agent_company_id_crawler_company', 'crawler_agent', 'crawler_company', ['company_id'], ['company_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_company_discovery_token_company_id_crawler_company', 'crawler_company_discovery_token', 'crawler_company', ['company_id'], ['company_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_discovered_project_latest_release_id_crawler_project_release', 'crawler_discovered_project', 'crawler_project_release', ['latest_release_id'], ['release_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_crawler_discovered_project_company_id_crawler_company', 'crawler_discovered_project', 'crawler_company', ['company_id'], ['company_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_discovered_project_formal_project_id_crawler_project', 'crawler_discovered_project', 'crawler_project', ['formal_project_id'], ['project_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_crawler_discovered_project_server_server_id_crawler_server', 'crawler_discovered_project_server', 'crawler_server', ['server_id'], ['server_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_discovered_project_server_company_id_crawler_company', 'crawler_discovered_project_server', 'crawler_company', ['company_id'], ['company_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_discovered_project_server_discovered_project_id_crawler_discovered_project', 'crawler_discovered_project_server', 'crawler_discovered_project', ['discovered_project_id'], ['discovered_project_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_project_discovered_project_id_crawler_discovered_project', 'crawler_project', 'crawler_discovered_project', ['discovered_project_id'], ['discovered_project_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_crawler_project_company_id_crawler_company', 'crawler_project', 'crawler_company', ['company_id'], ['company_id'], ondelete='RESTRICT')
        op.create_foreign_key('fk_crawler_project_created_by_sys_user', 'crawler_project', 'sys_user', ['created_by'], ['user_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_crawler_project_member_project_id_crawler_project', 'crawler_project_member', 'crawler_project', ['project_id'], ['project_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_project_member_user_id_sys_user', 'crawler_project_member', 'sys_user', ['user_id'], ['user_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_project_server_project_id_crawler_project', 'crawler_project_server', 'crawler_project', ['project_id'], ['project_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_project_server_company_id_crawler_company', 'crawler_project_server', 'crawler_company', ['company_id'], ['company_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_project_server_latest_release_id_crawler_project_release', 'crawler_project_server', 'crawler_project_release', ['latest_release_id'], ['release_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_crawler_project_server_server_id_crawler_server', 'crawler_project_server', 'crawler_server', ['server_id'], ['server_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_project_release_company_id_crawler_company', 'crawler_project_release', 'crawler_company', ['company_id'], ['company_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_project_release_artifact_id_crawler_image_artifact', 'crawler_project_release', 'crawler_image_artifact', ['artifact_id'], ['artifact_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_crawler_project_release_discovered_project_id_crawler_discovered_project', 'crawler_project_release', 'crawler_discovered_project', ['discovered_project_id'], ['discovered_project_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_project_release_project_id_crawler_project', 'crawler_project_release', 'crawler_project', ['project_id'], ['project_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_release_channel_release_id_crawler_project_release', 'crawler_release_channel', 'crawler_project_release', ['release_id'], ['release_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_crawler_release_channel_project_id_crawler_project', 'crawler_release_channel', 'crawler_project', ['project_id'], ['project_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_release_channel_company_id_crawler_company', 'crawler_release_channel', 'crawler_company', ['company_id'], ['company_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_project_task_definition_company_id_crawler_company', 'crawler_project_task_definition', 'crawler_company', ['company_id'], ['company_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_project_task_definition_latest_release_id_crawler_project_release', 'crawler_project_task_definition', 'crawler_project_release', ['latest_release_id'], ['release_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_crawler_project_task_definition_project_id_crawler_project', 'crawler_project_task_definition', 'crawler_project', ['project_id'], ['project_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_task_fixed_release_id_crawler_project_release', 'crawler_task', 'crawler_project_release', ['fixed_release_id'], ['release_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_crawler_task_definition_id_crawler_project_task_definition', 'crawler_task', 'crawler_project_task_definition', ['definition_id'], ['definition_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_crawler_task_project_id_crawler_project', 'crawler_task', 'crawler_project', ['project_id'], ['project_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_task_company_id_crawler_company', 'crawler_task', 'crawler_company', ['company_id'], ['company_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_task_schedule_company_id_crawler_company', 'crawler_task_schedule', 'crawler_company', ['company_id'], ['company_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_task_schedule_task_id_crawler_task', 'crawler_task_schedule', 'crawler_task', ['task_id'], ['task_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_task_schedule_project_id_crawler_project', 'crawler_task_schedule', 'crawler_project', ['project_id'], ['project_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_task_server_target_task_id_crawler_task', 'crawler_task_server_target', 'crawler_task', ['task_id'], ['task_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_task_server_target_company_id_crawler_company', 'crawler_task_server_target', 'crawler_company', ['company_id'], ['company_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_task_server_target_server_id_crawler_server', 'crawler_task_server_target', 'crawler_server', ['server_id'], ['server_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_task_run_company_id_crawler_company', 'crawler_task_run', 'crawler_company', ['company_id'], ['company_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_task_run_agent_id_crawler_agent', 'crawler_task_run', 'crawler_agent', ['agent_id'], ['agent_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_crawler_task_run_root_run_id_crawler_task_run', 'crawler_task_run', 'crawler_task_run', ['root_run_id'], ['run_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_crawler_task_run_schedule_id_crawler_task_schedule', 'crawler_task_run', 'crawler_task_schedule', ['schedule_id'], ['schedule_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_crawler_task_run_project_id_crawler_project', 'crawler_task_run', 'crawler_project', ['project_id'], ['project_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_task_run_release_id_crawler_project_release', 'crawler_task_run', 'crawler_project_release', ['release_id'], ['release_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_crawler_task_run_server_id_crawler_server', 'crawler_task_run', 'crawler_server', ['server_id'], ['server_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_crawler_task_run_parent_run_id_crawler_task_run', 'crawler_task_run', 'crawler_task_run', ['parent_run_id'], ['run_id'], ondelete='SET NULL')
        op.create_foreign_key('fk_crawler_task_run_task_id_crawler_task', 'crawler_task_run', 'crawler_task', ['task_id'], ['task_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_run_log_run_id_crawler_task_run', 'crawler_run_log', 'crawler_task_run', ['run_id'], ['run_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_crawler_run_log_company_id_crawler_company', 'crawler_run_log', 'crawler_company', ['company_id'], ['company_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_sys_notification_channel_project_id_crawler_project', 'sys_notification_channel', 'crawler_project', ['project_id'], ['project_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_sys_notification_channel_company_id_crawler_company', 'sys_notification_channel', 'crawler_company', ['company_id'], ['company_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_sys_alert_event_project_id_crawler_project', 'sys_alert_event', 'crawler_project', ['project_id'], ['project_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_sys_alert_event_company_id_crawler_company', 'sys_alert_event', 'crawler_company', ['company_id'], ['company_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_sys_alert_delivery_channel_id_sys_notification_channel', 'sys_alert_delivery', 'sys_notification_channel', ['channel_id'], ['channel_id'], ondelete='CASCADE')
        op.create_foreign_key('fk_sys_alert_delivery_alert_id_sys_alert_event', 'sys_alert_delivery', 'sys_alert_event', ['alert_id'], ['alert_id'], ondelete='CASCADE')

def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint('fk_sys_alert_delivery_alert_id_sys_alert_event', 'sys_alert_delivery', type_='foreignkey')
        op.drop_constraint('fk_sys_alert_delivery_channel_id_sys_notification_channel', 'sys_alert_delivery', type_='foreignkey')
        op.drop_constraint('fk_sys_alert_event_company_id_crawler_company', 'sys_alert_event', type_='foreignkey')
        op.drop_constraint('fk_sys_alert_event_project_id_crawler_project', 'sys_alert_event', type_='foreignkey')
        op.drop_constraint('fk_sys_notification_channel_company_id_crawler_company', 'sys_notification_channel', type_='foreignkey')
        op.drop_constraint('fk_sys_notification_channel_project_id_crawler_project', 'sys_notification_channel', type_='foreignkey')
        op.drop_constraint('fk_crawler_run_log_company_id_crawler_company', 'crawler_run_log', type_='foreignkey')
        op.drop_constraint('fk_crawler_run_log_run_id_crawler_task_run', 'crawler_run_log', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_run_task_id_crawler_task', 'crawler_task_run', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_run_parent_run_id_crawler_task_run', 'crawler_task_run', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_run_server_id_crawler_server', 'crawler_task_run', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_run_release_id_crawler_project_release', 'crawler_task_run', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_run_project_id_crawler_project', 'crawler_task_run', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_run_schedule_id_crawler_task_schedule', 'crawler_task_run', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_run_root_run_id_crawler_task_run', 'crawler_task_run', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_run_agent_id_crawler_agent', 'crawler_task_run', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_run_company_id_crawler_company', 'crawler_task_run', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_server_target_server_id_crawler_server', 'crawler_task_server_target', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_server_target_company_id_crawler_company', 'crawler_task_server_target', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_server_target_task_id_crawler_task', 'crawler_task_server_target', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_schedule_project_id_crawler_project', 'crawler_task_schedule', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_schedule_task_id_crawler_task', 'crawler_task_schedule', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_schedule_company_id_crawler_company', 'crawler_task_schedule', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_company_id_crawler_company', 'crawler_task', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_project_id_crawler_project', 'crawler_task', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_definition_id_crawler_project_task_definition', 'crawler_task', type_='foreignkey')
        op.drop_constraint('fk_crawler_task_fixed_release_id_crawler_project_release', 'crawler_task', type_='foreignkey')
        op.drop_constraint('fk_crawler_project_task_definition_project_id_crawler_project', 'crawler_project_task_definition', type_='foreignkey')
        op.drop_constraint('fk_crawler_project_task_definition_latest_release_id_crawler_project_release', 'crawler_project_task_definition', type_='foreignkey')
        op.drop_constraint('fk_crawler_project_task_definition_company_id_crawler_company', 'crawler_project_task_definition', type_='foreignkey')
        op.drop_constraint('fk_crawler_release_channel_company_id_crawler_company', 'crawler_release_channel', type_='foreignkey')
        op.drop_constraint('fk_crawler_release_channel_project_id_crawler_project', 'crawler_release_channel', type_='foreignkey')
        op.drop_constraint('fk_crawler_release_channel_release_id_crawler_project_release', 'crawler_release_channel', type_='foreignkey')
        op.drop_constraint('fk_crawler_project_release_project_id_crawler_project', 'crawler_project_release', type_='foreignkey')
        op.drop_constraint('fk_crawler_project_release_discovered_project_id_crawler_discovered_project', 'crawler_project_release', type_='foreignkey')
        op.drop_constraint('fk_crawler_project_release_artifact_id_crawler_image_artifact', 'crawler_project_release', type_='foreignkey')
        op.drop_constraint('fk_crawler_project_release_company_id_crawler_company', 'crawler_project_release', type_='foreignkey')
        op.drop_constraint('fk_crawler_project_server_server_id_crawler_server', 'crawler_project_server', type_='foreignkey')
        op.drop_constraint('fk_crawler_project_server_latest_release_id_crawler_project_release', 'crawler_project_server', type_='foreignkey')
        op.drop_constraint('fk_crawler_project_server_company_id_crawler_company', 'crawler_project_server', type_='foreignkey')
        op.drop_constraint('fk_crawler_project_server_project_id_crawler_project', 'crawler_project_server', type_='foreignkey')
        op.drop_constraint('fk_crawler_project_member_user_id_sys_user', 'crawler_project_member', type_='foreignkey')
        op.drop_constraint('fk_crawler_project_member_project_id_crawler_project', 'crawler_project_member', type_='foreignkey')
        op.drop_constraint('fk_crawler_project_created_by_sys_user', 'crawler_project', type_='foreignkey')
        op.drop_constraint('fk_crawler_project_company_id_crawler_company', 'crawler_project', type_='foreignkey')
        op.drop_constraint('fk_crawler_project_discovered_project_id_crawler_discovered_project', 'crawler_project', type_='foreignkey')
        op.drop_constraint('fk_crawler_discovered_project_server_discovered_project_id_crawler_discovered_project', 'crawler_discovered_project_server', type_='foreignkey')
        op.drop_constraint('fk_crawler_discovered_project_server_company_id_crawler_company', 'crawler_discovered_project_server', type_='foreignkey')
        op.drop_constraint('fk_crawler_discovered_project_server_server_id_crawler_server', 'crawler_discovered_project_server', type_='foreignkey')
        op.drop_constraint('fk_crawler_discovered_project_formal_project_id_crawler_project', 'crawler_discovered_project', type_='foreignkey')
        op.drop_constraint('fk_crawler_discovered_project_company_id_crawler_company', 'crawler_discovered_project', type_='foreignkey')
        op.drop_constraint('fk_crawler_discovered_project_latest_release_id_crawler_project_release', 'crawler_discovered_project', type_='foreignkey')
        op.drop_constraint('fk_crawler_company_discovery_token_company_id_crawler_company', 'crawler_company_discovery_token', type_='foreignkey')
        op.drop_constraint('fk_crawler_agent_company_id_crawler_company', 'crawler_agent', type_='foreignkey')
        op.drop_constraint('fk_crawler_agent_server_id_crawler_server', 'crawler_agent', type_='foreignkey')
        op.drop_constraint('fk_crawler_server_company_id_crawler_company', 'crawler_server', type_='foreignkey')
        op.drop_constraint('fk_crawler_company_created_by_sys_user', 'crawler_company', type_='foreignkey')
        op.drop_constraint('fk_sys_secret_project_id_crawler_project', 'sys_secret', type_='foreignkey')
        op.drop_constraint('fk_sys_secret_company_id_crawler_company', 'sys_secret', type_='foreignkey')
        op.drop_constraint('fk_sys_operation_log_user_id_sys_user', 'sys_operation_log', type_='foreignkey')
        op.drop_constraint('fk_sys_login_log_user_id_sys_user', 'sys_login_log', type_='foreignkey')
        op.drop_constraint('fk_sys_user_session_company_id_crawler_company', 'sys_user_session', type_='foreignkey')
        op.drop_constraint('fk_sys_user_session_user_id_sys_user', 'sys_user_session', type_='foreignkey')
        op.drop_constraint('fk_sys_user_company_id_crawler_company', 'sys_user', type_='foreignkey')
    op.drop_index('ix_sys_alert_delivery_delivery_status', table_name='sys_alert_delivery')
    op.drop_index('ix_sys_alert_delivery_channel_id', table_name='sys_alert_delivery')
    op.drop_index('ix_sys_alert_delivery_alert_id', table_name='sys_alert_delivery')
    op.drop_index('ix_sys_alert_event_severity', table_name='sys_alert_event')
    op.drop_index('ix_sys_alert_event_project_id', table_name='sys_alert_event')
    op.drop_index('ix_sys_alert_event_notify_after_at', table_name='sys_alert_event')
    op.drop_index('ix_sys_alert_event_fingerprint', table_name='sys_alert_event')
    op.drop_index('ix_sys_alert_event_company_id', table_name='sys_alert_event')
    op.drop_index('ix_sys_alert_event_alert_type', table_name='sys_alert_event')
    op.drop_index('ix_sys_alert_event_alert_status', table_name='sys_alert_event')
    op.drop_index('ix_sys_notification_channel_scope_type', table_name='sys_notification_channel')
    op.drop_index('ix_sys_notification_channel_project_id', table_name='sys_notification_channel')
    op.drop_index('ix_sys_notification_channel_company_id', table_name='sys_notification_channel')
    op.drop_index('ix_sys_notification_channel_channel_type', table_name='sys_notification_channel')
    op.drop_index('ix_sys_notification_channel_channel_status', table_name='sys_notification_channel')
    op.drop_index('ix_crawler_run_log_run_id', table_name='crawler_run_log')
    op.drop_index('ix_crawler_run_log_log_level', table_name='crawler_run_log')
    op.drop_index('ix_crawler_run_log_created_at', table_name='crawler_run_log')
    op.drop_index('ix_crawler_run_log_company_id', table_name='crawler_run_log')
    op.drop_index('ix_crawler_task_run_trigger_type', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_trigger_key', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_task_id', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_server_id', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_scheduled_at', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_schedule_id', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_run_status', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_routing_status', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_root_run_id', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_release_id', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_project_id', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_parent_run_id', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_lease_token', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_lease_expires_at', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_idempotency_policy', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_io_class', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_task_group', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_runtime_mode', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_execution_mode', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_company_id', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_run_agent_id', table_name='crawler_task_run')
    op.drop_index('idx_run_task_group_active', table_name='crawler_task_run')
    op.drop_index('idx_run_route', table_name='crawler_task_run')
    op.drop_index('ix_crawler_task_server_target_task_id', table_name='crawler_task_server_target')
    op.drop_index('ix_crawler_task_server_target_server_id', table_name='crawler_task_server_target')
    op.drop_index('ix_crawler_task_server_target_company_id', table_name='crawler_task_server_target')
    op.drop_index('ix_crawler_task_schedule_task_id', table_name='crawler_task_schedule')
    op.drop_index('ix_crawler_task_schedule_schedule_status', table_name='crawler_task_schedule')
    op.drop_index('ix_crawler_task_schedule_project_id', table_name='crawler_task_schedule')
    op.drop_index('ix_crawler_task_schedule_next_run_at', table_name='crawler_task_schedule')
    op.drop_index('ix_crawler_task_schedule_company_id', table_name='crawler_task_schedule')
    op.drop_index('ix_crawler_task_task_code', table_name='crawler_task')
    op.drop_index('ix_crawler_task_status', table_name='crawler_task')
    op.drop_index('ix_crawler_task_project_id', table_name='crawler_task')
    op.drop_index('ix_crawler_task_idempotency_policy', table_name='crawler_task')
    op.drop_index('ix_crawler_task_fixed_release_id', table_name='crawler_task')
    op.drop_index('ix_crawler_task_io_class', table_name='crawler_task')
    op.drop_index('ix_crawler_task_task_group', table_name='crawler_task')
    op.drop_index('ix_crawler_task_runtime_mode', table_name='crawler_task')
    op.drop_index('ix_crawler_task_execution_mode', table_name='crawler_task')
    op.drop_index('ix_crawler_task_definition_id', table_name='crawler_task')
    op.drop_index('ix_crawler_task_company_id', table_name='crawler_task')
    op.drop_index('idx_task_group_limits', table_name='crawler_task')
    op.drop_index('idx_task_company_status', table_name='crawler_task')
    op.drop_index('ix_crawler_project_task_definition_project_id', table_name='crawler_project_task_definition')
    op.drop_index('ix_crawler_project_task_definition_latest_release_id', table_name='crawler_project_task_definition')
    op.drop_index('ix_crawler_project_task_definition_idempotency_policy', table_name='crawler_project_task_definition')
    op.drop_index('ix_crawler_project_task_definition_io_class', table_name='crawler_project_task_definition')
    op.drop_index('ix_crawler_project_task_definition_task_group', table_name='crawler_project_task_definition')
    op.drop_index('ix_crawler_project_task_definition_runtime_mode', table_name='crawler_project_task_definition')
    op.drop_index('ix_crawler_project_task_definition_execution_mode', table_name='crawler_project_task_definition')
    op.drop_index('ix_crawler_project_task_definition_definition_status', table_name='crawler_project_task_definition')
    op.drop_index('ix_crawler_project_task_definition_company_id', table_name='crawler_project_task_definition')
    op.drop_index('ix_crawler_release_channel_release_id', table_name='crawler_release_channel')
    op.drop_index('ix_crawler_release_channel_project_id', table_name='crawler_release_channel')
    op.drop_index('ix_crawler_release_channel_company_id', table_name='crawler_release_channel')
    op.drop_index('ix_crawler_release_channel_channel_status', table_name='crawler_release_channel')
    op.drop_index('ix_crawler_project_release_version', table_name='crawler_project_release')
    op.drop_index('ix_crawler_project_release_release_status', table_name='crawler_project_release')
    op.drop_index('ix_crawler_project_release_release_channel', table_name='crawler_project_release')
    op.drop_index('ix_crawler_project_release_published_at', table_name='crawler_project_release')
    op.drop_index('ix_crawler_project_release_project_id', table_name='crawler_project_release')
    op.drop_index('ix_crawler_project_release_parse_status', table_name='crawler_project_release')
    op.drop_index('ix_crawler_project_release_image_digest', table_name='crawler_project_release')
    op.drop_index('ix_crawler_project_release_discovered_project_id', table_name='crawler_project_release')
    op.drop_index('ix_crawler_project_release_company_id', table_name='crawler_project_release')
    op.drop_index('ix_crawler_project_release_artifact_id', table_name='crawler_project_release')
    op.drop_index('ix_crawler_image_artifact_image_repository', table_name='crawler_image_artifact')
    op.drop_index('ix_crawler_image_artifact_image_digest', table_name='crawler_image_artifact')
    op.drop_index('ix_crawler_project_server_server_role', table_name='crawler_project_server')
    op.drop_index('ix_crawler_project_server_server_id', table_name='crawler_project_server')
    op.drop_index('ix_crawler_project_server_scheduling_status', table_name='crawler_project_server')
    op.drop_index('ix_crawler_project_server_project_id', table_name='crawler_project_server')
    op.drop_index('ix_crawler_project_server_latest_release_id', table_name='crawler_project_server')
    op.drop_index('ix_crawler_project_server_image_readiness_status', table_name='crawler_project_server')
    op.drop_index('ix_crawler_project_server_deployment_status', table_name='crawler_project_server')
    op.drop_index('ix_crawler_project_server_company_id', table_name='crawler_project_server')
    op.drop_index('idx_project_server_route', table_name='crawler_project_server')
    op.drop_index('ix_crawler_project_member_user_id', table_name='crawler_project_member')
    op.drop_index('ix_crawler_project_member_role', table_name='crawler_project_member')
    op.drop_index('ix_crawler_project_member_project_id', table_name='crawler_project_member')
    op.drop_index('ix_crawler_project_status', table_name='crawler_project')
    op.drop_index('ix_crawler_project_project_code', table_name='crawler_project')
    op.drop_index('ix_crawler_project_online_status', table_name='crawler_project')
    op.drop_index('ix_crawler_project_default_runtime_mode', table_name='crawler_project')
    op.drop_index('ix_crawler_project_dispatch_mode', table_name='crawler_project')
    op.drop_index('ix_crawler_project_discovered_project_id', table_name='crawler_project')
    op.drop_index('ix_crawler_project_company_id', table_name='crawler_project')
    op.drop_index('idx_project_company_status', table_name='crawler_project')
    op.drop_index('ix_crawler_discovered_project_server_server_id', table_name='crawler_discovered_project_server')
    op.drop_index('ix_crawler_discovered_project_server_discovered_project_id', table_name='crawler_discovered_project_server')
    op.drop_index('ix_crawler_discovered_project_server_deployment_status', table_name='crawler_discovered_project_server')
    op.drop_index('ix_crawler_discovered_project_server_company_id', table_name='crawler_discovered_project_server')
    op.drop_index('ix_crawler_discovered_project_project_code', table_name='crawler_discovered_project')
    op.drop_index('ix_crawler_discovered_project_parse_status', table_name='crawler_discovered_project')
    op.drop_index('ix_crawler_discovered_project_latest_release_id', table_name='crawler_discovered_project')
    op.drop_index('ix_crawler_discovered_project_formal_project_id', table_name='crawler_discovered_project')
    op.drop_index('ix_crawler_discovered_project_discovery_status', table_name='crawler_discovered_project')
    op.drop_index('ix_crawler_discovered_project_company_id', table_name='crawler_discovered_project')
    op.drop_index('ix_crawler_company_discovery_token_status', table_name='crawler_company_discovery_token')
    op.drop_index('ix_crawler_company_discovery_token_company_id', table_name='crawler_company_discovery_token')
    op.drop_index('ix_crawler_agent_server_id', table_name='crawler_agent')
    op.drop_index('ix_crawler_agent_connection_status', table_name='crawler_agent')
    op.drop_index('ix_crawler_agent_company_id', table_name='crawler_agent')
    op.drop_index('ix_crawler_agent_agent_instance_id', table_name='crawler_agent')
    op.drop_index('ix_crawler_agent_agent_code', table_name='crawler_agent')
    op.drop_index('ix_crawler_server_server_code', table_name='crawler_server')
    op.drop_index('ix_crawler_server_manage_status', table_name='crawler_server')
    op.drop_index('ix_crawler_server_health_status', table_name='crawler_server')
    op.drop_index('ix_crawler_server_environment', table_name='crawler_server')
    op.drop_index('ix_crawler_server_company_id', table_name='crawler_server')
    op.drop_index('ix_crawler_server_capacity_status', table_name='crawler_server')
    op.drop_index('idx_server_company_manage', table_name='crawler_server')
    op.drop_index('ix_crawler_company_status', table_name='crawler_company')
    op.drop_index('ix_crawler_company_company_code', table_name='crawler_company')
    op.drop_index('ix_sys_secret_project_id', table_name='sys_secret')
    op.drop_index('ix_sys_secret_company_id', table_name='sys_secret')
    op.drop_index('ix_sys_operation_log_user_id', table_name='sys_operation_log')
    op.drop_index('ix_sys_operation_log_status', table_name='sys_operation_log')
    op.drop_index('ix_sys_operation_log_resource_type', table_name='sys_operation_log')
    op.drop_index('ix_sys_operation_log_operation_type', table_name='sys_operation_log')
    op.drop_index('ix_sys_operation_log_created_at', table_name='sys_operation_log')
    op.drop_index('ix_sys_login_log_user_id', table_name='sys_login_log')
    op.drop_index('ix_sys_login_log_status', table_name='sys_login_log')
    op.drop_index('ix_sys_login_log_created_at', table_name='sys_login_log')
    op.drop_index('ix_sys_user_session_user_id', table_name='sys_user_session')
    op.drop_index('ix_sys_user_session_session_status', table_name='sys_user_session')
    op.drop_index('ix_sys_user_session_last_active_at', table_name='sys_user_session')
    op.drop_index('ix_sys_user_session_company_id', table_name='sys_user_session')
    op.drop_index('idx_session_user_status', table_name='sys_user_session')
    op.drop_index('ix_sys_user_user_name', table_name='sys_user')
    op.drop_index('ix_sys_user_status', table_name='sys_user')
    op.drop_index('ix_sys_user_role_type', table_name='sys_user')
    op.drop_index('ix_sys_user_current_session_id', table_name='sys_user')
    op.drop_index('ix_sys_user_company_id', table_name='sys_user')
    op.drop_table('sys_alert_delivery')
    op.drop_table('sys_alert_event')
    op.drop_table('sys_notification_channel')
    op.drop_table('crawler_run_log')
    op.drop_table('crawler_task_run')
    op.drop_table('crawler_task_server_target')
    op.drop_table('crawler_task_schedule')
    op.drop_table('crawler_task')
    op.drop_table('crawler_project_task_definition')
    op.drop_table('crawler_release_channel')
    op.drop_table('crawler_project_release')
    op.drop_table('crawler_image_artifact')
    op.drop_table('crawler_project_server')
    op.drop_table('crawler_project_member')
    op.drop_table('crawler_project')
    op.drop_table('crawler_discovered_project_server')
    op.drop_table('crawler_discovered_project')
    op.drop_table('crawler_company_discovery_token')
    op.drop_table('crawler_agent')
    op.drop_table('crawler_server')
    op.drop_table('crawler_company')
    op.drop_table('sys_secret')
    op.drop_table('sys_config')
    op.drop_table('sys_operation_log')
    op.drop_table('sys_login_log')
    op.drop_table('sys_user_session')
    op.drop_table('sys_user')
