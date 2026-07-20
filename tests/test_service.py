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
