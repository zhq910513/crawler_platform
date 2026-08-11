from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import text

from app.api import routers
from app.config import settings
from app.db import SessionLocal
from app.errors import AppError
from app.models import SysUser
from app.security import decode_access_token
from app.services.audit import write_operation_log
from app.responses import ok
from app.utils import api_data

settings.validate_runtime()

HIGH_FREQUENCY_AUDIT_PREFIXES = (
    "/agent-heartbeats",
    "/agent-run-claims",
    "/agent-image-pull-results",
    "/agent-run-heartbeats",
    "/agent-run-results",
    "/agent-run-events",
    "/agent-run-log-chunks",
    "/agent-run-log-finalizations",
    "/agent-container-snapshots",
    "/agent-account-status-events",
)


def should_write_operation_audit(path: str, method: str) -> bool:
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return False
    if not path.startswith(settings.api_prefix):
        return False
    relative = path.replace(settings.api_prefix, "", 1) or "/"
    return not relative.startswith(HIGH_FREQUENCY_AUDIT_PREFIXES)


app = FastAPI(
    title="爬虫管理平台",
    version=settings.app_version,
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
)



@app.middleware("http")
async def operation_audit_middleware(request: Request, call_next):
    response = await call_next(request)
    if should_write_operation_audit(request.url.path, request.method):
        try:
            auth = request.headers.get("authorization", "")
            user = None
            with SessionLocal() as db:
                if auth.startswith("Bearer "):
                    try:
                        payload = decode_access_token(auth[7:].strip())
                        user = db.get(SysUser, int(payload.get("sub")))
                    except Exception:
                        user = None
                write_operation_log(
                    db,
                    user,
                    request,
                    operation_type=request.method,
                    resource_type=request.url.path.replace(settings.api_prefix, "", 1).strip("/").split("/")[0] or "unknown",
                    resource_id="",
                    status="SUCCESS" if response.status_code < 400 else "FAILED",
                    error_message="" if response.status_code < 400 else f"HTTP {response.status_code}",
                )
                db.commit()
        except Exception:
            pass
    return response


if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.http_status, content={"code": exc.code, "message": exc.message, "data": api_data(exc.data)})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"code": 40001, "message": "请求参数不合法", "data": exc.errors()})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code = exc.status_code if exc.status_code in {400, 401, 403, 404, 500} else 400
    return JSONResponse(status_code=code, content={"code": code, "message": str(exc.detail), "data": None})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"code": 50000, "message": "服务器内部错误", "data": None})


def _read_migration_version() -> str:
    try:
        with SessionLocal() as db:
            value = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
            return str(value or "unknown")
    except Exception:
        return "unknown"


@app.get("/health")
def health():
    return ok({
        "status": "ok",
        "appName": settings.app_name,
        "version": settings.app_version,
        "gitCommit": settings.app_git_commit,
        "buildTime": settings.app_build_time,
        "migrationVersion": _read_migration_version(),
    })


for router in routers:
    app.include_router(router, prefix=settings.api_prefix)
