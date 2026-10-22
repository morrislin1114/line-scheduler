"""Voice transcription client and reply formatting."""

import httpx
import pytest

from app.transcriber import (
    TranscribeError,
    Transcriber,
    transcript_reply,
    transcribe_failure_reply,
)


def test_transcript_reply_languages():
    assert transcript_reply("Kelly", "明天早上九點見", "zh") == "語音 Kelly\n明天早上九點見"
    assert (
        transcript_reply("Siti", "Besok masuk jam 9", "id")
        == "Suara Siti\nBesok masuk jam 9"
    )
    assert transcript_reply("Kelly", "  ", "zh") == "這段錄音沒有聽出文字。"
    assert transcript_reply("", "halo", "id-ID") == "Suara\nhalo"


def test_failure_replies():
    assert "XAI_API_KEY" in transcribe_failure_reply("no_key")
    assert "10 分鐘" in transcribe_failure_reply("too_long")


def test_transcribe_posts_file_last(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"text": "明天九點見", "language": "zh", "duration": 2.0}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers, files):
            captured["url"] = url
            captured["headers"] = headers
            captured["files"] = files
            return FakeResponse()

    monkeypatch.setattr("app.transcriber.httpx.Client", FakeClient)
    text, language = Transcriber("secret-key").transcribe(b"fake-m4a")
    assert text == "明天九點見"
    assert language == "zh"
    assert captured["url"].endswith("/v1/stt")
    assert captured["headers"]["Authorization"] == "Bearer secret-key"
    assert captured["files"][0][0] == "model"
    assert captured["files"][0][1][1] == "grok-voice-transcribe-2.0"
    assert captured["files"][-1][0] == "file"
    assert captured["files"][-1][1][0] == "voice.m4a"
    assert captured["files"][-1][1][1] == b"fake-m4a"


def test_transcribe_requires_key():
    with pytest.raises(TranscribeError) as exc:
        Transcriber("").transcribe(b"abc")
    assert exc.value.code == "no_key"


def test_transcribe_timeout(monkeypatch: pytest.MonkeyPatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers, files):
            raise httpx.TimeoutException("timed out")

    monkeypatch.setattr("app.transcriber.httpx.Client", FakeClient)
    with pytest.raises(TranscribeError) as exc:
        Transcriber("secret-key").transcribe(b"abc")
    assert exc.value.code == "api"