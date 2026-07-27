from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from croniter import croniter


def normalize_cron(expression: str) -> tuple[str, bool]:
    parts = expression.strip().replace("?", "*").split()
    if len(parts) == 5:
        return " ".join(parts), False
    if len(parts) == 6:
        return " ".join(parts), True
    raise ValueError("Cron 表达式仅支持 5 位或 6 位格式")


def next_run_utc(expression: str, timezone_name: str, base_utc: datetime | None = None) -> datetime:
    expression, second_at_beginning = normalize_cron(expression)
    zone = ZoneInfo(timezone_name)
    base_utc = base_utc or datetime.now(timezone.utc).replace(tzinfo=None)
    local_base = base_utc.replace(tzinfo=timezone.utc).astimezone(zone)
    value = croniter(expression, local_base, second_at_beginning=second_at_beginning).get_next(datetime)
    if value.tzinfo is None:
        value = value.replace(tzinfo=zone)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def validate_cron(expression: str, timezone_name: str) -> None:
    next_run_utc(expression, timezone_name)
