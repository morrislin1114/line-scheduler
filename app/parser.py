"""Parse group chat text into scheduling commands."""

from __future__ import annotations

import re
from datetime import date
from typing import Optional
from zoneinfo import ZoneInfo

from app.config import TAIPEI_TZ
from app.models import Command, CommandType

_ADD_RE = re.compile(
    r"^(\d{1,2})/(\d{1,2})\s+(\d{1,2})-(\d{1,2})(?:\s+(.+))?$"
)
_CANCEL_RE = re.compile(
    r"^取消\s+(\d{1,2})/(\d{1,2})\s+(\d{1,2})-(\d{1,2})(?:\s+(.+))?$"
)


def _today_taipei() -> date:
    return datetime_now_taipei().date()


def datetime_now_taipei():
    from datetime import datetime

    return datetime.now(ZoneInfo(TAIPEI_TZ))


def resolve_shift_date(month: int, day: int, today: Optional[date] = None) -> date:
    """Map M/D to a concrete date; past dates roll to next year."""
    if today is None:
        today = _today_taipei()
    try:
        candidate = date(today.year, month, day)
    except ValueError as exc:
        raise ValueError(f"無效日期：{month}/{day}") from exc
    if candidate < today:
        try:
            candidate = date(today.year + 1, month, day)
        except ValueError as exc:
            raise ValueError(f"無效日期：{month}/{day}") from exc
    return candidate


def _validate_hours(start: int, end: int) -> None:
    if not (0 <= start <= 23):
        raise ValueError("開始時間須為 0–23 的整點")
    if not (1 <= end <= 24):
        raise ValueError("結束時間須為 1–24 的整點")
    if end <= start:
        raise ValueError("結束時間必須大於開始時間")


def parse_command(text: str, today: Optional[date] = None) -> Optional[Command]:
    """
    Parse user text into a Command.

    Returns None if the message is not a bot command (ignore quietly).
    Raises ValueError for recognized but invalid commands (reply with error).
    """
    raw = text.strip()
    if not raw:
        return None

    if raw == "查詢":
        return Command(type=CommandType.LIST)

    if raw in {"說明", "help", "Help", "HELP"}:
        return Command(type=CommandType.HELP)

    cancel_m = _CANCEL_RE.match(raw)
    if cancel_m:
        month, day, start, end = (
            int(cancel_m.group(1)),
            int(cancel_m.group(2)),
            int(cancel_m.group(3)),
            int(cancel_m.group(4)),
        )
        name = cancel_m.group(5)
        person = name.strip() if name and name.strip() else None
        _validate_hours(start, end)
        shift_date = resolve_shift_date(month, day, today=today)
        return Command(
            type=CommandType.CANCEL,
            shift_date=shift_date,
            start_hour=start,
            end_hour=end,
            person_name=person,
        )

    add_m = _ADD_RE.match(raw)
    if add_m:
        month, day, start, end = (
            int(add_m.group(1)),
            int(add_m.group(2)),
            int(add_m.group(3)),
            int(add_m.group(4)),
        )
        name = add_m.group(5)
        person = name.strip() if name and name.strip() else None
        _validate_hours(start, end)
        shift_date = resolve_shift_date(month, day, today=today)
        return Command(
            type=CommandType.ADD,
            shift_date=shift_date,
            start_hour=start,
            end_hour=end,
            person_name=person,
        )

    return None
