from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError
from app.models import SysConfig, SysUser
from app.services.audit import write_operation_log
from app.services.permissions import require_super_admin
from app.utils import utcnow

_ACTION_LOCK = threading.Lock()
_ACTION_STATE: dict[str, Any] = {
    "running": False,
    "actionKey": "",
    "stage": "IDLE",
    "status": "IDLE",
    "startedAt": "",
    "finishedAt": "",
    "triggeredBy": "",
    "logs": [],
    "manualCommand": "bash deploy/scripts/prepare-agent-image.sh",
}


class PlatformActionService:
    def __init__(self, db: Session):
        self.db = db

    def get_status(self, user: SysUser) -> dict:
        require_super_admin(user)
        return self._state_payload()

    def prepare_agent_image(self, user: SysUser) -> dict:
        require_super_admin(user)
        action_key = "prepare_agent_image"
        manual_command = "bash deploy/scripts/prepare-agent-image.sh"
        capability = self._inspect_prepare_agent_image_capability()
        if not capability["available"]:
            result = {
                "actionKey": action_key,
                "status": "UNAVAILABLE",
                "stage": "能力检查",
                "message": capability["message"],
                "logs": capability["logs"],
                "manualCommand": manual_command,
                "executable": False,
            }
            write_operation_log(self.db, user, None, operation_type="PLATFORM_ACTION_UNAVAILABLE", resource_type="platform_action", resource_id=action_key, after_data=result, status="FAILED", error_message=capability["message"])
            self.db.commit()
            return result

        db_lock_acquired = self._acquire_db_action_lock(action_key, user)
        if not _ACTION_LOCK.acquire(blocking=False):
            if db_lock_acquired:
                self._release_db_action_lock(action_key)
            raise AppError("已有平台自动化动作正在执行，请等待完成后再试", code=40901, http_status=409)
        started_at = utcnow().isoformat()
        try:
            _ACTION_STATE.update({
                "running": True,
                "actionKey": action_key,
                "stage": "开始执行",
                "status": "RUNNING",
                "startedAt": started_at,
                "finishedAt": "",
                "triggeredBy": user.user_name,
                "logs": ["[STEP] 开始执行平台白名单动作：准备执行组件镜像"],
                "manualCommand": manual_command,
            })
            root = Path(settings.platform_action_root).resolve()
            script = root / "deploy" / "scripts" / "prepare-agent-image.sh"
            command = ["bash", str(script)]
            env = os.environ.copy()
            env.setdefault("CRAWLER_PLATFORM_ACTION_RUN_ID", started_at)
            proc = subprocess.run(command, cwd=str(root), env=env, text=True, capture_output=True, timeout=max(60, int(settings.platform_action_timeout_seconds)))
            output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
            logs = [line for line in output.splitlines() if line.strip()]
            stage = self._detect_stage(logs)
            status_text = "SUCCESS" if proc.returncode == 0 else "FAILED"
            finished_at = utcnow().isoformat()
            result = {
                "actionKey": action_key,
                "status": status_text,
                "stage": stage,
                "message": "执行组件镜像已自动准备完成。" if proc.returncode == 0 else f"执行组件镜像自动准备失败，退出码 {proc.returncode}。",
                "logs": logs[-120:],
                "manualCommand": manual_command,
                "startedAt": started_at,
                "finishedAt": finished_at,
                "executable": True,
            }
            _ACTION_STATE.update({**result, "running": False, "triggeredBy": user.user_name})
            write_operation_log(self.db, user, None, operation_type="PLATFORM_ACTION_PREPARE_AGENT_IMAGE", resource_type="platform_action", resource_id=action_key, before_data={"capability": capability}, after_data=result, status="SUCCESS" if proc.returncode == 0 else "FAILED", error_message="" if proc.returncode == 0 else result["message"])
            self.db.commit()
            if proc.returncode != 0:
                raise AppError(result["message"], code=50058, http_status=500, data=result)
            return result
        except subprocess.TimeoutExpired as exc:
            finished_at = utcnow().isoformat()
            logs = []
            if exc.stdout:
                logs.extend(str(exc.stdout).splitlines())
            if exc.stderr:
                logs.extend(str(exc.stderr).splitlines())
            result = {
                "actionKey": action_key,
                "status": "FAILED",
                "stage": "执行超时",
                "message": f"执行组件镜像自动准备超时，已超过 {settings.platform_action_timeout_seconds} 秒。",
                "logs": logs[-120:],
                "manualCommand": manual_command,
                "startedAt": started_at,
                "finishedAt": finished_at,
                "executable": True,
            }
            _ACTION_STATE.update({**result, "running": False, "triggeredBy": user.user_name})
            write_operation_log(self.db, user, None, operation_type="PLATFORM_ACTION_PREPARE_AGENT_IMAGE", resource_type="platform_action", resource_id=action_key, after_data=result, status="FAILED", error_message=result["message"])
            self.db.commit()
            raise AppError(result["message"], code=50059, http_status=500, data=result)
        finally:
            if _ACTION_LOCK.locked():
                _ACTION_LOCK.release()
            self._release_db_action_lock(action_key)

    def _acquire_db_action_lock(self, action_key: str, user: SysUser) -> bool:
        lock_key = f"platform_action.{action_key}.lock"
        row = self.db.query(SysConfig).filter(SysConfig.config_key == lock_key).one_or_none()
        now = utcnow()
        if row and row.config_value:
            parts = str(row.config_value).split(":", 2)
            locked_at = parts[1] if len(parts) > 1 else ""
            try:
                locked_dt = datetime.fromisoformat(locked_at.replace("Z", "+00:00"))
                if locked_dt.tzinfo is not None:
                    locked_dt = locked_dt.astimezone(timezone.utc).replace(tzinfo=None)
                age_seconds = (now - locked_dt).total_seconds()
            except Exception:
                age_seconds = 0
            if age_seconds < max(60, int(settings.platform_action_timeout_seconds)):
                raise AppError("已有平台自动化动作正在执行，请等待完成后再试", code=40901, http_status=409)
        value = f"running:{now.isoformat()}:{user.user_name}"
        if not row:
            row = SysConfig(config_key=lock_key, config_name="平台动作锁", config_value=value, description="平台白名单自动化动作执行锁")
            self.db.add(row)
        else:
            row.config_value = value
            row.description = "平台白名单自动化动作执行锁"
        self.db.commit()
        return True

    def _release_db_action_lock(self, action_key: str) -> None:
        lock_key = f"platform_action.{action_key}.lock"
        row = self.db.query(SysConfig).filter(SysConfig.config_key == lock_key).one_or_none()
        if row and row.config_value:
            row.config_value = ""
            self.db.commit()

    def _inspect_prepare_agent_image_capability(self) -> dict:
        logs: list[str] = []
        if not settings.platform_action_enabled:
            return {
                "available": False,
                "message": "当前部署未启用平台白名单动作执行能力。请在平台服务器执行手动命令，或在确认安全边界后配置 CRAWLER_PLATFORM_ACTIONS_ENABLED=1 并挂载项目目录与 Docker 权限。",
                "logs": ["CRAWLER_PLATFORM_ACTIONS_ENABLED 未启用"],
            }
        root = Path(settings.platform_action_root).resolve()
        script = root / "deploy" / "scripts" / "prepare-agent-image.sh"
        if not script.exists():
            return {"available": False, "message": f"平台动作脚本不存在：{script}", "logs": [f"root={root}", f"script={script}"]}
        if not os.access(script, os.R_OK):
            return {"available": False, "message": f"平台动作脚本不可读：{script}", "logs": [str(script)]}
        try:
            subprocess.run(["docker", "version"], cwd=str(root), text=True, capture_output=True, timeout=15, check=True)
        except Exception as exc:
            return {"available": False, "message": "当前后端运行环境无法访问 Docker，不能在页面一键准备执行组件镜像。请在平台服务器执行手动命令。", "logs": [repr(exc)]}
        return {"available": True, "message": "平台白名单动作可执行。", "logs": logs}

    @staticmethod
    def _detect_stage(logs: list[str]) -> str:
        joined = "\n".join(logs[-80:])
        if "重启 API" in joined or "重启后端" in joined:
            return "重启后端服务"
        if "CRAWLER_AGENT_IMAGE" in joined or ".env 已更新" in joined:
            return "写入平台配置"
        if "docker push" in joined or "推送执行组件镜像" in joined:
            return "推送执行组件镜像"
        if "构建执行组件镜像" in joined or "docker build" in joined:
            return "构建执行组件镜像"
        if "registry" in joined:
            return "检查内置镜像仓库"
        return "执行平台动作"

    @staticmethod
    def _state_payload() -> dict:
        return dict(_ACTION_STATE)
