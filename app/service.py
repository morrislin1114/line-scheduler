"""Business logic for schedule commands."""

from __future__ import annotations

from datetime import date
from typing import Optional

from app import formatter
from app.models import Command, CommandType, NewShift
from app.parser import _today_taipei
from app.storage import ShiftStore


class ScheduleService:
    def __init__(self, store: ShiftStore) -> None:
        self.store = store

    def handle(
        self,
        command: Command,
        *,
        group_id: str,
        user_id: str,
        display_name: str,
        today: Optional[date] = None,
    ) -> str:
        if today is None:
            today = _today_taipei()

        if command.type == CommandType.HELP:
            return formatter.HELP_TEXT.strip()

        if command.type == CommandType.LIST:
            shifts = self.store.list_from_date(group_id, today)
            return formatter.truncate_reply(formatter.format_list(shifts))

        if command.type == CommandType.ADD:
            assert command.shift_date is not None
            assert command.start_hour is not None
            assert command.end_hour is not None
            person = command.person_name if command.person_name else display_name
            shift = self.store.add_shift(
                NewShift(
                    group_id=group_id,
                    shift_date=command.shift_date,
                    start_hour=command.start_hour,
                    end_hour=command.end_hour,
                    person_name=person,
                    created_by_user_id=user_id,
                    created_by_name=display_name,
                )
            )
            return formatter.format_add_success(shift)

        if command.type == CommandType.CANCEL:
            assert command.shift_date is not None
            assert command.start_hour is not None
            assert command.end_hour is not None

            if command.person_name:
                deleted = self.store.delete_latest(
                    group_id,
                    command.shift_date,
                    command.start_hour,
                    command.end_hour,
                    person_name=command.person_name,
                )
                label = command.person_name
            else:
                deleted = self.store.delete_latest(
                    group_id,
                    command.shift_date,
                    command.start_hour,
                    command.end_hour,
                    created_by_user_id=user_id,
                )
                if deleted is None:
                    deleted = self.store.delete_latest(
                        group_id,
                        command.shift_date,
                        command.start_hour,
                        command.end_hour,
                        person_name=display_name,
                    )
                label = display_name

            if deleted is None:
                return formatter.format_cancel_not_found(
                    command.shift_date,
                    command.start_hour,
                    command.end_hour,
                    label,
                )
            return formatter.format_cancel_success(deleted)

        return "無法處理此指令。"
