from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from datetime import timedelta
from pathlib import Path

DB_PATH = Path(tempfile.gettempdir()) / "crawler_platform_v2_tests.db"
LOG_ROOT = Path(tempfile.gettempdir()) / "crawler_platform_v2_test_logs"
DB_PATH.unlink(missing_ok=True)
if LOG_ROOT.exists():
    import shutil
    shutil.rmtree(LOG_ROOT)
os.environ.update({
    "APP_ENV": "test",
    "DATABASE_URL": f"sqlite:///{DB_PATH}",
    "TASK_LOG_ROOT": str(LOG_ROOT),
    "ADMIN_PASSWORD": "TestAdmin123!",
    "CICD_TOKEN": "test-cicd",
    "AGENT_BOOTSTRAP_TOKEN": "test-agent",
    "JWT_SECRET": "test-jwt-secret-which-is-long-enough",
    "SECRET_ENCRYPTION_KEY": "test-secret-encryption-key",
})

# Offline CI environments may not have croniter installed. The business tests
# below use MANUAL schedules, so a tiny compatible shim is sufficient.
try:
    import croniter as _croniter  # noqa: F401
except ModuleNotFoundError:
    class _FakeCron:
        @classmethod
        def is_valid(cls, expression: str) -> bool:
            return bool(expression)

        def __init__(self, expression, start_time):
            self.start_time = start_time

        def get_next(self, _type):
            return self.start_time + timedelta(minutes=1)

    module = types.ModuleType("croniter")
    module.croniter = _FakeCron
    sys.modules["croniter"] = module

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import (
    CrawlerCompany,
    CrawlerProject,
    CrawlerProjectMember,
    CrawlerProjectResourceBinding,
    CrawlerProjectSecretBinding,
    CrawlerResourceConnection,
    CrawlerResourceDatabase,
    CrawlerResourceObject,
    SysSecret,
)
from app.security import encrypt_secret
from app.services.resource_manifest import build_resource_files, resolve_manifest_secrets
from app.services.run_state import InvalidRunTransition, transition


MANIFEST = {
    "schema_version": "1.0",
    "app_name": "crawler_platform_spiders",
    "version": "1.0.0",
    "build_sha": "test",
    "entries": [{
        "task_name": "system.health",
        "description": "health",
        "image_profile": "api",
        "default_timeout_seconds": 60,
        "required_resources": [],
        "parameter_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    }],
}


class PlatformV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()
        login = cls.client.post("/api/auth/login", json={"user_name": "admin", "password": "TestAdmin123!"})
        assert login.status_code == 200, login.text
        cls.user_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        cls.company_id = cls.client.get("/api/companies", headers=cls.user_headers).json()[0]["company_id"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def _ok(self, response, expected: int = 200):
        self.assertEqual(response.status_code, expected, response.text)
        return response.json() if response.content else None

    def test_01_agent_run_error_and_finish_contract(self) -> None:
        digest = "sha256:" + "a" * 64
        release = self._ok(self.client.post(
            "/api/cicd/spider-releases",
            headers={"X-CICD-Token": "test-cicd"},
            json={
                "image_repository": "registry.example.com/crawler_platform_spiders",
                "image_tag": "1.0.0",
                "image_digest": digest,
                "git_commit": "abc123",
                "manifest": MANIFEST,
            },
        ))
        project = self._ok(self.client.post("/api/projects", headers=self.user_headers, json={
            "company_id": self.company_id,
            "project_code": "contract-project",
            "project_name": "Contract Project",
            "registry": "",
            "repository": "",
            "default_branch": "main",
            "status": "ENABLED",
            "description": "",
        }))
        project_id = project["project_id"]
        self._ok(self.client.put(
            f"/api/projects/{project_id}/channels/stable",
            headers=self.user_headers,
            json={"spider_release_id": release["release_id"]},
        ))
        agent = self._ok(self.client.post(
            "/api/agent/v2/register",
            headers={"X-Agent-Bootstrap-Token": "test-agent"},
            json={
                "protocol_version": "2.0",
                "instance_id": "test-instance",
                "agent_code": "test-agent",
                "server_code": "test-server",
                "server_name": "Test Server",
                "hostname": "localhost",
                "agent_version": "2.0.0",
                "os_name": "linux",
                "python_version": "3.12",
                "docker_version": "27",
                "cpu_count": 4,
                "memory_total_bytes": 1024,
                "capabilities": ["api"],
                "labels": {"region": "test"},
                "max_container_slots": 2,
            },
        ))
        agent_headers = {"Authorization": f"Agent {agent['agent_token']}"}
        task = self._ok(self.client.post("/api/tasks", headers=self.user_headers, json={
            "task_code": "contract-health",
            "task_name": "Contract Health",
            "project_id": project_id,
            "spider_task_name": "system.health",
            "platform": "system",
            "task_group": "default",
            "developer": "tests",
            "parameters": {},
            "status": "ENABLED",
            "description": "",
            "runtime": {
                "image_policy": "RELEASE_CHANNEL",
                "release_channel": "stable",
                "pull_policy": "IF_NOT_PRESENT",
                "cpu_limit": 1,
                "memory_limit_mb": 256,
                "shm_size_mb": 64,
                "pids_limit": 128,
                "stop_grace_seconds": 10,
                "auto_remove": True,
                "keep_failed_container": False,
            },
            "schedule": {
                "schedule_type": "MANUAL",
                "cron_expression": "",
                "timezone": "Asia/Shanghai",
                "misfire_policy": "FIRE_ONCE",
                "max_concurrency": 1,
                "overlap_policy": "SKIP",
                "timeout_seconds": 60,
                "max_retry_count": 1,
                "retry_interval_seconds": 60,
                "retry_backoff": "FIXED",
                "enabled": False,
            },
            "server_ids": [agent["server_id"]],
        }))
        run = self._ok(self.client.post(f"/api/tasks/{task['task_id']}/run", headers=self.user_headers))
        run_id = run["run_id"]
        claim = self._ok(self.client.post("/api/agent/v2/claim", headers=agent_headers, json={"available_slots": 1}))["items"][0]
        self.assertEqual(claim["run_id"], run_id)
        self.assertEqual(claim["files"]["task"]["task_name"], "system.health")
        self.assertEqual(claim["image"]["ref"], f"registry.example.com/crawler_platform_spiders@{digest}")
        lease_headers = {**agent_headers, "X-Run-Lease-Token": claim["lease_token"]}
        self._ok(self.client.post(f"/api/agent/v2/runs/{run_id}/starting", headers=lease_headers, json={"message": "starting"}))
        self._ok(self.client.post(f"/api/agent/v2/runs/{run_id}/started", headers=lease_headers, json={"container_id": "cid", "container_name": "cname"}))

        first = self._ok(self.client.post(
            f"/api/agent/v2/runs/{run_id}/logs",
            headers=lease_headers,
            json={"stream": "stdout", "start_seq": 1, "lines": ["line-1", "line-2"]},
        ))
        duplicate = self._ok(self.client.post(
            f"/api/agent/v2/runs/{run_id}/logs",
            headers=lease_headers,
            json={"stream": "stdout", "start_seq": 1, "lines": ["line-1", "line-2"]},
        ))
        self.assertEqual(first["ack_seq"], 2)
        self.assertEqual(duplicate["ack_seq"], 2)

        event = {
            "event_uid": "evt-login-failed",
            "stream": "stdout",
            "seq": 2,
            "level": "ERROR",
            "event_name": "login_failed",
            "message": "账号登录失败",
            "error_code": "TEST.LOGIN_FAILED",
            "error_type": "AuthenticationError",
            "retryable": False,
            "context": {"token": "must-be-redacted", "account_id": "a1"},
            "payload": {"schema": "crawler.event.v1"},
            "occurred_at": "2026-07-30T01:02:03Z",
        }
        accepted = self._ok(self.client.post(f"/api/agent/v2/runs/{run_id}/events", headers=lease_headers, json={"events": [event]}))
        repeated = self._ok(self.client.post(f"/api/agent/v2/runs/{run_id}/events", headers=lease_headers, json={"events": [event]}))
        self.assertEqual(accepted["accepted_count"], 1)
        self.assertEqual(repeated["accepted_count"], 0)
        detail = self._ok(self.client.get(f"/api/runs/{run_id}", headers=self.user_headers))
        self.assertEqual(detail["last_error"]["code"], "TEST.LOGIN_FAILED")

        finish = self._ok(self.client.post(f"/api/agent/v2/runs/{run_id}/finish", headers=lease_headers, json={
            "status": "FAILED",
            "exit_code": 1,
            "oom_killed": False,
            "result": {"status": "failed", "metrics": {"records": 3}},
            "last_error": {"code": "TEST.LOGIN_FAILED", "type": "AuthenticationError", "message": "账号登录失败", "retryable": False},
            "terminal_error": {"code": "TEST.LOGIN_FAILED", "type": "AuthenticationError", "message": "账号登录失败", "retryable": False},
            "inspect_summary": {"status": "exited"},
        }))
        self.assertEqual(finish["status"], "FAILED")
        detail = self._ok(self.client.get(f"/api/runs/{run_id}", headers=self.user_headers))
        self.assertEqual(detail["terminal_error"]["code"], "TEST.LOGIN_FAILED")
        self.assertEqual(detail["metrics"], {"records": 3})

    def test_02_minimum_multi_database_resource_manifest(self) -> None:
        with SessionLocal() as db:
            company = db.get(CrawlerCompany, self.company_id)
            project = CrawlerProject(
                company_id=company.company_id,
                project_code="resource-project",
                project_name="Resource Project",
                registry="",
                repository="",
                status="ENABLED",
            )
            db.add(project)
            db.flush()
            admin_id = db.scalar(select(CrawlerProjectMember.user_id).limit(1))
            db.add(CrawlerProjectMember(project_id=project.project_id, user_id=admin_id, role="OWNER"))

            secrets = {}
            for code, value in {
                "mysql.resource.password": "mysql-password",
                "mongo.resource.uri": "mongodb://resource",
                "redis.resource.password": "redis-password",
                "unused.password": "unused",
            }.items():
                row = SysSecret(
                    company_id=company.company_id,
                    project_id=project.project_id,
                    secret_code=code,
                    secret_name=code,
                    encrypted_value=encrypt_secret(value),
                    enabled=True,
                )
                db.add(row)
                db.flush()
                db.add(CrawlerProjectSecretBinding(project_id=project.project_id, logical_name=code, secret_id=row.secret_id))
                secrets[code] = row

            mysql = CrawlerResourceConnection(
                company_id=company.company_id,
                project_id=project.project_id,
                connection_code="mysql-main",
                connection_name="MySQL Main",
                resource_type="MYSQL",
                config_json={"host": "mysql.internal", "port": 3306, "username": "crawler", "password_secret": "mysql.resource.password"},
            )
            mongo = CrawlerResourceConnection(
                company_id=company.company_id,
                project_id=project.project_id,
                connection_code="mongo-main",
                connection_name="Mongo Main",
                resource_type="MONGO",
                config_json={"uri_secret": "mongo.resource.uri"},
            )
            redis = CrawlerResourceConnection(
                company_id=company.company_id,
                project_id=project.project_id,
                connection_code="redis-cache",
                connection_name="Redis Cache",
                resource_type="REDIS",
                config_json={"host": "redis.internal", "port": 6379, "database": 3, "password_secret": "redis.resource.password"},
            )
            unused = CrawlerResourceConnection(
                company_id=company.company_id,
                project_id=project.project_id,
                connection_code="mysql-unused",
                connection_name="Unused MySQL",
                resource_type="MYSQL",
                config_json={"host": "unused.internal", "port": 3306, "username": "crawler", "password_secret": "unused.password"},
            )
            db.add_all([mysql, mongo, redis, unused])
            db.flush()
            mysql_db = CrawlerResourceDatabase(connection_id=mysql.connection_id, database_code="market", database_name="market_db", config_json={})
            mongo_db = CrawlerResourceDatabase(connection_id=mongo.connection_id, database_code="quotation", database_name="Quotation", config_json={})
            db.add_all([mysql_db, mongo_db])
            db.flush()
            mysql_table = CrawlerResourceObject(database_id=mysql_db.database_id, object_code="product", object_name="product_detail", object_type="TABLE")
            mongo_collection = CrawlerResourceObject(database_id=mongo_db.database_id, object_code="categories", object_name="categories", object_type="COLLECTION")
            db.add_all([mysql_table, mongo_collection])
            db.flush()
            db.add_all([
                CrawlerProjectResourceBinding(project_id=project.project_id, logical_name="market.product_detail", resource_kind="OBJECT", object_id=mysql_table.object_id),
                CrawlerProjectResourceBinding(project_id=project.project_id, logical_name="quotation.categories", resource_kind="OBJECT", object_id=mongo_collection.object_id),
                CrawlerProjectResourceBinding(project_id=project.project_id, logical_name="cache", resource_kind="CONNECTION", connection_id=redis.connection_id),
            ])
            db.commit()

            manifest, plaintext = build_resource_files(
                db,
                company_id=company.company_id,
                project_id=project.project_id,
                required_resources=["market.product_detail", "quotation.categories", "cache"],
            )
            self.assertEqual(len(manifest["mysql"]["connections"]), 1)
            self.assertEqual(len(manifest["mongo"]["connections"]), 1)
            self.assertEqual(len(manifest["redis"]["connections"]), 1)
            self.assertNotIn("unused.internal", json.dumps(manifest))
            self.assertEqual(plaintext["mysql.resource.password"], "mysql-password")
            self.assertEqual(resolve_manifest_secrets(db, project.project_id, manifest), {
                "mysql.resource.password": "mysql-password",
                "mongo.resource.uri": "mongodb://resource",
                "redis.resource.password": "redis-password",
            })

    def test_03_terminal_state_is_immutable(self) -> None:
        class Run:
            status = "RUNNING"
            assigned_at = starting_at = started_at = cancel_requested_at = finished_at = lost_at = duration_ms = None

        run = Run()
        transition(run, "FAILED")
        self.assertEqual(run.status, "FAILED")
        with self.assertRaises(InvalidRunTransition):
            transition(run, "RUNNING")


if __name__ == "__main__":
    unittest.main(verbosity=2)
