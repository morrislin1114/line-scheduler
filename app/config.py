"""Application configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

TAIPEI_TZ = "Asia/Taipei"


@dataclass(frozen=True)
class Settings:
    line_channel_secret: str
    line_channel_access_token: str
    database_url: Optional[str]  # Postgres (Neon etc.); preferred when set
    database_path: Path  # SQLite fallback for local
    skip_signature_verify: bool = False

    @property
    def db_backend(self) -> str:
        return "postgres" if self.database_url else "sqlite"


def get_settings() -> Settings:
    secret = os.getenv("LINE_CHANNEL_SECRET", "").strip()
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    # Prefer DATABASE_URL (Postgres). Fall back to SQLite path.
    database_url = (
        os.getenv("DATABASE_URL", "").strip()
        or os.getenv("POSTGRES_URL", "").strip()
        or None
    )
    db_path = os.getenv("DATABASE_PATH", "./data/shifts.db").strip()
    skip = os.getenv("SKIP_SIGNATURE_VERIFY", "").lower() in {"1", "true", "yes"}
    return Settings(
        line_channel_secret=secret,
        line_channel_access_token=token,
        database_url=database_url,
        database_path=Path(db_path),
        skip_signature_verify=skip,
    )
