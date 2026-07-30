from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.encoders import ENCODERS_BY_TYPE
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent, auth, companies, dashboard, operations, projects, releases, resources, runs, servers, settings_api, tasks, users
from app.config import settings
from app.init_db import init_db

ENCODERS_BY_TYPE[datetime] = lambda value: (
    value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_runtime()
    init_db()
    settings.task_log_root.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=settings.cors_origin_list != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.app_name, "version": settings.app_version, "protocol": "agent-v2"}


for router in (
    auth.router,
    users.router,
    companies.router,
    projects.router,
    tasks.router,
    runs.router,
    servers.router,
    releases.router,
    releases.cicd_router,
    resources.router,
    settings_api.router,
    operations.router,
    dashboard.router,
    agent.router,
):
    app.include_router(router, prefix=settings.api_prefix)
