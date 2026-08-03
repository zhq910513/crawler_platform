from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
MULTI_CRON_SEPARATOR = ";"


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
    out: list[datetime] = []
    for _ in range(366 * 24 * 60):
        current += timedelta(minutes=1)
        if _match(current, fields):
            out.append(current)
            if len(out) >= count:
                return out
    raise ValueError('一年内没有匹配的执行时间')


def _normalize_time(value: str) -> str:
    text = str(value or "").strip()
    import re
    match = re.match(r"^(\d{1,2}):(\d{2})$", text)
    if not match:
        raise AppError("时间点必须是 HH:mm 格式", code=40084, http_status=status.HTTP_400_BAD_REQUEST)
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise AppError("时间点超出范围", code=40084, http_status=status.HTTP_400_BAD_REQUEST)
    return f"{hour:02d}:{minute:02d}"


def _normalize_times(values: list | tuple | set | None) -> list[str]:
    times = sorted({_normalize_time(str(item)) for item in (values or [])})
    if not times:
        raise AppError("启用定时任务时至少需要一个时间点", code=40085, http_status=status.HTTP_400_BAD_REQUEST)
    return times


def _normalize_int_set(values: list | tuple | set | None, *, minimum: int, maximum: int, empty_message: str, range_message: str) -> list[int]:
    numbers = sorted({int(item) for item in (values or [])})
    if not numbers:
        raise AppError(empty_message, code=40087, http_status=status.HTTP_400_BAD_REQUEST)
    if any(item < minimum or item > maximum for item in numbers):
        raise AppError(range_message, code=40088, http_status=status.HTTP_400_BAD_REQUEST)
    return numbers


def _cron_for_time(time_text: str, day: str = "*", month: str = "*", weekday: str = "*") -> str:
    hour, minute = time_text.split(":")
    return f"{int(minute)} {int(hour)} {day} {month} {weekday}"


def _cron_expressions_for_times(times: list[str], day: str = "*", month: str = "*", weekday: str = "*") -> list[str]:
    minutes = sorted({int(item.split(":")[1]) for item in times})
    if len(minutes) == 1:
        hours = sorted({int(item.split(":")[0]) for item in times})
        return [f"{minutes[0]} {','.join(str(hour) for hour in hours)} {day} {month} {weekday}"]
    return [_cron_for_time(item, day=day, month=month, weekday=weekday) for item in times]


def _ensure_timezone(timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise AppError("调度时区不合法", code=40082, http_status=status.HTTP_400_BAD_REQUEST) from exc


class CronService:
    """5 段 Linux Cron 校验与预览。支持用分号连接多个 5 段 Cron，用于表达业务多时间点。"""

    @staticmethod
    def normalize(expression: str) -> str:
        return " ".join((expression or "").strip().split())

    @staticmethod
    def split_expressions(expression: str) -> list[str]:
        expressions = [CronService.normalize(item) for item in (expression or "").split(MULTI_CRON_SEPARATOR)]
        expressions = [item for item in expressions if item]
        if not expressions:
            raise AppError("Cron 表达式不能为空", code=CRON_ERROR_CODE, http_status=status.HTTP_400_BAD_REQUEST)
        return expressions

    @staticmethod
    def _validate_single(expression: str, timezone: str) -> str:
        expr = CronService.normalize(expression)
        parts = expr.split()
        if len(parts) != 5:
            raise AppError("Cron 表达式必须是 5 段格式：分钟 小时 日 月 星期", code=CRON_ERROR_CODE, http_status=status.HTTP_400_BAD_REQUEST)
        if any(token in expr for token in ["?", "L", "W", "#"]):
            raise AppError("暂不支持 Quartz 特殊语法：?、L、W、#", code=CRON_ERROR_CODE, http_status=status.HTTP_400_BAD_REQUEST)
        _ensure_timezone(timezone)
        try:
            if croniter:
                base = utcnow().replace(tzinfo=UTC).astimezone(ZoneInfo(timezone))
                itr = croniter(expr, base)
                itr.get_next(datetime)
            else:
                _fallback_next_times(expr, timezone, 1)
        except Exception as exc:
            raise AppError("Cron 表达式不合法，请检查分钟、小时、日期、月份和星期配置", code=CRON_ERROR_CODE, http_status=status.HTTP_400_BAD_REQUEST, data={"reason": str(exc)}) from exc
        return expr

    @staticmethod
    def _next_datetimes_for_single(expression: str, timezone: str, count: int) -> list[datetime]:
        tz = ZoneInfo(timezone)
        if croniter:
            base = utcnow().replace(tzinfo=UTC).astimezone(tz)
            itr = croniter(expression, base)
            return [itr.get_next(datetime) for _ in range(count)]
        return _fallback_next_times(expression, timezone, count)

    @staticmethod
    def _combined_next_datetimes(expressions: list[str], timezone: str, count: int) -> list[datetime]:
        wanted = max(1, min(int(count or 5), 20))
        candidates: list[datetime] = []
        # 多表达式可能在同一分钟重复，抓取更大的窗口后去重排序。
        per_expression_count = max(wanted * 3, wanted + 3)
        for expr in expressions:
            candidates.extend(CronService._next_datetimes_for_single(expr, timezone, per_expression_count))
        unique: dict[str, datetime] = {}
        for item in candidates:
            key = item.strftime("%Y-%m-%d %H:%M:%S")
            unique[key] = item
        ordered = sorted(unique.values())
        if len(ordered) < wanted:
            raise AppError("一年内没有足够的调度预览时间", code=CRON_ERROR_CODE, http_status=status.HTTP_400_BAD_REQUEST)
        return ordered[:wanted]

    @staticmethod
    def validate(expression: str, timezone: str = "Asia/Shanghai", *, is_super_admin: bool = False) -> str:
        expressions = [CronService._validate_single(item, timezone) for item in CronService.split_expressions(expression)]
        min_interval = MIN_INTERVAL_SECONDS_ADMIN if is_super_admin else MIN_INTERVAL_SECONDS_NORMAL
        next_times = CronService._combined_next_datetimes(expressions, timezone, 2)
        if len(next_times) >= 2 and (next_times[1] - next_times[0]).total_seconds() < min_interval:
            raise AppError(f"Cron 执行间隔不能小于 {min_interval // 60} 分钟", code=40083, http_status=status.HTTP_400_BAD_REQUEST)
        return f" {MULTI_CRON_SEPARATOR} ".join(expressions)

    @staticmethod
    def preview(expression: str, timezone: str = "Asia/Shanghai", count: int = 5, *, is_super_admin: bool = False) -> dict:
        expr = CronService.validate(expression, timezone, is_super_admin=is_super_admin)
        expressions = CronService.split_expressions(expr)
        next_times = [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in CronService._combined_next_datetimes(expressions, timezone, count)]
        return {"valid": True, "cronExpression": expr, "timezone": timezone, "nextTimes": next_times}

    @staticmethod
    def next_time(expression: str, timezone: str = "Asia/Shanghai", *, is_super_admin: bool = False):
        expr = CronService.validate(expression, timezone, is_super_admin=is_super_admin)
        first = CronService._combined_next_datetimes(CronService.split_expressions(expr), timezone, 1)[0]
        return first.astimezone(UTC).replace(tzinfo=None)

    @staticmethod
    def normalize_config(config: dict | None, timezone: str = "Asia/Shanghai") -> tuple[str, dict, str]:
        config = dict(config or {})
        mode = str(config.get("mode") or "").strip()
        mode_key = mode.lower()
        _ensure_timezone(timezone)

        if mode_key in {"daily_times", "daily"} and "times" in config:
            times = _normalize_times(config.get("times"))
            expressions = _cron_expressions_for_times(times)
            normalized = {"mode": "daily_times", "times": times, "timezone": timezone}
            return f" {MULTI_CRON_SEPARATOR} ".join(expressions), normalized, f"每天 {', '.join(times)} 执行"

        if mode_key in {"weekly_times", "weekly"} and "times" in config:
            weekdays = _normalize_int_set(config.get("weekdays"), minimum=0, maximum=7, empty_message="每周调度必须选择星期", range_message="星期必须在 0-7 范围内")
            cron_days = sorted({0 if item in {0, 7} else item for item in weekdays})
            times = _normalize_times(config.get("times"))
            expressions = _cron_expressions_for_times(times, weekday=','.join(str(day) for day in cron_days))
            normalized = {"mode": "weekly_times", "weekdays": cron_days, "times": times, "timezone": timezone}
            return f" {MULTI_CRON_SEPARATOR} ".join(expressions), normalized, f"每周 {','.join(str(item) for item in cron_days)} 的 {', '.join(times)} 执行"

        if mode_key in {"monthly_times", "monthly"} and "times" in config:
            days = _normalize_int_set(config.get("days"), minimum=1, maximum=31, empty_message="每月调度必须选择日期", range_message="每月日期必须在 1-31 范围内")
            times = _normalize_times(config.get("times"))
            expressions = _cron_expressions_for_times(times, day=','.join(str(day) for day in days))
            normalized = {"mode": "monthly_times", "days": days, "times": times, "timezone": timezone}
            return f" {MULTI_CRON_SEPARATOR} ".join(expressions), normalized, f"每月 {','.join(str(item) for item in days)} 日 {', '.join(times)} 执行"

        if mode_key in {"every_n_minutes", "every_n_minute"}:
            interval = int(config.get("intervalMinutes") or config.get("interval_minutes") or 0)
            if interval < 1 or interval > 59:
                raise AppError("分钟间隔必须在 1-59 范围内；超过 59 分钟请使用每 N 小时或高级 Cron", code=40089, http_status=status.HTTP_400_BAD_REQUEST)
            normalized = {"mode": "EVERY_N_MINUTES", "intervalMinutes": interval, "timezone": timezone}
            return f"*/{interval} * * * *", normalized, f"每 {interval} 分钟执行一次"

        if mode_key in {"every_n_hours", "every_n_hour"}:
            interval = int(config.get("intervalHours") or config.get("interval_hours") or 0)
            if interval < 1 or interval > 24:
                raise AppError("小时间隔必须在 1-24 范围内", code=40090, http_status=status.HTTP_400_BAD_REQUEST)
            expression = "0 0 * * *" if interval == 24 else f"0 */{interval} * * *"
            normalized = {"mode": "EVERY_N_HOURS", "intervalHours": interval, "timezone": timezone}
            return expression, normalized, f"每 {interval} 小时执行一次"

        if mode_key == "daily" and "time" in config:
            time_text = _normalize_time(str(config.get("time")))
            normalized = {"mode": "DAILY", "time": time_text, "timezone": timezone}
            return _cron_for_time(time_text), normalized, f"每天 {time_text} 执行"

        if mode_key == "weekly" and "time" in config:
            weekday = int(config.get("weekday"))
            if weekday < 0 or weekday > 7:
                raise AppError("星期必须在 0-7 范围内", code=40088, http_status=status.HTTP_400_BAD_REQUEST)
            weekday = 0 if weekday in {0, 7} else weekday
            time_text = _normalize_time(str(config.get("time")))
            normalized = {"mode": "WEEKLY", "weekday": weekday, "time": time_text, "timezone": timezone}
            return _cron_for_time(time_text, weekday=str(weekday)), normalized, f"每周 {weekday} 的 {time_text} 执行"

        if mode_key == "monthly" and "time" in config:
            day = int(config.get("day"))
            if day < 1 or day > 31:
                raise AppError("每月日期必须在 1-31 范围内", code=40088, http_status=status.HTTP_400_BAD_REQUEST)
            time_text = _normalize_time(str(config.get("time")))
            normalized = {"mode": "MONTHLY", "day": day, "time": time_text, "timezone": timezone}
            return _cron_for_time(time_text, day=str(day)), normalized, f"每月 {day} 日 {time_text} 执行"

        return "", config, ""

    @staticmethod
    def preview_schedule(config: dict, timezone: str = "Asia/Shanghai", count: int = 5, *, is_super_admin: bool = False) -> dict:
        expression, normalized, label = CronService.normalize_config(config, timezone)
        if not expression:
            raise AppError("调度配置无法生成 Cron 表达式", code=CRON_ERROR_CODE, http_status=status.HTTP_400_BAD_REQUEST)
        result = CronService.preview(expression, timezone, count, is_super_admin=is_super_admin)
        result["scheduleConfig"] = normalized
        result["scheduleLabel"] = label
        return result

    @staticmethod
    def label_from_config(config: dict | None, expression: str) -> str:
        config = config or {}
        mode = config.get("mode")
        if mode == "daily_times":
            return f"每天 {', '.join(config.get('times') or [])} 执行"
        if mode == "weekly_times":
            return f"每周 {','.join(str(item) for item in (config.get('weekdays') or []))} 的 {', '.join(config.get('times') or [])} 执行"
        if mode == "monthly_times":
            return f"每月 {','.join(str(item) for item in (config.get('days') or []))} 日 {', '.join(config.get('times') or [])} 执行"
        if mode == "EVERY_N_MINUTES":
            return f"每 {config.get('intervalMinutes', '')} 分钟执行一次"
        if mode == "EVERY_N_HOURS":
            return f"每 {config.get('intervalHours', '')} 小时执行一次"
        if mode == "DAILY":
            return f"每天 {config.get('time', '')} 执行"
        if mode == "WEEKLY":
            return f"每周 {config.get('weekday', '')} 的 {config.get('time', '')} 执行"
        if mode == "MONTHLY":
            return f"每月 {config.get('day', '')} 日 {config.get('time', '')} 执行"
        return expression or "手动执行"
