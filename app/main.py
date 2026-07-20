"""FastAPI entrypoint: LINE webhook + health check."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Request, Response

from app.config import get_settings
from app.line_client import LineClient
from app.parser import parse_command
from app.service import ScheduleService
from app.storage import ShiftStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()
store = ShiftStore(settings.database_path)
line = LineClient(
    channel_secret=settings.line_channel_secret,
    channel_access_token=settings.line_channel_access_token,
)
service = ScheduleService(store)

app = FastAPI(title="LINE Shift Scheduler", version="1.0.0")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(
    request: Request,
    x_line_signature: Optional[str] = Header(default=None, alias="X-Line-Signature"),
) -> Response:
    body = await request.body()

    if not settings.skip_signature_verify:
        if not x_line_signature or not line.verify_signature(body, x_line_signature):
            raise HTTPException(status_code=400, detail="Invalid signature")
    elif not settings.line_channel_secret:
        logger.warning("SKIP_SIGNATURE_VERIFY enabled; do not use in production")

    try:
        payload: Dict[str, Any] = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    events = payload.get("events") or []
    for event in events:
        try:
            _handle_event(event)
        except Exception:
            logger.exception("Failed to handle event: %s", event)

    return Response(content="OK", media_type="text/plain")


def _handle_event(event: Dict[str, Any]) -> None:
    if event.get("type") != "message":
        return
    message = event.get("message") or {}
    if message.get("type") != "text":
        return

    text = (message.get("text") or "").strip()
    reply_token = event.get("replyToken") or ""
    source = event.get("source") or {}
    source_type = source.get("type")
    user_id = source.get("userId") or ""

    # group / room / user (1:1 for testing)
    if source_type == "group":
        group_id = source.get("groupId") or ""
        room_id = None
    elif source_type == "room":
        group_id = source.get("roomId") or ""
        room_id = source.get("roomId")
    elif source_type == "user":
        group_id = f"user:{user_id}"
        room_id = None
    else:
        return

    if not group_id:
        return

    try:
        command = parse_command(text)
    except ValueError as exc:
        line.reply_text(reply_token, f"⚠️ {exc}")
        return

    if command is None:
        # Not a bot command — stay silent in group chats
        return

    display_name = line.get_display_name(
        user_id,
        group_id=source.get("groupId") if source_type == "group" else None,
        room_id=room_id if source_type == "room" else None,
    )

    reply = service.handle(
        command,
        group_id=group_id,
        user_id=user_id,
        display_name=display_name,
    )
    line.reply_text(reply_token, reply)
