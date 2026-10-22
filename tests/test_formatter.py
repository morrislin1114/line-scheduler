"""Tests for reply formatting."""

from datetime import date, datetime, timezone

from app.formatter import (
    HELP_TEXT,
    format_add_success,
    format_cancel_success,
    format_day_result,
    format_list,
)
from app.models import Shift


def _shift(
    sid: int,
    d: date,
    start: int,
    end: int,
    name: str,
) -> Shift:
    return Shift(
        id=sid,
        group_id="g1",
        shift_date=d,
        start_hour=start,
        end_hour=end,
        person_name=name,
        created_by_user_id="u1",
        created_by_name="creator",
        created_at=datetime.now(timezone.utc),
    )


def test_format_list_empty():
    text = format_list([])
    assert "沒有今日之後的排班" in text


def test_format_list_with_days_empty():
    text = format_list([], days=7)
    assert "7 天內" in text


def test_format_list_grouped():
    shifts = [
        _shift(1, date(2026, 7, 21), 9, 13, "Morris"),
        _shift(2, date(2026, 7, 21), 13, 19, "John"),
        _shift(3, date(2026, 7, 22), 9, 13, "Alice"),
    ]
    text = format_list(shifts)
    assert "排班一覽" in text
    assert "7/21" in text
    assert "09–13  Morris" in text
    assert "13–19  John" in text
    assert "7/22" in text
    assert "共 3 筆" in text


def test_format_day_result_empty():
    text = format_day_result(date(2026, 7, 21), [])
    assert "無人排班" in text
    assert "7/21" in text


def test_format_add_success_includes_day():
    s = _shift(1, date(2026, 7, 21), 9, 13, "Morris")
    day = [s, _shift(2, date(2026, 7, 21), 13, 19, "John")]
    text = format_add_success(s, day)
    assert text.startswith("✅")
    assert "Morris" in text
    assert "目前" in text
    assert "John" in text


def test_format_cancel_success_empty_day():
    s = _shift(1, date(2026, 7, 21), 9, 13, "Morris")
    text = format_cancel_success(s, [])
    assert "已取消" in text
    assert "無人排班" in text


def test_help_concise():
    assert "查詢" in HELP_TEXT
    assert "取消" in HELP_TEXT
    assert "新增" in HELP_TEXT
    assert "查詢 我" in HELP_TEXT
    assert "翻譯" in HELP_TEXT
    assert "翻印尼" in HELP_TEXT
