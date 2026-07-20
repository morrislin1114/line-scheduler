"""FastAPI entrypoint: LINE webhook + health check."""

from __future__ import annotations

import json
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
if not settings.line_channel_secret:
    logger.error("LINE_CHANNEL_SECRET is empty — webhook signature will fail")
if not settings.line_channel_access_token:
    logger.error("LINE_CHANNEL_ACCESS_TOKEN is empty — replies will fail")

store = ShiftStore(settings.database_path)
line = LineClient(
    channel_secret=settings.line_channel_secret,
    channel_access_token=settings.line_channel_access_token,
)
service = ScheduleService(store)

app = FastAPI(title="LINE Shift Scheduler", version="1.0.0")


@app.get("/health")
def health() -> Dict[str, str]:
    return {
        "status": "ok",
        "has_secret": str(bool(settings.line_channel_secret)).lower(),
        "has_token": str(bool(settings.line_channel_access_token)).lower(),
    }


@app.post("/webhook")
async def webhook(
    request: Request,
    x_line_signature: Optional[str] = Header(default=None, alias="X-Line-Signature"),
) -> Response:
    body = await request.body()
    logger.info("Webhook hit: %d bytes, signature=%s", len(body), bool(x_line_signature))

    if not settings.skip_signature_verify:
        if not x_line_signature or not line.verify_signature(body, x_line_signature):
            logger.warning("Invalid LINE signature — check LINE_CHANNEL_SECRET")
            raise HTTPException(status_code=400, detail="Invalid signature")
    elif not settings.line_channel_secret:
        logger.warning("SKIP_SIGNATURE_VERIFY enabled; do not use in production")

    try:
        payload: Dict[str, Any] = json.loads(body.decode("utf-8") or "{}")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    events = payload.get("events") or []
    logger.info("Webhook events: %d", len(events))
    for event in events:
        try:
            _handle_event(event)
        except Exception:
            logger.exception("Failed to handle event: %s", event)

    return Response(content="OK", media_type="text/plain")


def _handle_event(event: Dict[str, Any]) -> None:
    event_type = event.get("type")
    mode = event.get("mode")  # "active" can reply; "standby" has no usable reply
    logger.info(
        "Event type=%s mode=%s source=%s",
        event_type,
        mode,
        (event.get("source") or {}).get("type"),
    )

    if mode == "standby":
        logger.warning(
            "Event is standby (no reply). In LINE OA Manager: turn off Chat, "
            "use Bot response mode; disable conflicting extensions."
        )
        return

    if event_type != "message":
        return
    message = event.get("message") or {}
    if message.get("type") != "text":
        return

    text = (message.get("text") or "").strip()
    reply_token = event.get("replyToken") or ""
    source = event.get("source") or {}
    source_type = source.get("type")
    user_id = source.get("userId") or ""

    logger.info("Text from %s: %r", source_type, text[:80])

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
        logger.warning("Unsupported source type: %s", source_type)
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
        logger.info("Ignored non-command text")
        return

    if not reply_token:
        logger.error("Missing replyToken; cannot reply")
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
    logger.info("Replying (%d chars) as command=%s", len(reply), command.type)
    line.reply_text(reply_token, reply)
