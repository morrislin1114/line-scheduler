"""Shift persistence: PostgreSQL (DATABASE_URL) or SQLite fallback."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator, List, Optional, Sequence, Union

from app.models import NewShift, Shift

logger = logging.getLogger(__name__)


class ShiftStore:
    """
    Unified store.

    - If database_url is set → PostgreSQL (Neon / Supabase / Render Postgres)
    - Else → SQLite at database_path (local / simple deploy)
    """

    def __init__(
        self,
        database_path: Optional[Union[Path, str]] = None,
        *,
        database_url: Optional[str] = None,
    ) -> None:
        self.database_url = (database_url or "").strip() or None
        self.db_path = Path(database_path) if database_path else Path("./data/shifts.db")
        self.backend = "postgres" if self.database_url else "sqlite"
        if self.backend == "sqlite":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        logger.info("ShiftStore backend=%s", self.backend)

    def _ph(self) -> str:
        """SQL placeholder for current backend."""
        return "%s" if self.backend == "postgres" else "?"

    @contextmanager
    def _conn(self) -> Iterator[Any]:
        if self.backend == "postgres":
            import psycopg
            from psycopg.rows import dict_row

            conn = psycopg.connect(self.database_url, row_factory=dict_row)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        else:
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
            if self.backend == "postgres":
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS shifts (
                        id BIGSERIAL PRIMARY KEY,
                        group_id TEXT NOT NULL,
                        shift_date DATE NOT NULL,
                        start_hour INTEGER NOT NULL,
                        end_hour INTEGER NOT NULL,
                        person_name TEXT NOT NULL,
                        created_by_user_id TEXT NOT NULL,
                        created_by_name TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_shifts_group_date
                    ON shifts (group_id, shift_date)
                    """
                )
            else:
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

    def _row_to_shift(self, row: Any) -> Shift:
        if self.backend == "postgres":
            data = dict(row)
            shift_date = data["shift_date"]
            if isinstance(shift_date, str):
                shift_date = date.fromisoformat(shift_date)
            created_at = data["created_at"]
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
        else:
            data = dict(row)
            shift_date = date.fromisoformat(data["shift_date"])
            created_at = datetime.fromisoformat(data["created_at"])

        return Shift(
            id=int(data["id"]),
            group_id=data["group_id"],
            shift_date=shift_date,
            start_hour=int(data["start_hour"]),
            end_hour=int(data["end_hour"]),
            person_name=data["person_name"],
            created_by_user_id=data["created_by_user_id"],
            created_by_name=data["created_by_name"],
            created_at=created_at,
        )

    def _execute(self, conn: Any, sql: str, params: Sequence[Any] = ()) -> Any:
        if self.backend == "postgres":
            return conn.execute(sql, params)
        return conn.execute(sql, params)

    def add_shift(self, shift: NewShift) -> Shift:
        created_at = datetime.now(timezone.utc)
        ph = self._ph()
        cols = (
            "group_id, shift_date, start_hour, end_hour, "
            "person_name, created_by_user_id, created_by_name, created_at"
        )
        placeholders = ", ".join([ph] * 8)
        date_val: Any = (
            shift.shift_date if self.backend == "postgres" else shift.shift_date.isoformat()
        )
        created_val: Any = (
            created_at if self.backend == "postgres" else created_at.isoformat()
        )
        params = (
            shift.group_id,
            date_val,
            shift.start_hour,
            shift.end_hour,
            shift.person_name,
            shift.created_by_user_id,
            shift.created_by_name,
            created_val,
        )

        with self._conn() as conn:
            if self.backend == "postgres":
                row = self._execute(
                    conn,
                    f"""
                    INSERT INTO shifts ({cols})
                    VALUES ({placeholders})
                    RETURNING *
                    """,
                    params,
                ).fetchone()
                return self._row_to_shift(row)

            cur = self._execute(
                conn,
                f"INSERT INTO shifts ({cols}) VALUES ({placeholders})",
                params,
            )
            shift_id = int(cur.lastrowid)
            row = self._execute(
                conn, f"SELECT * FROM shifts WHERE id = {ph}", (shift_id,)
            ).fetchone()
            return self._row_to_shift(row)

    def list_from_date(self, group_id: str, from_date: date) -> List[Shift]:
        ph = self._ph()
        date_val: Any = from_date if self.backend == "postgres" else from_date.isoformat()
        with self._conn() as conn:
            rows = self._execute(
                conn,
                f"""
                SELECT * FROM shifts
                WHERE group_id = {ph} AND shift_date >= {ph}
                ORDER BY shift_date ASC, start_hour ASC, end_hour ASC,
                         person_name ASC, id ASC
                """,
                (group_id, date_val),
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
        """Delete the latest matching shift."""
        ph = self._ph()
        date_val: Any = (
            shift_date if self.backend == "postgres" else shift_date.isoformat()
        )

        with self._conn() as conn:
            if person_name is not None:
                row = self._execute(
                    conn,
                    f"""
                    SELECT * FROM shifts
                    WHERE group_id = {ph}
                      AND shift_date = {ph}
                      AND start_hour = {ph}
                      AND end_hour = {ph}
                      AND LOWER(person_name) = LOWER({ph})
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (group_id, date_val, start_hour, end_hour, person_name),
                ).fetchone()
            elif created_by_user_id is not None:
                row = self._execute(
                    conn,
                    f"""
                    SELECT * FROM shifts
                    WHERE group_id = {ph}
                      AND shift_date = {ph}
                      AND start_hour = {ph}
                      AND end_hour = {ph}
                      AND created_by_user_id = {ph}
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (group_id, date_val, start_hour, end_hour, created_by_user_id),
                ).fetchone()
            else:
                return None

            if row is None:
                return None

            shift = self._row_to_shift(row)
            self._execute(
                conn, f"DELETE FROM shifts WHERE id = {ph}", (shift.id,)
            )
            return shift

    def ping(self) -> bool:
        """Return True if DB is reachable."""
        try:
            with self._conn() as conn:
                if self.backend == "postgres":
                    conn.execute("SELECT 1")
                else:
                    conn.execute("SELECT 1")
            return True
        except Exception:
            logger.exception("DB ping failed")
            return False
