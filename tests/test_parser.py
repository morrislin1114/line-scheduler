"""Tests for command parsing and date resolution."""

from datetime import date

import pytest

from app.models import CommandType
from app.parser import parse_command, resolve_shift_date


def test_list_command():
    cmd = parse_command("查詢")
    assert cmd is not None
    assert cmd.type == CommandType.LIST


def test_help_commands():
    for text in ("說明", "help", "Help"):
        cmd = parse_command(text)
        assert cmd is not None
        assert cmd.type == CommandType.HELP


def test_add_self():
    today = date(2026, 7, 20)
    cmd = parse_command("7/21 9-13", today=today)
    assert cmd is not None
    assert cmd.type == CommandType.ADD
    assert cmd.shift_date == date(2026, 7, 21)
    assert cmd.start_hour == 9
    assert cmd.end_hour == 13
    assert cmd.person_name is None


def test_add_other():
    today = date(2026, 7, 20)
    cmd = parse_command("7/22 13-19 John", today=today)
    assert cmd is not None
    assert cmd.type == CommandType.ADD
    assert cmd.shift_date == date(2026, 7, 22)
    assert cmd.start_hour == 13
    assert cmd.end_hour == 19
    assert cmd.person_name == "John"


def test_cancel_self_and_other():
    today = date(2026, 7, 20)
    c1 = parse_command("取消 7/21 9-13", today=today)
    assert c1 is not None
    assert c1.type == CommandType.CANCEL
    assert c1.person_name is None

    c2 = parse_command("取消 7/22 13-19 John", today=today)
    assert c2 is not None
    assert c2.type == CommandType.CANCEL
    assert c2.person_name == "John"


def test_past_date_rolls_to_next_year():
    today = date(2026, 7, 21)
    assert resolve_shift_date(7, 20, today=today) == date(2027, 7, 20)
    assert resolve_shift_date(7, 21, today=today) == date(2026, 7, 21)


def test_invalid_hours():
    today = date(2026, 7, 20)
    with pytest.raises(ValueError, match="結束時間"):
        parse_command("7/21 13-9", today=today)
    with pytest.raises(ValueError, match="開始時間"):
        parse_command("7/21 25-26", today=today)


def test_non_command_returns_none():
    assert parse_command("今天吃什麼") is None
    assert parse_command("7/21") is None
    assert parse_command("") is None


def test_padded_and_name_with_spaces():
    today = date(2026, 1, 1)
    cmd = parse_command("07/05 09-18 Mary Jane", today=today)
    assert cmd is not None
    assert cmd.person_name == "Mary Jane"
    assert cmd.start_hour == 9
    assert cmd.end_hour == 18
