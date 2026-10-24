"""FastAPI entrypoint: LINE webhook + health check."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Request, Response

from app.assistant import Assistant, ask_reply
from app.config import get_settings
from app.line_client import LineClient
from app.models import Command, CommandType
from app.parser import parse_message
from app.service import ScheduleService
from app.storage import ShiftStore
from app.transcriber import (
    MAX_AUDIO_MS,
    TranscribeError,
    Transcriber,
    transcript_reply,
    transcribe_failure_reply,
)
from app.translator import Translator, translation_reply

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
if not settings.xai_api_key:
    logger.warning(
        "XAI_API_KEY is empty — 翻譯, 機器人, and voice transcription will be unavailable"
    )

store = ShiftStore(
    settings.database_path,
    database_url=settings.database_url,
)
line = LineClient(
    channel_secret=settings.line_channel_secret,
    channel_access_token=settings.line_channel_access_token,
)
service = ScheduleService(store)
translator = Translator(
    api_key=settings.xai_api_key,
    model=settings.xai_model,
)
assistant = Assistant(
    api_key=settings.xai_api_key,
    model=settings.xai_model,
)
transcriber = Transcriber(api_key=settings.xai_api_key)

app = FastAPI(title="LINE Shift Scheduler", version="1.2.0")


@app.get("/health")
def health() -> Dict[str, str]:
    db_ok = store.ping()
    return {
        "status": "ok" if db_ok else "degraded",
        "db": settings.db_backend,
        "db_ok": str(db_ok).lower(),
        "has_secret": str(bool(settings.line_channel_secret)).lower(),
        "has_token": str(bool(settings.line_channel_access_token)).lower(),
        "has_xai_key": str(bool(settings.xai_api_key)).lower(),
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


def _reply_translation(reply_token: str, command: Command) -> None:
    try:
        reply = translation_reply(command, translator)
        logger.info("Replying translation (%d chars)", len(reply))
        line.reply_text(reply_token, reply)
    except Exception:
        logger.exception("Translation reply failed")


def _start_translation(reply_token: str, command: Command) -> None:
    threading.Thread(
        target=_reply_translation,
        args=(reply_token, command),
        daemon=True,
    ).start()


def _reply_ask(reply_token: str, command: Command) -> None:
    try:
        reply = ask_reply(command, assistant)
        logger.info("Replying ask (%d chars)", len(reply))
        line.reply_text(reply_token, reply)
    except Exception:
        logger.exception("Ask reply failed")


def _start_ask(reply_token: str, command: Command) -> None:
    threading.Thread(
        target=_reply_ask,
        args=(reply_token, command),
        daemon=True,
    ).start()


def _reply_audio(
    reply_token: str,
    message_id: str,
    user_id: str,
    group_id: str,
    room_id: Optional[str],
    source_type: str,
) -> None:
    try:
        audio = line.get_message_content(message_id)
        text, language = transcriber.transcribe(audio)
        name = line.get_display_name(
            user_id,
            group_id=group_id if source_type == "group" else None,
            room_id=room_id if source_type == "room" else None,
        )
        reply = transcript_reply(name, text, language)
    except TranscribeError as exc:
        logger.warning("transcribe failed: %s", exc.code)
        reply = transcribe_failure_reply(exc.code)
    except Exception:
        logger.exception("Voice transcription failed")
        reply = transcribe_failure_reply("download")
    line.reply_text(reply_token, reply)


def _start_audio(
    reply_token: str,
    message_id: str,
    user_id: str,
    group_id: str,
    room_id: Optional[str],
    source_type: str,
) -> None:
    threading.Thread(
        target=_reply_audio,
        args=(reply_token, message_id, user_id, group_id, room_id, source_type),
        daemon=True,
    ).start()


def _handle_audio(event: Dict[str, Any]) -> None:
    message = event.get("message") or {}
    reply_token = event.get("replyToken") or ""
    if not reply_token:
        logger.error("Missing replyToken; cannot reply")
        return

    source = event.get("source") or {}
    source_type = source.get("type")
    user_id = source.get("userId") or ""
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

    provider = (message.get("contentProvider") or {}).get("type") or "line"
    if provider != "line":
        line.reply_text(reply_token, transcribe_failure_reply("external"))
        return

    duration = message.get("duration")
    if isinstance(duration, int) and duration > MAX_AUDIO_MS:
        line.reply_text(reply_token, transcribe_failure_reply("too_long"))
        return

    message_id = str(message.get("id") or "")
    if not message_id:
        line.reply_text(reply_token, transcribe_failure_reply("download"))
        return

    # Return 200 before download and transcription so LINE does not retry.
    _start_audio(reply_token, message_id, user_id, group_id, room_id, source_type)


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
    if message.get("type") == "audio":
        _handle_audio(event)
        return
    if message.get("type") != "text":
        return

    text = (message.get("text") or "").strip()
    reply_token = event.get("replyToken") or ""
    source = event.get("source") or {}
    source_type = source.get("type")
    user_id = source.get("userId") or ""

    preview = text.replace("\n", "\\n")[:120]
    logger.info("Text from %s: %r", source_type, preview)

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

    parsed = parse_message(text)
    if parsed.ignore:
        logger.info("Ignored non-command text")
        return

    if (
        len(parsed.commands) == 1
        and not parsed.line_errors
        and parsed.commands[0].type in {CommandType.TRANSLATE, CommandType.ASK}
    ):
        if not reply_token:
            logger.error("Missing replyToken; cannot reply")
            return
        # Return 200 before the model responds so LINE does not retry the webhook.
        command = parsed.commands[0]
        if command.type == CommandType.TRANSLATE:
            _start_translation(reply_token, command)
        else:
            _start_ask(reply_token, command)
        return

    if not reply_token:
        logger.error("Missing replyToken; cannot reply")
        return

    display_name = line.get_display_name(
        user_id,
        group_id=source.get("groupId") if source_type == "group" else None,
        room_id=room_id if source_type == "room" else None,
    )

    reply = service.handle_message(
        parsed,
        group_id=group_id,
        user_id=user_id,
        display_name=display_name,
    )
    if not reply:
        logger.info("No reply content")
        return

    logger.info("Replying (%d chars)", len(reply))
    line.reply_text(reply_token, reply)
