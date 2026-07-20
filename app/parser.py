"""Parse group chat text into scheduling commands."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import List, Optional
from zoneinfo import ZoneInfo

from app.config import TAIPEI_TZ
from app.models import Command, CommandType

_ADD_RE = re.compile(
    r"^(\d{1,2})/(\d{1,2})\s+(\d{1,2})-(\d{1,2})(?:\s+(.+))?$"
)
_CANCEL_RE = re.compile(
    r"^取消\s+(\d{1,2})/(\d{1,2})\s+(\d{1,2})-(\d{1,2})(?:\s+(.+))?$"
)
# Safety cap for 查詢 N
MAX_LIST_DAYS = 366


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


def _is_days_token(token: str) -> bool:
    return bool(re.fullmatch(r"\d{1,3}", token))


def _parse_list_days(token: str) -> int:
    days = int(token)
    if days < 1:
        raise ValueError("查詢天數須為 1 以上的整數，例如：查詢 7")
    if days > MAX_LIST_DAYS:
        raise ValueError(f"查詢天數最多 {MAX_LIST_DAYS} 天")
    return days


def parse_list_command(raw: str) -> Optional[Command]:
    """
    Parse 查詢 variants:

    - 查詢
    - 查詢 7                 (N days, all people)
    - 查詢 Morris            (person, from today)
    - 查詢 7 Morris          (person within N days)
    - 查詢 Morris 7          (same)
    - 查詢 我                (self; resolved later via display name)
    """
    text = raw.strip()
    if text == "查詢":
        return Command(type=CommandType.LIST)
    if not re.match(r"^查詢[\s\u3000]", text):
        return None

    rest = re.sub(r"^查詢[\s\u3000]+", "", text).strip()
    if not rest:
        return Command(type=CommandType.LIST)

    parts = rest.split()
    days: Optional[int] = None
    person: Optional[str] = None

    if len(parts) == 1:
        if _is_days_token(parts[0]):
            days = _parse_list_days(parts[0])
        else:
            person = parts[0]
    elif _is_days_token(parts[0]):
        days = _parse_list_days(parts[0])
        person = " ".join(parts[1:]).strip() or None
    elif _is_days_token(parts[-1]):
        days = _parse_list_days(parts[-1])
        person = " ".join(parts[:-1]).strip() or None
    else:
        person = rest

    return Command(type=CommandType.LIST, days=days, person_name=person)


def parse_command(text: str, today: Optional[date] = None) -> Optional[Command]:
    """
    Parse a single-line user text into a Command.

    Returns None if the message is not a bot command (ignore quietly).
    Raises ValueError for recognized but invalid commands (reply with error).
    """
    raw = text.strip()
    if not raw:
        return None

    list_cmd = parse_list_command(raw)
    if list_cmd is not None:
        return list_cmd

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


@dataclass
class LineParseResult:
    line_no: int
    raw: str
    command: Optional[Command] = None
    error: Optional[str] = None


@dataclass
class MessageParseResult:
    """Result of parsing a full message (possibly multi-line)."""

    commands: List[Command]
    line_errors: List[LineParseResult]
    # True when the whole message is not a bot command (ignore)
    ignore: bool = False


def parse_message(text: str, today: Optional[date] = None) -> MessageParseResult:
    """
    Parse a full chat message.

    - Single line: same rules as before (查詢 / 說明 / 新增 / 取消)
    - Multi-line: each non-empty line is add or cancel; 查詢/說明 only valid alone
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return MessageParseResult(commands=[], line_errors=[], ignore=True)

    # Single-line message
    if len(lines) == 1:
        try:
            cmd = parse_command(lines[0], today=today)
        except ValueError as exc:
            return MessageParseResult(
                commands=[],
                line_errors=[
                    LineParseResult(line_no=1, raw=lines[0], error=str(exc))
                ],
            )
        if cmd is None:
            return MessageParseResult(commands=[], line_errors=[], ignore=True)
        return MessageParseResult(commands=[cmd], line_errors=[])

    # Multi-line: only ADD / CANCEL per line
    commands: List[Command] = []
    errors: List[LineParseResult] = []
    for i, line in enumerate(lines, start=1):
        try:
            cmd = parse_command(line, today=today)
        except ValueError as exc:
            errors.append(LineParseResult(line_no=i, raw=line, error=str(exc)))
            continue

        if cmd is None:
            errors.append(
                LineParseResult(
                    line_no=i,
                    raw=line,
                    error="無法辨識（多行僅支援新增/取消格式）",
                )
            )
            continue

        if cmd.type in {CommandType.LIST, CommandType.HELP}:
            errors.append(
                LineParseResult(
                    line_no=i,
                    raw=line,
                    error="「查詢／說明」請單獨一行送出，不可與多行混用",
                )
            )
            continue

        commands.append(cmd)

    # If nothing looked like a command at all, ignore (casual multi-line chat)
    if not commands and not errors:
        return MessageParseResult(commands=[], line_errors=[], ignore=True)

    # All lines failed to parse as known schedule syntax → ignore quietly
    # unless at least one line matched date pattern-ish? If all are "無法辨識"
    # and no commands, treat as ignore only when NO line had errors that look
    # intentional. Safer: if zero commands and all errors are "無法辨識", ignore.
    if not commands and errors and all(
        e.error and e.error.startswith("無法辨識") for e in errors
    ):
        return MessageParseResult(commands=[], line_errors=[], ignore=True)

    return MessageParseResult(commands=commands, line_errors=errors)
