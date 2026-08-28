from __future__ import annotations

import os
from datetime import datetime
from uuid import uuid4

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:////tmp/crawler_platform_pytest.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "Admin@123456")
os.environ.setdefault("JWT_SECRET", "pytest-jwt-secret-for-crawler-platform-1-0-9")
os.environ.setdefault("SECRET_ENCRYPTION_KEY", "pytest-secret-encryption-key-for-crawler-platform-1-0-9")

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.migration_main import main as migrate
from app.models import CrawlerCompany, CrawlerProject, CrawlerProjectMember, CrawlerProjectServer, CrawlerServer, CrawlerTask, CrawlerTaskRun, CrawlerTaskSchedule, CrawlerTaskServerTarget, SysUser
from app.security import hash_password


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/sessions", json={"userName": "admin", "password": "Admin@123456"})
    if response.json()["code"] == 40901:
        response = client.post("/api/v1/sessions", json={"userName": "admin", "password": "Admin@123456", "forceLoginToken": response.json()["data"]["forceLoginToken"]})
    return {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}


def _normal_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/sessions", json={"userName": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}


def test_task_schedule_panel_aggregation_filters_and_scope() -> None:
    migrate()
    suffix = uuid4().hex[:8]
    normal_username = f"panel_user_{suffix}"
    normal_password = "Panel@123456"

    with SessionLocal() as db:
        company_a = CrawlerCompany(company_code=f"panel_a_{suffix}", company_name="面板公司A")
        company_b = CrawlerCompany(company_code=f"panel_b_{suffix}", company_name="面板公司B")
        db.add_all([company_a, company_b])
        db.flush()
        owner = SysUser(company_id=company_a.company_id, user_name=normal_username, nick_name="面板负责人", password_hash=hash_password(normal_password), role_type="NORMAL_USER", status="ENABLED", must_change_password=False)
        db.add(owner)
        db.flush()
        project_a = CrawlerProject(company_id=company_a.company_id, project_key=f"panel-project-a-{suffix}", project_code=f"panel_a_{suffix}", project_name="面板项目A", image_repository="repo/panel-a")
        project_b = CrawlerProject(company_id=company_b.company_id, project_key=f"panel-project-b-{suffix}", project_code=f"panel_b_{suffix}", project_name="面板项目B", image_repository="repo/panel-b")
        db.add_all([project_a, project_b])
        db.flush()
        db.add(CrawlerProjectMember(project_id=project_a.project_id, user_id=owner.user_id, role="OPERATOR"))
        server_a = CrawlerServer(company_id=company_a.company_id, server_code=f"panel-srv-a-{suffix}", server_name="面板服务器A", server_ip="10.0.0.8", manage_status="ENABLED")
        db.add(server_a)
        db.flush()
        db.add(CrawlerProjectServer(company_id=company_a.company_id, project_id=project_a.project_id, server_id=server_a.server_id, deployment_status="DEPLOYED", scheduling_status="ENABLED"))
        task_a = CrawlerTask(company_id=company_a.company_id, project_id=project_a.project_id, owner_user_id=owner.user_id, task_code=f"panel_task_a_{suffix}", task_name="面板采集任务", entry_module="spiders.panel.collector", entry_function="run", task_group="browser", status="ENABLED")
        task_b = CrawlerTask(company_id=company_b.company_id, project_id=project_b.project_id, task_code=f"panel_task_b_{suffix}", task_name="其他公司任务", entry_module="spiders.other", entry_function="run", status="ENABLED")
        task_without_schedule = CrawlerTask(company_id=company_a.company_id, project_id=project_a.project_id, task_code=f"panel_task_none_{suffix}", task_name="未配置调度任务", entry_module="spiders.panel.manual", entry_function="run", task_group="manual", status="ENABLED")
        db.add_all([task_a, task_b, task_without_schedule])
        db.flush()
        schedule_a = CrawlerTaskSchedule(company_id=company_a.company_id, project_id=project_a.project_id, task_id=task_a.task_id, schedule_status="ENABLED", schedule_type="CRON", cron_expression="10 3 * * *", schedule_timezone="Asia/Singapore", schedule_label="每天 03:10 执行", next_run_at=datetime(2026, 8, 5, 3, 10))
        schedule_b = CrawlerTaskSchedule(company_id=company_b.company_id, project_id=project_b.project_id, task_id=task_b.task_id, schedule_status="PAUSED", schedule_type="MANUAL")
        db.add_all([schedule_a, schedule_b])
        db.flush()
        db.add(CrawlerTaskServerTarget(company_id=company_a.company_id, task_id=task_a.task_id, server_id=server_a.server_id, priority=1, enabled=True))
        run = CrawlerTaskRun(company_id=company_a.company_id, project_id=project_a.project_id, task_id=task_a.task_id, schedule_id=schedule_a.schedule_id, server_id=server_a.server_id, run_status="SUCCEEDED", routing_status="ROUTED", finished_at=datetime(2026, 8, 4, 3, 10, 28), error_summary="")
        db.add(run)
        db.commit()
        company_a_id = company_a.company_id
        company_b_id = company_b.company_id
        project_a_id = project_a.project_id
        task_a_id = task_a.task_id
        task_without_schedule_id = task_without_schedule.task_id
        run_id = run.run_id
        server_a_id = server_a.server_id

    client = TestClient(app)
    admin_headers = _admin_headers(client)
    response = client.get(
        "/api/v1/task-schedule-panels",
        headers=admin_headers,
        params={"companyId": company_a_id, "projectId": project_a_id, "taskName": "面板采集", "entryKeyword": "collector", "serverId": server_a_id, "lastRunStatus": "SUCCEEDED", "page": 1, "pageSize": 20},
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"code", "message", "data"}
    assert set(body["data"]) == {"items", "total", "page", "pageSize", "pendingDefinitions", "pendingDefinitionTotal", "ignoredDefinitions", "ignoredDefinitionTotal"}
    assert body["data"]["pendingDefinitionTotal"] == 0
    assert body["data"]["pendingDefinitions"] == []
    assert body["data"]["ignoredDefinitionTotal"] == 0
    assert body["data"]["ignoredDefinitions"] == []
    assert body["data"]["total"] == 1
    item = body["data"]["items"][0]
    assert item["taskId"] == task_a_id
    assert item["companyName"] == "面板公司A"
    assert item["projectName"] == "面板项目A"
    assert item["entryPath"] == "spiders.panel.collector:run"
    assert item["taskPlatform"] == "browser"
    assert item["serverName"] == "面板服务器A"
    assert item["ownerUserName"] == "面板负责人"
    assert item["scheduleStatus"] == "ENABLED"
    assert item["lastRunId"] == run_id
    assert item["lastRunStatus"] == "SUCCEEDED"

    not_scheduled = client.get(
        "/api/v1/task-schedule-panels",
        headers=admin_headers,
        params={"companyId": company_a_id, "scheduleStatus": "NONE", "lastRunStatus": "NOT_RUN"},
    )
    assert not_scheduled.status_code == 200
    assert not_scheduled.json()["data"]["total"] == 1
    not_scheduled_item = not_scheduled.json()["data"]["items"][0]
    assert not_scheduled_item["taskId"] == task_without_schedule_id
    assert not_scheduled_item["scheduleStatus"] == "NONE"
    assert not_scheduled_item["lastRunStatus"] == "NOT_RUN"

    normal_headers = _normal_headers(client, normal_username, normal_password)
    normal_response = client.get("/api/v1/task-schedule-panels", headers=normal_headers)
    assert normal_response.status_code == 200
    normal_items = normal_response.json()["data"]["items"]
    assert {row["companyId"] for row in normal_items} == {company_a_id}
    assert task_a_id in {row["taskId"] for row in normal_items}

    cross_company = client.get("/api/v1/task-schedule-panels", headers=normal_headers, params={"companyId": company_b_id})
    assert cross_company.status_code == 404
