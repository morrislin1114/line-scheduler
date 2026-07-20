"""Application configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TAIPEI_TZ = "Asia/Taipei"


@dataclass(frozen=True)
class Settings:
    line_channel_secret: str
    line_channel_access_token: str
    database_path: Path
    skip_signature_verify: bool = False


def get_settings() -> Settings:
    secret = os.getenv("LINE_CHANNEL_SECRET", "").strip()
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    db = os.getenv("DATABASE_PATH", "./data/shifts.db").strip()
    skip = os.getenv("SKIP_SIGNATURE_VERIFY", "").lower() in {"1", "true", "yes"}
    return Settings(
        line_channel_secret=secret,
        line_channel_access_token=token,
        database_path=Path(db),
        skip_signature_verify=skip,
    )
