from __future__ import annotations

from fastapi import status

from app.errors import AppError
from app.models import CrawlerTaskRun

RUN_TERMINAL = {"SUCCEEDED", "PARTIAL_SUCCESS", "SKIPPED", "FAILED", "CANCELLED", "TIMED_OUT", "LOST"}
RUN_TRANSITIONS = {
    "CREATED": {"QUEUED", "CANCELLED"},
    "QUEUED": {"ASSIGNED", "SKIPPED", "CANCELLED", "FAILED", "LOST"},
    "ASSIGNED": {"STARTING", "RUNNING", "CANCEL_REQUESTED", "FAILED", "LOST"},
    "STARTING": {"RUNNING", "SUCCEEDED", "PARTIAL_SUCCESS", "CANCEL_REQUESTED", "CANCELLED", "FAILED", "TIMED_OUT", "LOST"},
    "RUNNING": {"SUCCEEDED", "PARTIAL_SUCCESS", "FAILED", "TIMED_OUT", "LOST", "CANCEL_REQUESTED", "CANCELLED"},
    "CANCEL_REQUESTED": {"CANCELLED", "FAILED", "TIMED_OUT", "LOST"},
}
ROUTING_TRANSITIONS = {
    "PENDING": {"WAITING_RESOURCE", "WARMING_IMAGE", "ROUTED", "ROUTE_FAILED", "ROUTE_CANCELLED"},
    "WAITING_RESOURCE": {"WARMING_IMAGE", "ROUTED", "ROUTE_FAILED", "ROUTE_CANCELLED", "PENDING"},
    "WARMING_IMAGE": {"ROUTED", "WAITING_RESOURCE", "ROUTE_FAILED"},
    "ROUTED": {"PENDING", "ROUTE_CANCELLED"},
    "ROUTE_FAILED": set(),
    "ROUTE_CANCELLED": set(),
}


def set_run_status(run: CrawlerTaskRun, next_status: str, *, message: str = "") -> None:
    current = run.run_status
    if current in RUN_TERMINAL:
        raise AppError("终态运行实例不可再次变更", code=40070, http_status=status.HTTP_400_BAD_REQUEST)
    if next_status != current and next_status not in RUN_TRANSITIONS.get(current, set()):
        raise AppError(f"运行状态不允许从 {current} 变更为 {next_status}", code=40071, http_status=status.HTTP_400_BAD_REQUEST)
    run.run_status = next_status
    if message:
        run.error_message = message


def safe_set_run_status(run: CrawlerTaskRun, next_status: str, *, message: str = "") -> bool:
    if run.run_status in RUN_TERMINAL:
        return False
    if next_status == run.run_status or next_status in RUN_TRANSITIONS.get(run.run_status, set()):
        run.run_status = next_status
        if message:
            run.error_message = message
        return True
    return False


def set_routing_status(run: CrawlerTaskRun, next_status: str, *, reason: str = "") -> None:
    current = run.routing_status
    if next_status != current and next_status not in ROUTING_TRANSITIONS.get(current, set()):
        # 路由会被调度器多次修正，允许 WAITING_RESOURCE/PENDING 之间互相恢复。
        if {current, next_status} <= {"PENDING", "WAITING_RESOURCE", "ROUTED"}:
            pass
        else:
            raise AppError(f"路由状态不允许从 {current} 变更为 {next_status}", code=40072, http_status=status.HTTP_400_BAD_REQUEST)
    run.routing_status = next_status
    run.routing_reason = reason


def set_synthetic_parent_terminal(run: CrawlerTaskRun, next_status: str, *, message: str = "") -> None:
    if next_status not in RUN_TERMINAL:
        raise AppError("父运行只能聚合为终态", code=40073, http_status=status.HTTP_400_BAD_REQUEST)
    if run.run_status in RUN_TERMINAL:
        return
    run.run_status = next_status
    if message:
        run.error_message = message
