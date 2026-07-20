"""Tests for command parsing and date resolution."""

from datetime import date

import pytest

from app.models import CommandType
from app.parser import parse_command, parse_message, resolve_shift_date


def test_list_command():
    cmd = parse_command("查詢")
    assert cmd is not None
    assert cmd.type == CommandType.LIST
    assert cmd.days is None


def test_list_with_days():
    cmd = parse_command("查詢 7")
    assert cmd is not None
    assert cmd.type == CommandType.LIST
    assert cmd.days == 7


def test_list_days_invalid():
    with pytest.raises(ValueError, match="1 以上"):
        parse_command("查詢 0")
    with pytest.raises(ValueError, match="最多"):
        parse_command("查詢 999")


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


def test_multi_line_add():
    today = date(2026, 7, 20)
    text = """7/21 9-12 Morris
7/22 9-21 Kelly
7/23 13-21 Annie"""
    result = parse_message(text, today=today)
    assert not result.ignore
    assert len(result.commands) == 3
    assert not result.line_errors
    assert result.commands[0].person_name == "Morris"
    assert result.commands[1].person_name == "Kelly"
    assert result.commands[2].person_name == "Annie"
    assert result.commands[0].start_hour == 9
    assert result.commands[0].end_hour == 12
    assert result.commands[1].end_hour == 21


def test_multi_line_partial_errors():
    today = date(2026, 7, 20)
    text = """7/21 9-12 Morris
not a command
7/22 13-9 Bad"""
    result = parse_message(text, today=today)
    assert len(result.commands) == 1
    assert len(result.line_errors) == 2


def test_multi_line_casual_chat_ignored():
    result = parse_message("hello\nworld")
    assert result.ignore


def test_multi_line_cancel():
    today = date(2026, 7, 20)
    text = """取消 7/21 9-12 Morris
取消 7/22 9-21 Kelly"""
    result = parse_message(text, today=today)
    assert len(result.commands) == 2
    assert all(c.type == CommandType.CANCEL for c in result.commands)
