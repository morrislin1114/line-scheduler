"""SQLite persistence for shifts."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional

from app.models import NewShift, Shift


class ShiftStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shifts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    shift_date TEXT NOT NULL,
                    start_hour INTEGER NOT NULL,
                    end_hour INTEGER NOT NULL,
                    person_name TEXT NOT NULL,
                    created_by_user_id TEXT NOT NULL,
                    created_by_name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_shifts_group_date
                ON shifts (group_id, shift_date)
                """
            )

    @staticmethod
    def _row_to_shift(row: sqlite3.Row) -> Shift:
        return Shift(
            id=row["id"],
            group_id=row["group_id"],
            shift_date=date.fromisoformat(row["shift_date"]),
            start_hour=row["start_hour"],
            end_hour=row["end_hour"],
            person_name=row["person_name"],
            created_by_user_id=row["created_by_user_id"],
            created_by_name=row["created_by_name"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def add_shift(self, shift: NewShift) -> Shift:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO shifts (
                    group_id, shift_date, start_hour, end_hour,
                    person_name, created_by_user_id, created_by_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    shift.group_id,
                    shift.shift_date.isoformat(),
                    shift.start_hour,
                    shift.end_hour,
                    shift.person_name,
                    shift.created_by_user_id,
                    shift.created_by_name,
                    created_at,
                ),
            )
            shift_id = int(cur.lastrowid)
            row = conn.execute(
                "SELECT * FROM shifts WHERE id = ?", (shift_id,)
            ).fetchone()
        return self._row_to_shift(row)

    def list_from_date(self, group_id: str, from_date: date) -> List[Shift]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM shifts
                WHERE group_id = ? AND shift_date >= ?
                ORDER BY shift_date ASC, start_hour ASC, end_hour ASC,
                         person_name ASC, id ASC
                """,
                (group_id, from_date.isoformat()),
            ).fetchall()
        return [self._row_to_shift(r) for r in rows]

    def delete_latest(
        self,
        group_id: str,
        shift_date: date,
        start_hour: int,
        end_hour: int,
        *,
        person_name: Optional[str] = None,
        created_by_user_id: Optional[str] = None,
    ) -> Optional[Shift]:
        """Delete the latest matching shift. Prefer user_id when person_name is None."""
        with self._conn() as conn:
            if person_name is not None:
                row = conn.execute(
                    """
                    SELECT * FROM shifts
                    WHERE group_id = ?
                      AND shift_date = ?
                      AND start_hour = ?
                      AND end_hour = ?
                      AND LOWER(person_name) = LOWER(?)
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (
                        group_id,
                        shift_date.isoformat(),
                        start_hour,
                        end_hour,
                        person_name,
                    ),
                ).fetchone()
            elif created_by_user_id is not None:
                row = conn.execute(
                    """
                    SELECT * FROM shifts
                    WHERE group_id = ?
                      AND shift_date = ?
                      AND start_hour = ?
                      AND end_hour = ?
                      AND created_by_user_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (
                        group_id,
                        shift_date.isoformat(),
                        start_hour,
                        end_hour,
                        created_by_user_id,
                    ),
                ).fetchone()
            else:
                return None

            if row is None:
                return None

            shift = self._row_to_shift(row)
            conn.execute("DELETE FROM shifts WHERE id = ?", (shift.id,))
            return shift

    def delete_latest_by_person_name(
        self,
        group_id: str,
        shift_date: date,
        start_hour: int,
        end_hour: int,
        person_name: str,
    ) -> Optional[Shift]:
        return self.delete_latest(
            group_id,
            shift_date,
            start_hour,
            end_hour,
            person_name=person_name,
        )
