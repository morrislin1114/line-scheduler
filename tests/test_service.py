"""Tests for schedule service and storage."""

from datetime import date
from pathlib import Path

from app.models import Command, CommandType
from app.service import ScheduleService
from app.storage import ShiftStore


def _svc(tmp_path: Path) -> ScheduleService:
    return ScheduleService(ShiftStore(tmp_path / "t.db"))


def test_add_list_cancel_self(tmp_path: Path):
    svc = _svc(tmp_path)
    today = date(2026, 7, 20)
    group = "group-1"

    add = Command(
        type=CommandType.ADD,
        shift_date=date(2026, 7, 21),
        start_hour=9,
        end_hour=13,
        person_name=None,
    )
    msg = svc.handle(
        add,
        group_id=group,
        user_id="u-morris",
        display_name="Morris",
        today=today,
    )
    assert "已新增" in msg
    assert "Morris" in msg

    listed = svc.handle(
        Command(type=CommandType.LIST),
        group_id=group,
        user_id="u-morris",
        display_name="Morris",
        today=today,
    )
    assert "Morris" in listed
    assert "共 1 筆" in listed

    cancel = Command(
        type=CommandType.CANCEL,
        shift_date=date(2026, 7, 21),
        start_hour=9,
        end_hour=13,
        person_name=None,
    )
    cmsg = svc.handle(
        cancel,
        group_id=group,
        user_id="u-morris",
        display_name="Morris",
        today=today,
    )
    assert "已取消" in cmsg

    listed2 = svc.handle(
        Command(type=CommandType.LIST),
        group_id=group,
        user_id="u-morris",
        display_name="Morris",
        today=today,
    )
    assert "沒有今日之後" in listed2


def test_duplicate_shifts_allowed(tmp_path: Path):
    svc = _svc(tmp_path)
    today = date(2026, 7, 20)
    group = "g"
    cmd = Command(
        type=CommandType.ADD,
        shift_date=date(2026, 7, 21),
        start_hour=9,
        end_hour=13,
        person_name="John",
    )
    svc.handle(cmd, group_id=group, user_id="u1", display_name="A", today=today)
    svc.handle(cmd, group_id=group, user_id="u1", display_name="A", today=today)
    listed = svc.handle(
        Command(type=CommandType.LIST),
        group_id=group,
        user_id="u1",
        display_name="A",
        today=today,
    )
    assert "共 2 筆" in listed


def test_cancel_removes_latest_only(tmp_path: Path):
    svc = _svc(tmp_path)
    today = date(2026, 7, 20)
    group = "g"
    cmd = Command(
        type=CommandType.ADD,
        shift_date=date(2026, 7, 21),
        start_hour=9,
        end_hour=13,
        person_name="John",
    )
    svc.handle(cmd, group_id=group, user_id="u1", display_name="A", today=today)
    svc.handle(cmd, group_id=group, user_id="u1", display_name="A", today=today)

    cancel = Command(
        type=CommandType.CANCEL,
        shift_date=date(2026, 7, 21),
        start_hour=9,
        end_hour=13,
        person_name="John",
    )
    svc.handle(cancel, group_id=group, user_id="u1", display_name="A", today=today)
    listed = svc.handle(
        Command(type=CommandType.LIST),
        group_id=group,
        user_id="u1",
        display_name="A",
        today=today,
    )
    assert "共 1 筆" in listed


def test_cancel_not_found(tmp_path: Path):
    svc = _svc(tmp_path)
    today = date(2026, 7, 20)
    msg = svc.handle(
        Command(
            type=CommandType.CANCEL,
            shift_date=date(2026, 7, 21),
            start_hour=9,
            end_hour=13,
            person_name="Nobody",
        ),
        group_id="g",
        user_id="u1",
        display_name="A",
        today=today,
    )
    assert "找不到" in msg


def test_group_isolation(tmp_path: Path):
    svc = _svc(tmp_path)
    today = date(2026, 7, 20)
    cmd = Command(
        type=CommandType.ADD,
        shift_date=date(2026, 7, 21),
        start_hour=9,
        end_hour=13,
        person_name="X",
    )
    svc.handle(cmd, group_id="g1", user_id="u", display_name="A", today=today)
    listed = svc.handle(
        Command(type=CommandType.LIST),
        group_id="g2",
        user_id="u",
        display_name="A",
        today=today,
    )
    assert "沒有今日之後" in listed


def test_list_excludes_past(tmp_path: Path):
    store = ShiftStore(tmp_path / "t.db")
    from app.models import NewShift

    store.add_shift(
        NewShift(
            group_id="g",
            shift_date=date(2026, 7, 10),
            start_hour=9,
            end_hour=13,
            person_name="Old",
            created_by_user_id="u",
            created_by_name="A",
        )
    )
    store.add_shift(
        NewShift(
            group_id="g",
            shift_date=date(2026, 7, 25),
            start_hour=9,
            end_hour=13,
            person_name="New",
            created_by_user_id="u",
            created_by_name="A",
        )
    )
    svc = ScheduleService(store)
    listed = svc.handle(
        Command(type=CommandType.LIST),
        group_id="g",
        user_id="u",
        display_name="A",
        today=date(2026, 7, 21),
    )
    assert "New" in listed
    assert "Old" not in listed
    assert "共 1 筆" in listed


def test_list_with_days_window(tmp_path: Path):
    from app.models import NewShift

    store = ShiftStore(tmp_path / "t.db")
    store.add_shift(
        NewShift(
            group_id="g",
            shift_date=date(2026, 7, 21),
            start_hour=9,
            end_hour=12,
            person_name="Near",
            created_by_user_id="u",
            created_by_name="A",
        )
    )
    store.add_shift(
        NewShift(
            group_id="g",
            shift_date=date(2026, 8, 1),
            start_hour=9,
            end_hour=12,
            person_name="Far",
            created_by_user_id="u",
            created_by_name="A",
        )
    )
    svc = ScheduleService(store)
    today = date(2026, 7, 21)
    msg = svc.handle(
        Command(type=CommandType.LIST, days=7),
        group_id="g",
        user_id="u",
        display_name="A",
        today=today,
    )
    assert "7 天內" in msg
    assert "Near" in msg
    assert "Far" not in msg
    assert "共 1 筆" in msg

    all_msg = svc.handle(
        Command(type=CommandType.LIST, days=None),
        group_id="g",
        user_id="u",
        display_name="A",
        today=today,
    )
    assert "Near" in all_msg and "Far" in all_msg
    assert "共 2 筆" in all_msg


def test_list_by_person_and_self_alias(tmp_path: Path):
    from app.models import NewShift

    store = ShiftStore(tmp_path / "t.db")
    for name, d in (("Morris", date(2026, 7, 22)), ("Kelly", date(2026, 7, 23))):
        store.add_shift(
            NewShift(
                group_id="g",
                shift_date=d,
                start_hour=9,
                end_hour=12,
                person_name=name,
                created_by_user_id="u",
                created_by_name="A",
            )
        )
    svc = ScheduleService(store)
    today = date(2026, 7, 21)

    by_name = svc.handle(
        Command(type=CommandType.LIST, person_name="Morris"),
        group_id="g",
        user_id="u",
        display_name="Someone",
        today=today,
    )
    assert "Morris" in by_name
    assert "Kelly" not in by_name
    assert "共 1 筆" in by_name

    self_msg = svc.handle(
        Command(type=CommandType.LIST, person_name="我"),
        group_id="g",
        user_id="u",
        display_name="Morris",
        today=today,
    )
    assert "Morris" in self_msg
    assert "Kelly" not in self_msg


def test_multi_line_batch_add(tmp_path: Path):
    from app.parser import parse_message

    svc = _svc(tmp_path)
    today = date(2026, 7, 20)
    text = """7/21 9-12 Morris
7/22 9-21 Kelly
7/23 13-21 Annie"""
    parsed = parse_message(text, today=today)
    msg = svc.handle_message(
        parsed,
        group_id="g",
        user_id="u1",
        display_name="Admin",
        today=today,
    )
    assert msg is not None
    assert "已新增 3 筆" in msg
    assert "Morris" in msg and "Kelly" in msg and "Annie" in msg

    listed = svc.handle(
        Command(type=CommandType.LIST),
        group_id="g",
        user_id="u1",
        display_name="Admin",
        today=today,
    )
    assert "共 3 筆" in listed
