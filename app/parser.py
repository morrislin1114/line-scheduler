"""Parse group chat text into scheduling commands."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from app.config import TAIPEI_TZ
from app.models import Command, CommandType

_ADD_RE = re.compile(
    r"^(\d{1,2})/(\d{1,2})\s+(\d{1,2})-(\d{1,2})(?:\s+(.+))?$"
)
_CANCEL_RE = re.compile(
    r"^取消\s+(\d{1,2})/(\d{1,2})\s+(\d{1,2})-(\d{1,2})(?:\s+(.+))?$"
)
_DATE_TOKEN_RE = re.compile(r"^(\d{1,2})/(\d{1,2})$")

# Safety cap for 查詢 N
MAX_LIST_DAYS = 366

_WEEK_KEYWORDS = {
    "本週": "this_week",
    "本周": "this_week",
    "下週": "next_week",
    "下周": "next_week",
}


def _today_taipei() -> date:
    return datetime_now_taipei().date()


def datetime_now_taipei():
    from datetime import datetime

    return datetime.now(ZoneInfo(TAIPEI_TZ))


def resolve_shift_date(month: int, day: int, today: Optional[date] = None) -> date:
    """Map M/D to a concrete date; past dates roll to next year (for add/cancel)."""
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


def resolve_query_date(month: int, day: int, today: Optional[date] = None) -> date:
    """
    Map M/D for 查詢.

    Prefer current calendar year (including recent past).
    If that date is more than ~6 months before today, use next year.
    """
    if today is None:
        today = _today_taipei()
    try:
        candidate = date(today.year, month, day)
    except ValueError as exc:
        raise ValueError(f"無效日期：{month}/{day}") from exc
    if (today - candidate).days > 183:
        try:
            candidate = date(today.year + 1, month, day)
        except ValueError as exc:
            raise ValueError(f"無效日期：{month}/{day}") from exc
    return candidate


def week_range(today: date, which: str) -> Tuple[date, date]:
    """Return Mon–Sun inclusive for this or next week (Asia/Taipei calendar)."""
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    if which == "this_week":
        return monday, sunday
    if which == "next_week":
        return monday + timedelta(days=7), sunday + timedelta(days=7)
    raise ValueError(f"未知週別：{which}")


_WEEKDAYS = "一二三四五六日"


def _date_label(d: date) -> str:
    return f"{d.month}/{d.day}（{_WEEKDAYS[d.weekday()]}）"


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


def parse_list_command(
    raw: str, today: Optional[date] = None
) -> Optional[Command]:
    """
    Parse 查詢 variants:

    - 查詢
    - 查詢 7
    - 查詢 7/21
    - 查詢 本週 / 下週（本周／下周 亦可）
    - 查詢 Morris / 查詢 我
    - 可與人名併用：查詢 7/21 Morris、查詢 本週 Morris、查詢 Morris 7
    """
    if today is None:
        today = _today_taipei()

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
    week_mode: Optional[str] = None
    date_token: Optional[str] = None
    name_parts: List[str] = []

    for p in parts:
        if p in _WEEK_KEYWORDS and week_mode is None:
            week_mode = _WEEK_KEYWORDS[p]
            continue
        if _DATE_TOKEN_RE.match(p) and date_token is None:
            date_token = p
            continue
        if _is_days_token(p) and days is None and date_token is None:
            # Pure number = day window (not a date)
            days = _parse_list_days(p)
            continue
        name_parts.append(p)

    person = " ".join(name_parts).strip() or None

    modes = sum(
        [
            days is not None,
            week_mode is not None,
            date_token is not None,
        ]
    )
    if modes > 1:
        raise ValueError(
            "請擇一條件：天數（查詢 7）、日期（查詢 7/21）、或本週／下週"
        )

    if date_token:
        m = _DATE_TOKEN_RE.match(date_token)
        assert m is not None
        month, day = int(m.group(1)), int(m.group(2))
        d = resolve_query_date(month, day, today=today)
        return Command(
            type=CommandType.LIST,
            person_name=person,
            list_from=d,
            list_to=d,
            list_label=_date_label(d),
        )

    if week_mode:
        start, end = week_range(today, week_mode)
        label = "本週" if week_mode == "this_week" else "下週"
        # Human-readable span e.g. 本週 7/21–7/27
        span = f"{label} {start.month}/{start.day}–{end.month}/{end.day}"
        return Command(
            type=CommandType.LIST,
            person_name=person,
            list_from=start,
            list_to=end,
            list_label=span,
        )

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

    list_cmd = parse_list_command(raw, today=today)
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

    if not commands and not errors:
        return MessageParseResult(commands=[], line_errors=[], ignore=True)

    if not commands and errors and all(
        e.error and e.error.startswith("無法辨識") for e in errors
    ):
        return MessageParseResult(commands=[], line_errors=[], ignore=True)

    return MessageParseResult(commands=commands, line_errors=errors)
