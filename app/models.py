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
    TRANSLATE = "translate"


@dataclass(frozen=True)
class Command:
    type: CommandType
    shift_date: Optional[date] = None
    start_hour: Optional[int] = None
    end_hour: Optional[int] = None
    person_name: Optional[str] = None  # None means "self" / for LIST = filter
    # LIST: rolling window (今日起 N 天); ignored if list_from is set
    days: Optional[int] = None
    # LIST: explicit date range (inclusive), e.g. 查詢 7/21 or 本週
    list_from: Optional[date] = None
    list_to: Optional[date] = None
    list_label: Optional[str] = None  # display scope, e.g. 本週 / 7/21（二）
    # TRANSLATE
    source_text: Optional[str] = None
    translate_target: Optional[str] = None  # "id" | "zh" | None (auto)
    reply_lang: Optional[str] = None  # "id" | "zh": language of the command itself


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
