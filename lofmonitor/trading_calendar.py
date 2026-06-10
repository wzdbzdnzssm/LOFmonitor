"""Trading day helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache

import exchange_calendars as xcals


@lru_cache(maxsize=1)
def _sse_calendar():
    return xcals.get_calendar("XSHG")


def is_trading_day(day: date | None = None) -> bool:
    target = day or date.today()
    calendar = _sse_calendar()
    return calendar.is_session(target.isoformat())


def next_run_datetime(push_time: str, now: datetime | None = None) -> datetime:
    current = now or datetime.now()
    hour, minute = map(int, push_time.split(":"))
    candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    calendar = _sse_calendar()

    while True:
        if calendar.is_session(candidate.date().isoformat()) and candidate > current:
            return candidate
        candidate = candidate.replace(hour=hour, minute=minute) + timedelta(days=1)
