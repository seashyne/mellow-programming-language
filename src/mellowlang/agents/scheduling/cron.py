"""The cron expression reader: field parsing with steps and ranges, the match test, and the minute-
   by-minute next-run search."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .paths import _now_iso


def _parse_field(field: str, value: int) -> bool:
    field = str(field).strip()
    if field == '*':
        return True
    if field.startswith('*/'):
        try:
            step = int(field[2:])
            return step > 0 and value % step == 0
        except Exception:
            return False
    parts = [x.strip() for x in field.split(',') if x.strip()]
    for part in parts:
        if '-' in part:
            try:
                a, b = [int(x) for x in part.split('-', 1)]
                if a <= value <= b:
                    return True
            except Exception:
                continue
        else:
            try:
                if int(part) == value:
                    return True
            except Exception:
                continue
    return False


def cron_matches(expr: str, dt: datetime | None = None) -> bool:
    now = (dt or datetime.now(timezone.utc)).astimezone(timezone.utc)
    expr = str(expr or '').strip().lower()
    aliases = {'@hourly': '0 * * * *', '@daily': '0 0 * * *', '@weekly': '0 0 * * 0'}
    expr = aliases.get(expr, expr)
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f'invalid cron expression: {expr}')
    minute, hour, dom, month, dow = fields
    py_dow = (now.weekday() + 1) % 7
    return (
        _parse_field(minute, now.minute)
        and _parse_field(hour, now.hour)
        and _parse_field(dom, now.day)
        and _parse_field(month, now.month)
        and _parse_field(dow, py_dow)
    )


def next_run(expr: str, from_dt: datetime | None = None, *, max_minutes: int = 60 * 24 * 31) -> str:
    start = (from_dt or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(second=0, microsecond=0)
    probe = start + timedelta(minutes=1)
    for _ in range(max_minutes):
        if cron_matches(expr, probe):
            return _now_iso(probe)
        probe += timedelta(minutes=1)
    raise ValueError(f'could not find next run for cron: {expr}')
