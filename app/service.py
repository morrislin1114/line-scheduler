"""Business logic for schedule commands."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence

from app import formatter
from app.models import Command, CommandType, NewShift, Shift
from app.parser import MessageParseResult, _today_taipei
from app.storage import ShiftStore


class ScheduleService:
    def __init__(self, store: ShiftStore) -> None:
        self.store = store

    def handle_message(
        self,
        parsed: MessageParseResult,
        *,
        group_id: str,
        user_id: str,
        display_name: str,
        today: Optional[date] = None,
    ) -> Optional[str]:
        """
        Handle a full parsed message. Returns None if nothing to reply (ignore).
        """
        if parsed.ignore:
            return None

        if today is None:
            today = _today_taipei()

        # Pure parse errors (no successful commands)
        if not parsed.commands and parsed.line_errors:
            return formatter.truncate_reply(
                formatter.format_line_errors(
                    [(e.line_no, e.raw, e.error or "錯誤") for e in parsed.line_errors]
                )
            )

        # Single special commands
        if len(parsed.commands) == 1 and not parsed.line_errors:
            only = parsed.commands[0]
            if only.type in {CommandType.LIST, CommandType.HELP}:
                return self.handle(
                    only,
                    group_id=group_id,
                    user_id=user_id,
                    display_name=display_name,
                    today=today,
                )

        # Batch add / cancel (and mixed)
        parts: List[str] = []
        added: List[Shift] = []
        cancelled: List[Shift] = []
        cancel_misses: List[str] = []

        for command in parsed.commands:
            if command.type == CommandType.ADD:
                shift = self._add(command, group_id, user_id, display_name)
                added.append(shift)
            elif command.type == CommandType.CANCEL:
                deleted, label = self._cancel(
                    command, group_id, user_id, display_name
                )
                if deleted:
                    cancelled.append(deleted)
                else:
                    assert command.shift_date is not None
                    assert command.start_hour is not None
                    assert command.end_hour is not None
                    day = self._shifts_on_date(group_id, command.shift_date)
                    cancel_misses.append(
                        formatter.format_cancel_not_found(
                            command.shift_date,
                            command.start_hour,
                            command.end_hour,
                            label,
                            day_shifts=day,
                        )
                    )
            else:
                # LIST/HELP mixed into multi-line already rejected in parser
                parts.append(
                    self.handle(
                        command,
                        group_id=group_id,
                        user_id=user_id,
                        display_name=display_name,
                        today=today,
                    )
                )

        if added:
            snaps = self._snapshots_for_dates(
                group_id, [s.shift_date for s in added]
            )
            parts.append(formatter.format_add_batch_success(added, snaps))
        if cancelled:
            snaps = self._snapshots_for_dates(
                group_id, [s.shift_date for s in cancelled]
            )
            parts.append(formatter.format_cancel_batch_success(cancelled, snaps))
        if cancel_misses:
            parts.extend(cancel_misses)
        if parsed.line_errors:
            parts.append(
                formatter.format_line_errors(
                    [(e.line_no, e.raw, e.error or "錯誤") for e in parsed.line_errors]
                )
            )

        if not parts:
            return None
        return formatter.truncate_reply("\n\n".join(parts))

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
            to_date = None
            if command.days is not None:
                # 查詢 7 = today .. today+6 (7 days inclusive)
                to_date = today + timedelta(days=command.days - 1)
            person = command.person_name
            if person and person in {"我", "me", "Me", "ME"}:
                person = display_name
            shifts = self.store.list_from_date(
                group_id,
                today,
                to_date=to_date,
                person_name=person,
            )
            return formatter.truncate_reply(
                formatter.format_list(
                    shifts,
                    days=command.days,
                    person_name=person,
                )
            )

        if command.type == CommandType.ADD:
            shift = self._add(command, group_id, user_id, display_name)
            day = self._shifts_on_date(group_id, shift.shift_date)
            return formatter.format_add_success(shift, day)

        if command.type == CommandType.CANCEL:
            deleted, label = self._cancel(command, group_id, user_id, display_name)
            assert command.shift_date is not None
            day = self._shifts_on_date(group_id, command.shift_date)
            if deleted is None:
                assert command.start_hour is not None
                assert command.end_hour is not None
                return formatter.format_cancel_not_found(
                    command.shift_date,
                    command.start_hour,
                    command.end_hour,
                    label,
                    day_shifts=day,
                )
            return formatter.format_cancel_success(deleted, day)

        return "無法處理此指令。"

    def _shifts_on_date(self, group_id: str, d: date) -> List[Shift]:
        return self.store.list_from_date(group_id, d, to_date=d)

    def _snapshots_for_dates(
        self, group_id: str, dates: Sequence[date]
    ) -> Dict[date, List[Shift]]:
        out: Dict[date, List[Shift]] = {}
        for d in sorted(set(dates)):
            out[d] = self._shifts_on_date(group_id, d)
        return out

    def _add(
        self,
        command: Command,
        group_id: str,
        user_id: str,
        display_name: str,
    ) -> Shift:
        assert command.shift_date is not None
        assert command.start_hour is not None
        assert command.end_hour is not None
        person = command.person_name if command.person_name else display_name
        return self.store.add_shift(
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

    def _cancel(
        self,
        command: Command,
        group_id: str,
        user_id: str,
        display_name: str,
    ) -> tuple[Optional[Shift], str]:
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
            return deleted, command.person_name

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
        return deleted, display_name
