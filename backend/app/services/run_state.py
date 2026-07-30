from __future__ import annotations

from dataclasses import dataclass

from app.models import CrawlerTaskRun
from app.utils import utcnow

TERMINAL_STATUSES = {
    "SUCCEEDED", "PARTIAL_SUCCESS", "SKIPPED", "FAILED", "CANCELLED", "TIMED_OUT", "LOST"
}
ACTIVE_STATUSES = {"ASSIGNED", "STARTING", "RUNNING", "CANCEL_REQUESTED"}

_TRANSITIONS = {
    "CREATED": {"QUEUED", "CANCELLED"},
    "QUEUED": {"ASSIGNED", "CANCELLED"},
    "ASSIGNED": {"STARTING", "RUNNING", "CANCEL_REQUESTED", "CANCELLED", "LOST", "FAILED"},
    "STARTING": {"RUNNING", "CANCEL_REQUESTED", "CANCELLED", "TIMED_OUT", "LOST", "FAILED"},
    "RUNNING": {"CANCEL_REQUESTED", "SUCCEEDED", "PARTIAL_SUCCESS", "SKIPPED", "FAILED", "CANCELLED", "TIMED_OUT", "LOST"},
    "CANCEL_REQUESTED": {"CANCELLED", "TIMED_OUT", "FAILED", "LOST"},
}


class InvalidRunTransition(RuntimeError):
    pass


def normalize_status(value: str) -> str:
    return {
        "CLAIMED": "ASSIGNED",
        "SUCCESS": "SUCCEEDED",
        "TIMEOUT": "TIMED_OUT",
        "RETRY_WAIT": "QUEUED",
    }.get(value, value)


def transition(run: CrawlerTaskRun, new_status: str) -> None:
    old = normalize_status(run.status)
    new = normalize_status(new_status)
    if old == new:
        run.status = new
        return
    if old in TERMINAL_STATUSES or new not in _TRANSITIONS.get(old, set()):
        raise InvalidRunTransition(f"不允许的运行状态变化：{old} -> {new}")
    now = utcnow()
    run.status = new
    if new == "QUEUED":
        run.queued_at = run.queued_at or now
    elif new == "ASSIGNED":
        run.assigned_at = now
    elif new == "STARTING":
        run.starting_at = now
    elif new == "RUNNING":
        run.started_at = run.started_at or now
    elif new == "CANCEL_REQUESTED":
        run.cancel_requested_at = now
    elif new == "LOST":
        run.lost_at = now
        run.finished_at = now
    elif new in TERMINAL_STATUSES:
        run.finished_at = now
    if run.finished_at and run.started_at:
        run.duration_ms = max(0, int((run.finished_at - run.started_at).total_seconds() * 1000))
