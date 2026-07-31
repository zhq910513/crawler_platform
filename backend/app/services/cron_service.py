from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import status

from app.errors import AppError
from app.utils import utcnow

try:
    from croniter import croniter
except Exception:  # pragma: no cover
    croniter = None

CRON_ERROR_CODE = 40081
MIN_INTERVAL_SECONDS_NORMAL = 300
MIN_INTERVAL_SECONDS_ADMIN = 60



def _parse_field(field: str, minimum: int, maximum: int, names: dict[str, int] | None = None) -> set[int]:
    names = names or {}
    values: set[int] = set()
    for part in field.split(','):
        part = part.strip().lower()
        if not part:
            raise ValueError('空字段')
        step = 1
        if '/' in part:
            base, step_text = part.split('/', 1)
            step = int(step_text)
            if step <= 0:
                raise ValueError('步长必须大于 0')
        else:
            base = part
        if base == '*':
            start, end = minimum, maximum
        elif '-' in base:
            left, right = base.split('-', 1)
            start, end = names.get(left, int(left) if left.isdigit() else left), names.get(right, int(right) if right.isdigit() else right)
            start, end = int(start), int(end)
        else:
            value = names.get(base, int(base) if base.isdigit() else base)
            start = end = int(value)
        if start < minimum or end > maximum or start > end:
            raise ValueError(f'字段 {field} 超出范围 {minimum}-{maximum}')
        values.update(range(start, end + 1, step))
    return values


def _match(dt: datetime, fields: list[set[int]]) -> bool:
    # Python weekday: Monday=0; Cron: Sunday=0, Monday=1
    cron_weekday = 0 if dt.weekday() == 6 else dt.weekday() + 1
    return dt.minute in fields[0] and dt.hour in fields[1] and dt.day in fields[2] and dt.month in fields[3] and cron_weekday in fields[4]


def _fallback_next_times(expression: str, timezone: str, count: int) -> list[datetime]:
    tz = ZoneInfo(timezone)
    parts = expression.split()
    fields = [
        _parse_field(parts[0], 0, 59),
        _parse_field(parts[1], 0, 23),
        _parse_field(parts[2], 1, 31),
        _parse_field(parts[3], 1, 12),
        _parse_field(parts[4], 0, 7),
    ]
    if 7 in fields[4]:
        fields[4].add(0)
        fields[4].discard(7)
    current = utcnow().replace(tzinfo=UTC).astimezone(tz).replace(second=0, microsecond=0)
    from datetime import timedelta
    out: list[datetime] = []
    for _ in range(366 * 24 * 60):
        current += timedelta(minutes=1)
        if _match(current, fields):
            out.append(current)
            if len(out) >= count:
                return out
    raise ValueError('一年内没有匹配的执行时间')

class CronService:
    """5 段 Linux Cron 校验与预览。暂不支持秒、年、?、L、W、# 等 Quartz 语法。"""

    @staticmethod
    def normalize(expression: str) -> str:
        return " ".join((expression or "").strip().split())

    @staticmethod
    def validate(expression: str, timezone: str = "Asia/Shanghai", *, is_super_admin: bool = False) -> str:
        expr = CronService.normalize(expression)
        parts = expr.split()
        if len(parts) != 5:
            raise AppError("Cron 表达式必须是 5 段格式：分钟 小时 日 月 星期", code=CRON_ERROR_CODE, http_status=status.HTTP_400_BAD_REQUEST)
        if any(token in expr for token in ["?", "L", "W", "#"]):
            raise AppError("暂不支持 Quartz 特殊语法：?、L、W、#", code=CRON_ERROR_CODE, http_status=status.HTTP_400_BAD_REQUEST)
        try:
            tz = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise AppError("调度时区不合法", code=40082, http_status=status.HTTP_400_BAD_REQUEST) from exc
        try:
            if croniter:
                base = utcnow().replace(tzinfo=UTC).astimezone(tz)
                itr = croniter(expr, base)
                first = itr.get_next(datetime)
                second = itr.get_next(datetime)
            else:
                first, second = _fallback_next_times(expr, timezone, 2)
        except Exception as exc:
            raise AppError("Cron 表达式不合法，请检查分钟、小时、日期、月份和星期配置", code=CRON_ERROR_CODE, http_status=status.HTTP_400_BAD_REQUEST, data={"reason": str(exc)}) from exc
        min_interval = MIN_INTERVAL_SECONDS_ADMIN if is_super_admin else MIN_INTERVAL_SECONDS_NORMAL
        if (second - first).total_seconds() < min_interval:
            raise AppError(f"Cron 执行间隔不能小于 {min_interval // 60} 分钟", code=40083, http_status=status.HTTP_400_BAD_REQUEST)
        return expr

    @staticmethod
    def preview(expression: str, timezone: str = "Asia/Shanghai", count: int = 5, *, is_super_admin: bool = False) -> dict:
        expr = CronService.validate(expression, timezone, is_super_admin=is_super_admin)
        count = max(1, min(int(count or 5), 20))
        tz = ZoneInfo(timezone)
        next_times: list[str] = []
        if croniter:
            base = utcnow().replace(tzinfo=UTC).astimezone(tz)
            itr = croniter(expr, base)
            for _ in range(count):
                dt = itr.get_next(datetime)
                next_times.append(dt.strftime("%Y-%m-%d %H:%M:%S"))
        else:
            next_times = [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in _fallback_next_times(expr, timezone, count)]
        return {"valid": True, "cronExpression": expr, "timezone": timezone, "nextTimes": next_times}

    @staticmethod
    def next_time(expression: str, timezone: str = "Asia/Shanghai", *, is_super_admin: bool = False):
        expr = CronService.validate(expression, timezone, is_super_admin=is_super_admin)
        tz = ZoneInfo(timezone)
        if croniter:
            base_local = utcnow().replace(tzinfo=UTC).astimezone(tz)
            return croniter(expr, base_local).get_next(datetime).astimezone(UTC).replace(tzinfo=None)
        return _fallback_next_times(expr, timezone, 1)[0].astimezone(UTC).replace(tzinfo=None)

    @staticmethod
    def label_from_config(config: dict | None, expression: str) -> str:
        config = config or {}
        mode = config.get("mode")
        if mode == "EVERY_N_MINUTES":
            return f"每 {config.get('intervalMinutes', '')} 分钟执行一次"
        if mode == "EVERY_N_HOURS":
            return f"每 {config.get('intervalHours', '')} 小时执行一次"
        if mode == "DAILY":
            return f"每天 {config.get('time', '')} 执行"
        if mode == "WEEKLY":
            return f"每周{config.get('weekday', '')} {config.get('time', '')} 执行"
        if mode == "MONTHLY":
            return f"每月 {config.get('day', '')} 日 {config.get('time', '')} 执行"
        return expression or "手动执行"
