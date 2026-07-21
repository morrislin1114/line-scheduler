"""Format shifts and command results for LINE text replies."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from app.models import Shift

_WEEKDAYS = "一二三四五六日"


def format_time_range(start_hour: int, end_hour: int) -> str:
    return f"{start_hour:02d}:00–{end_hour:02d}:00"


def format_date_heading(d: date) -> str:
    # Monday=0 ... Sunday=6
    return f"{d.month}/{d.day}（{_WEEKDAYS[d.weekday()]}）"


def format_shift_brief(shift: Shift) -> str:
    return (
        f"{format_date_heading(shift.shift_date)} "
        f"{format_time_range(shift.start_hour, shift.end_hour)}  "
        f"{shift.person_name}"
    )


def format_day_result(d: date, shifts: Sequence[Shift]) -> str:
    """Current schedule for a single calendar day."""
    day_items = sorted(
        [s for s in shifts if s.shift_date == d],
        key=lambda s: (s.start_hour, s.end_hour, s.person_name, s.id),
    )
    lines = [f"📌 {format_date_heading(d)} 目前："]
    if not day_items:
        lines.append("  無人排班")
    else:
        for s in day_items:
            lines.append(
                f"  {format_time_range(s.start_hour, s.end_hour)}  {s.person_name}"
            )
    return "\n".join(lines)


def format_day_results(
    dates: Sequence[date],
    shifts_by_date: Mapping[date, Sequence[Shift]],
) -> str:
    blocks = [
        format_day_result(d, shifts_by_date.get(d, []))
        for d in sorted(set(dates))
    ]
    return "\n\n".join(blocks)


def format_list(
    shifts: Iterable[Shift],
    *,
    days: Optional[int] = None,
    person_name: Optional[str] = None,
) -> str:
    items: List[Shift] = list(shifts)
    scope_bits: List[str] = []
    if person_name:
        scope_bits.append(person_name)
    if days is not None:
        scope_bits.append(f"今日起 {days} 天內")
    else:
        scope_bits.append("今日起")

    title = "📅 排班一覽（" + " · ".join(scope_bits) + "）"
    if person_name and days is not None:
        empty = (
            f"目前沒有 {person_name} 在今日起 {days} 天內的排班。"
            f"可用 7/21 9-13 {person_name} 新增。"
        )
    elif person_name:
        empty = (
            f"目前沒有 {person_name} 今日之後的排班。"
            f"可用 7/21 9-13 {person_name} 新增。"
        )
    elif days is not None:
        empty = f"目前沒有今日起 {days} 天內的排班。可用 7/21 9-13 新增。"
    else:
        empty = "目前沒有今日之後的排班。可用 7/21 9-13 新增。"

    if not items:
        return empty

    by_date: dict[date, List[Shift]] = defaultdict(list)
    for s in items:
        by_date[s.shift_date].append(s)

    lines = [title, ""]
    for d in sorted(by_date.keys()):
        lines.append(format_date_heading(d))
        for s in by_date[d]:
            lines.append(
                f"  {format_time_range(s.start_hour, s.end_hour)}  {s.person_name}"
            )
        lines.append("")
    lines.append(f"共 {len(items)} 筆")
    return "\n".join(lines).rstrip()


def format_add_success(
    shift: Shift,
    day_shifts: Sequence[Shift],
) -> str:
    return (
        f"✅ 已新增\n{format_shift_brief(shift)}\n\n"
        f"{format_day_result(shift.shift_date, day_shifts)}"
    )


def format_add_batch_success(
    shifts: Sequence[Shift],
    day_shifts_by_date: Mapping[date, Sequence[Shift]],
) -> str:
    if len(shifts) == 1:
        d = shifts[0].shift_date
        return format_add_success(shifts[0], day_shifts_by_date.get(d, []))
    lines = [f"✅ 已新增 {len(shifts)} 筆", ""]
    for s in shifts:
        lines.append(format_shift_brief(s))
    dates = [s.shift_date for s in shifts]
    lines.append("")
    lines.append(format_day_results(dates, day_shifts_by_date))
    return "\n".join(lines)


def format_cancel_success(
    shift: Shift,
    day_shifts: Sequence[Shift],
) -> str:
    return (
        f"🗑 已取消\n{format_shift_brief(shift)}\n\n"
        f"{format_day_result(shift.shift_date, day_shifts)}"
    )


def format_cancel_batch_success(
    shifts: Sequence[Shift],
    day_shifts_by_date: Mapping[date, Sequence[Shift]],
) -> str:
    if len(shifts) == 1:
        d = shifts[0].shift_date
        return format_cancel_success(shifts[0], day_shifts_by_date.get(d, []))
    lines = [f"🗑 已取消 {len(shifts)} 筆", ""]
    for s in shifts:
        lines.append(format_shift_brief(s))
    dates = [s.shift_date for s in shifts]
    lines.append("")
    lines.append(format_day_results(dates, day_shifts_by_date))
    return "\n".join(lines)


def format_cancel_not_found(
    shift_date: date,
    start_hour: int,
    end_hour: int,
    person_label: str,
    day_shifts: Optional[Sequence[Shift]] = None,
) -> str:
    text = (
        "找不到符合的排班：\n"
        f"{format_date_heading(shift_date)} "
        f"{format_time_range(start_hour, end_hour)}  {person_label}"
    )
    if day_shifts is not None:
        text += "\n\n" + format_day_result(shift_date, day_shifts)
    return text


def format_line_errors(errors: Sequence[tuple[int, str, str]]) -> str:
    """errors: (line_no, raw, message)"""
    lines = ["⚠️ 部分行未處理："]
    for line_no, raw, msg in errors:
        preview = raw if len(raw) <= 40 else raw[:37] + "..."
        lines.append(f"  第{line_no}行「{preview}」：{msg}")
    return "\n".join(lines)


HELP_TEXT = """📋 排班說明

【新增】可多行
7/21 9-13
7/22 13-19 John
・沒寫名字＝排自己
・有寫名字＝幫該人排

【取消】可多行
取消 7/21 9-13
取消 7/22 13-19 John
・每次只取消符合條件的最新一筆

【查詢】
查詢              全部（今日起）
查詢 7            今日起 7 天內
查詢 Morris       指定人名
查詢 我           自己的班
查詢 7 Morris     人名＋天數（可對調）

・時間：24 小時制整點（9-13、13-19）
・可重複排班
"""


# LINE text message soft limit
MAX_REPLY_CHARS = 4800


def truncate_reply(text: str, limit: int = MAX_REPLY_CHARS) -> str:
    if len(text) <= limit:
        return text
    notice = "\n…（內容過長已截斷，請改查詢較近日期）"
    return text[: limit - len(notice)] + notice
