"""Chinese ↔ Indonesian translation via the xAI Responses API."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional, Tuple

import httpx

from app.formatter import TRANSLATE_USAGE, truncate_reply
from app.models import Command

logger = logging.getLogger(__name__)

XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"
DEFAULT_MODEL = "grok-4.7"
MAX_SOURCE_CHARS = 2000

_HAN_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")

_SYSTEM = (
    "You translate between Traditional Chinese used in Taiwan (繁體中文) "
    "and Indonesian (Bahasa Indonesia) for a workplace LINE group. "
    "Output only the translation. No labels, quotes, notes, or pinyin. "
    "Keep names, numbers, dates, times, and line breaks. "
    "Use natural spoken language. Chinese output must be Traditional, not Simplified."
)


class TranslateError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class Translator:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model.strip() or DEFAULT_MODEL
        self.timeout = timeout

    def translate(
        self, text: str, target: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Translate text.

        target: "id" (Indonesian), "zh" (Traditional Chinese), or None to detect.
        Returns (translation, resolved target).
        """
        if not self.api_key:
            raise TranslateError("no_key", "XAI_API_KEY is empty")

        source = text.strip()
        if not source:
            raise TranslateError("empty", "empty source")

        resolved = target if target in {"id", "zh"} else detect_target(source)
        payload = {
            "model": self.model,
            "store": False,
            "reasoning": {"effort": "low"},
            "input": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _user_prompt(source, resolved)},
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
        except httpx.HTTPError as exc:
            raise TranslateError("api", str(exc)) from exc

        if resp.status_code >= 400:
            detail = resp.text[:300]
            logger.error("xAI translate failed: %s %s", resp.status_code, detail)
            raise TranslateError("api", f"{resp.status_code}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise TranslateError("api", "invalid json") from exc

        translated = _extract_text(data)
        if not translated:
            raise TranslateError("api", "empty translation")
        return translated, resolved


def detect_target(text: str) -> str:
    """Return "id" when the text is mainly Chinese, otherwise "zh"."""
    han = len(_HAN_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    if han == 0:
        return "zh"
    if latin == 0:
        return "id"
    # One Han character carries about as much meaning as a short Latin syllable.
    if han * 2 >= latin:
        return "id"
    return "zh"


def translation_reply(command: Command, translator: Translator) -> str:
    """LINE reply for a translate command, including usage and errors."""
    text = (command.source_text or "").strip()
    if not text:
        return TRANSLATE_USAGE.strip()
    if len(text) > MAX_SOURCE_CHARS:
        return f"一次最多翻譯 {MAX_SOURCE_CHARS} 字，請分段再送。"
    try:
        translated, target = translator.translate(text, command.translate_target)
    except TranslateError as exc:
        logger.warning("translate failed: %s", exc.code)
        if exc.code == "no_key":
            return "翻譯還沒設定。請在環境變數加入 XAI_API_KEY 後重新部署。"
        return "翻譯失敗，請稍後再試。"
    if target == "id":
        label = "Bahasa Indonesia:"
        notice = "\n…(terjemahan terpotong karena terlalu panjang)"
    else:
        label = "中文："
        notice = "\n…（譯文過長已截斷）"
    return truncate_reply(f"{label}\n{translated}", notice=notice)


def _user_prompt(text: str, target: str) -> str:
    if target == "id":
        direction = "Translate the following into Indonesian (Bahasa Indonesia)."
    else:
        direction = (
            "Translate the following into Traditional Chinese used in Taiwan (繁體中文)."
        )
    return f"{direction}\n\n{text}"


def _extract_text(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    chunks = []
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content") or []
        if isinstance(content, str):
            if content.strip():
                chunks.append(content.strip())
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") in {"output_text", "text"} and part.get("text"):
                chunks.append(str(part["text"]))
    return "\n".join(chunks).strip()
