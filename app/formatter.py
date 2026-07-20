"""Format shifts and command results for LINE text replies."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Iterable, List, Optional, Sequence

from app.models import Shift

_WEEKDAYS = "一二三四五六日"


def format_time_range(start_hour: int, end_hour: int) -> str:
    return f"{start_hour:02d}:00–{end_hour:02d}:00"


def format_date_heading(d: date) -> str:
    # Monday=0 ... Sunday=6
    return f"{d.month}/{d.day}（{_WEEKDAYS[d.weekday()]}）"


def format_shift_line(shift: Shift) -> str:
    return (
        f"{format_date_heading(shift.shift_date)} "
        f"{format_time_range(shift.start_hour, shift.end_hour)}  "
        f"{shift.person_name}"
    )


def format_shift_brief(shift: Shift) -> str:
    return (
        f"{format_date_heading(shift.shift_date)} "
        f"{format_time_range(shift.start_hour, shift.end_hour)}  "
        f"{shift.person_name}"
    )


def format_list(
    shifts: Iterable[Shift],
    *,
    days: Optional[int] = None,
) -> str:
    items: List[Shift] = list(shifts)
    if days is not None:
        title = f"📅 排班一覽（今日起 {days} 天內）"
        empty = f"目前沒有今日起 {days} 天內的排班。可用 7/21 9-13 新增。"
    else:
        title = "📅 排班一覽（今日起）"
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


def format_add_success(shift: Shift) -> str:
    return f"✅ 已新增\n{format_shift_brief(shift)}"


def format_add_batch_success(shifts: Sequence[Shift]) -> str:
    if len(shifts) == 1:
        return format_add_success(shifts[0])
    lines = [f"✅ 已新增 {len(shifts)} 筆", ""]
    for s in shifts:
        lines.append(format_shift_brief(s))
    return "\n".join(lines)


def format_cancel_success(shift: Shift) -> str:
    return f"🗑 已取消\n{format_shift_brief(shift)}"


def format_cancel_batch_success(shifts: Sequence[Shift]) -> str:
    if len(shifts) == 1:
        return format_cancel_success(shifts[0])
    lines = [f"🗑 已取消 {len(shifts)} 筆", ""]
    for s in shifts:
        lines.append(format_shift_brief(s))
    return "\n".join(lines)


def format_cancel_not_found(
    shift_date: date,
    start_hour: int,
    end_hour: int,
    person_label: str,
) -> str:
    return (
        "找不到符合的排班：\n"
        f"{format_date_heading(shift_date)} "
        f"{format_time_range(start_hour, end_hour)}  {person_label}"
    )


def format_line_errors(errors: Sequence[tuple[int, str, str]]) -> str:
    """errors: (line_no, raw, message)"""
    lines = ["⚠️ 部分行未處理："]
    for line_no, raw, msg in errors:
        preview = raw if len(raw) <= 40 else raw[:37] + "..."
        lines.append(f"  第{line_no}行「{preview}」：{msg}")
    return "\n".join(lines)


HELP_TEXT = """📋 排班 Bot 說明

【新增】（可多行一次送出）
7/21 9-13
7/22 13-19 John
7/21 9-12 Morris
7/22 9-21 Kelly
7/23 13-21 Annie
→ 沒帶名字排自己；有帶名字幫該人排

【取消】（可多行）
取消 7/21 9-13
取消 7/22 13-19 John
→ 每次只取消符合條件的最新一筆

【查詢】
查詢
→ 列出今日之後的全部班表
查詢 7
→ 列出今日算起 7 天內的班表（含今天）

時間為 24 小時制整點，例如 9-13、13-19。
可重複排班（不擋同人同時段）。
"""


# LINE text message soft limit
MAX_REPLY_CHARS = 4800


def truncate_reply(text: str, limit: int = MAX_REPLY_CHARS) -> str:
    if len(text) <= limit:
        return text
    notice = "\n…（內容過長已截斷，請改查詢較近日期）"
    return text[: limit - len(notice)] + notice
