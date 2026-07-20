"""LINE Messaging API helpers: signature, reply, profile."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

LINE_API_BASE = "https://api.line.me/v2/bot"


class LineClient:
    def __init__(self, channel_secret: str, channel_access_token: str) -> None:
        self.channel_secret = channel_secret
        self.channel_access_token = channel_access_token

    def verify_signature(self, body: bytes, signature: str) -> bool:
        if not self.channel_secret or not signature:
            return False
        mac = hmac.new(
            self.channel_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).digest()
        expected = base64.b64encode(mac).decode("utf-8")
        return hmac.compare_digest(expected, signature)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.channel_access_token}",
            "Content-Type": "application/json",
        }

    def reply_text(self, reply_token: str, text: str) -> None:
        if not reply_token:
            logger.warning("Empty reply_token; skip reply")
            return
        payload = {
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text}],
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    f"{LINE_API_BASE}/message/reply",
                    headers=self._headers(),
                    json=payload,
                )
                if resp.status_code >= 400:
                    logger.error(
                        "LINE reply failed: %s %s", resp.status_code, resp.text
                    )
        except httpx.HTTPError as exc:
            logger.exception("LINE reply request error: %s", exc)

    def get_display_name(
        self,
        user_id: str,
        *,
        group_id: Optional[str] = None,
        room_id: Optional[str] = None,
    ) -> str:
        """Fetch display name; fall back to short user id on failure."""
        url: Optional[str] = None
        if group_id:
            url = f"{LINE_API_BASE}/group/{group_id}/member/{user_id}"
        elif room_id:
            url = f"{LINE_API_BASE}/room/{room_id}/member/{user_id}"
        else:
            url = f"{LINE_API_BASE}/profile/{user_id}"

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, headers=self._headers())
                if resp.status_code == 200:
                    data: Dict[str, Any] = resp.json()
                    name = (data.get("displayName") or "").strip()
                    if name:
                        return name
                else:
                    logger.warning(
                        "get profile failed: %s %s", resp.status_code, resp.text
                    )
        except httpx.HTTPError as exc:
            logger.exception("get profile error: %s", exc)

        suffix = user_id[-4:] if user_id else "????"
        return f"User-{suffix}"
