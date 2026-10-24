"""Answer a LINE prompt via the xAI Responses API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.formatter import ASK_USAGE, truncate_reply
from app.models import Command
from app.translator import XAI_RESPONSES_URL, _extract_text

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "grok-4.7"
MAX_PROMPT_CHARS = 2000
# LINE reply tokens expire in about a minute, so this stays under that window.
ASK_TIMEOUT = 45.0

_SYSTEM = (
    "You are Grok, an AI agent built to answer helpful questions in a workplace "
    "LINE group. Reply in the same language as the user. Chinese must be "
    "Traditional Chinese used in Taiwan (繁體中文), not Simplified. "
    "Use plain text for LINE: no markdown tables or headings. Be direct and concise. "
    "You do not have this group's shift schedule. If asked about shifts, say to use 查詢. "
    "Each message is a new question; you have no earlier turns."
)


class AskError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class Assistant:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout: float = ASK_TIMEOUT,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model.strip() or DEFAULT_MODEL
        self.timeout = timeout

    def ask(self, text: str) -> str:
        """Send one prompt and return the answer text."""
        if not self.api_key:
            raise AskError("no_key", "XAI_API_KEY is empty")

        prompt = text.strip()
        if not prompt:
            raise AskError("empty", "empty prompt")

        payload: dict[str, Any] = {
            "model": self.model,
            "store": False,
            "reasoning": {"effort": "low"},
            "input": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt},
            ],
        }
        try:
            with httpx.Client(timeout=httpx.Timeout(self.timeout, connect=5.0)) as client:
                resp = client.post(
                    XAI_RESPONSES_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise AskError("timeout", str(exc)) from exc
        except httpx.HTTPError as exc:
            raise AskError("api", str(exc)) from exc

        if resp.status_code >= 400:
            detail = resp.text[:300]
            logger.error("xAI ask failed: %s %s", resp.status_code, detail)
            raise AskError("api", f"{resp.status_code}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise AskError("api", "invalid json") from exc

        answer = _extract_text(data)
        if not answer:
            raise AskError("api", "empty answer")
        return answer


def ask_reply(command: Command, assistant: Assistant) -> str:
    """LINE reply for a 機器人 command, including usage and errors."""
    text = (command.source_text or "").strip()
    if not text:
        return ASK_USAGE.strip()
    if len(text) > MAX_PROMPT_CHARS:
        return f"一次最多 {MAX_PROMPT_CHARS} 字，請縮短再送。"
    try:
        answer = assistant.ask(text)
    except AskError as exc:
        logger.warning("ask failed: %s", exc.code)
        if exc.code == "no_key":
            return "問答還沒設定。請在環境變數加入 XAI_API_KEY 後重新部署。"
        if exc.code == "timeout":
            return "回答逾時，請稍後再試或把問題縮短。"
        return "回答失敗，請稍後再試。"
    return truncate_reply(answer, notice="\n…（回答過長已截斷）")
