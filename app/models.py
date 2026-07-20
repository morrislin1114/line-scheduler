"""Domain models and command types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Optional


class CommandType(str, Enum):
    LIST = "list"
    HELP = "help"
    ADD = "add"
    CANCEL = "cancel"


@dataclass(frozen=True)
class Command:
    type: CommandType
    shift_date: Optional[date] = None
    start_hour: Optional[int] = None
    end_hour: Optional[int] = None
    person_name: Optional[str] = None  # None means "self"


@dataclass(frozen=True)
class Shift:
    id: int
    group_id: str
    shift_date: date
    start_hour: int
    end_hour: int
    person_name: str
    created_by_user_id: str
    created_by_name: str
    created_at: datetime


@dataclass(frozen=True)
class NewShift:
    group_id: str
    shift_date: date
    start_hour: int
    end_hour: int
    person_name: str
    created_by_user_id: str
    created_by_name: str
