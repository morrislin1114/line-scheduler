"""Turn LINE voice messages into text via the xAI Speech to Text API."""

from __future__ import annotations

import logging
from typing import Any, Tuple

import httpx

from app.formatter import truncate_reply

logger = logging.getLogger(__name__)

_traditional = None

XAI_STT_URL = "https://api.x.ai/v1/stt"
STT_MODEL = "grok-voice-transcribe-2.0"
# LINE voice notes are short. Cap so a long clip cannot hold the reply open.
MAX_AUDIO_MS = 10 * 60 * 1000
MAX_AUDIO_BYTES = 20 * 1024 * 1024


class TranscribeError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


class Transcriber:
    def __init__(
        self,
        api_key: str,
        model: str = STT_MODEL,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model.strip() or STT_MODEL
        self.timeout = timeout

    def transcribe(self, audio: bytes, filename: str = "voice.m4a") -> Tuple[str, str]:
        """
        Transcribe audio bytes.

        Returns (text, language code). Language is a BCP-47 code such as "zh" or "id".
        Language is left unset on the request so Chinese and Indonesian are both detected.
        """
        if not self.api_key:
            raise TranscribeError("no_key", "XAI_API_KEY is empty")
        if not audio:
            raise TranscribeError("empty", "empty audio")
        if len(audio) > MAX_AUDIO_BYTES:
            raise TranscribeError("too_big", "audio too large")

        # file must be the last multipart field.
        form = [
            ("model", (None, self.model)),
            ("file", (filename, audio, "audio/mp4")),
        ]
        try:
            with httpx.Client(timeout=httpx.Timeout(self.timeout, connect=5.0)) as client:
                resp = client.post(
                    XAI_STT_URL,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files=form,
                )
        except httpx.HTTPError as exc:
            raise TranscribeError("api", str(exc)) from exc

        if resp.status_code >= 400:
            logger.error("xAI stt failed: %s %s", resp.status_code, resp.text[:300])
            raise TranscribeError("api", f"{resp.status_code}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise TranscribeError("api", "invalid json") from exc

        text, language = _extract_transcript(data)
        if _is_chinese(language):
            text = to_traditional(text)
        return text, language


def to_traditional(text: str) -> str:
    """Simplified Chinese to Traditional Chinese used in Taiwan, including phrases."""
    global _traditional
    if _traditional is None:
        import opencc

        _traditional = opencc.OpenCC("s2twp")
    return _traditional.convert(text)


def _is_chinese(language: str) -> bool:
    lang = language.lower().replace("_", "-")
    return lang.startswith("zh") or lang.startswith("cmn") or lang.startswith("yue")


def transcript_reply(name: str, text: str, language: str) -> str:
    """LINE reply for a finished transcript."""
    indonesian = language.lower().startswith("id")
    cleaned = to_traditional(text.strip()) if _is_chinese(language) else text.strip()
    if not cleaned:
        if indonesian:
            return "Tidak terdengar kata-kata."
        return "這段錄音沒有聽出文字。"
    header = "Suara" if indonesian else "語音"
    who = name.strip()
    body = f"{header} {who}\n{cleaned}" if who else f"{header}\n{cleaned}"
    notice = (
        "\n…(teks terpotong karena terlalu panjang)"
        if indonesian
        else "\n…（文字過長已截斷）"
    )
    return truncate_reply(body, notice=notice)


def transcribe_failure_reply(code: str, *, indonesian: bool = False) -> str:
    if code == "no_key":
        if indonesian:
            return "Ubah suara ke teks belum disiapkan. Minta admin menambahkan XAI_API_KEY."
        return "語音轉文字還沒設定。請在環境變數加入 XAI_API_KEY 後重新部署。"
    if code == "too_long":
        return "錄音超過 10 分鐘，請分成較短的語音再傳。"
    if code == "too_big":
        return "錄音檔太大，請分成較短的語音再傳。"
    if code == "download":
        return "讀不到這段錄音，請再傳一次。"
    if code == "external":
        return "這段不是 LINE 裡錄的語音，無法轉文字。"
    if indonesian:
        return "Gagal mengubah suara ke teks. Coba lagi nanti."
    return "語音轉文字失敗，請稍後再試。"


def _extract_transcript(data: Any) -> Tuple[str, str]:
    if not isinstance(data, dict):
        return "", ""
    text = data.get("text")
    language = data.get("language")
    return (
        text.strip() if isinstance(text, str) else "",
        language.strip() if isinstance(language, str) else "",
    )
