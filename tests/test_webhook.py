"""Webhook integration-style tests (signature skipped)."""

import base64
import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LINE_CHANNEL_SECRET", "test_secret")
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "wh.db"))
    monkeypatch.setenv("SKIP_SIGNATURE_VERIFY", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)

    # Re-import app with new env
    import importlib

    import app.config as config_mod
    import app.main as main_mod
    import app.storage as storage_mod

    importlib.reload(config_mod)
    importlib.reload(storage_mod)
    importlib.reload(main_mod)

    return TestClient(main_mod.app), main_mod


def _sign(body: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(mac).decode()


def test_health(client):
    c, _ = client
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_webhook_add_and_list(client, monkeypatch):
    c, main_mod = client
    replies: list[str] = []

    def fake_reply(token: str, text: str) -> None:
        replies.append(text)

    def fake_name(user_id: str, **kwargs) -> str:
        return "Morris"

    monkeypatch.setattr(main_mod.line, "reply_text", fake_reply)
    monkeypatch.setattr(main_mod.line, "get_display_name", fake_name)

    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "tok1",
                "source": {
                    "type": "group",
                    "groupId": "G1",
                    "userId": "U1",
                },
                "message": {"type": "text", "text": "7/25 9-13"},
            }
        ]
    }
    r = c.post("/webhook", json=payload)
    assert r.status_code == 200
    assert any("已新增" in t for t in replies)

    replies.clear()
    payload["events"][0]["message"]["text"] = "查詢"
    payload["events"][0]["replyToken"] = "tok2"
    r = c.post("/webhook", json=payload)
    assert r.status_code == 200
    assert any("Morris" in t for t in replies)


def test_webhook_translate(client, monkeypatch):
    c, main_mod = client
    replies: list[str] = []
    monkeypatch.setattr(main_mod.line, "reply_text", lambda token, text: replies.append(text))
    monkeypatch.setattr(
        main_mod,
        "_start_translation",
        lambda token, command: main_mod._reply_translation(token, command),
    )

    def fake_translate(text: str, target=None):
        assert text == "早安"
        assert target is None
        return "Selamat pagi", "id"

    monkeypatch.setattr(main_mod.translator, "translate", fake_translate)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "tok-tr",
                "source": {"type": "group", "groupId": "G1", "userId": "U1"},
                "message": {"type": "text", "text": "翻譯 早安"},
            }
        ]
    }
    r = c.post("/webhook", json=payload)
    assert r.status_code == 200
    assert replies == ["Bahasa Indonesia:\nSelamat pagi"]


def test_webhook_ask(client, monkeypatch):
    c, main_mod = client
    replies: list[str] = []
    monkeypatch.setattr(main_mod.line, "reply_text", lambda token, text: replies.append(text))
    monkeypatch.setattr(
        main_mod,
        "_start_ask",
        lambda token, command: main_mod._reply_ask(token, command),
    )

    def fake_ask(text: str) -> str:
        assert text == "台北現在幾點"
        return "下午三點。"

    monkeypatch.setattr(main_mod.assistant, "ask", fake_ask)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "tok-ask",
                "source": {"type": "group", "groupId": "G1", "userId": "U1"},
                "message": {"type": "text", "text": "機器人 台北現在幾點"},
            }
        ]
    }
    r = c.post("/webhook", json=payload)
    assert r.status_code == 200
    assert replies == ["下午三點。"]


def test_webhook_audio(client, monkeypatch):
    c, main_mod = client
    replies: list[str] = []
    monkeypatch.setattr(main_mod.line, "reply_text", lambda token, text: replies.append(text))
    monkeypatch.setattr(main_mod.line, "get_message_content", lambda message_id: b"audio-bytes")
    monkeypatch.setattr(
        main_mod.line,
        "get_display_name",
        lambda user_id, group_id=None, room_id=None: "Kelly",
    )
    monkeypatch.setattr(
        main_mod,
        "_start_audio",
        lambda *args: main_mod._reply_audio(*args),
    )

    def fake_transcribe(audio, filename="voice.m4a"):
        assert audio == b"audio-bytes"
        return "明天早上九點見", "zh"

    monkeypatch.setattr(main_mod.transcriber, "transcribe", fake_transcribe)
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "tok-audio",
                "source": {"type": "group", "groupId": "G1", "userId": "U1"},
                "message": {
                    "type": "audio",
                    "id": "m1",
                    "duration": 3000,
                    "contentProvider": {"type": "line"},
                },
            }
        ]
    }
    r = c.post("/webhook", json=payload)
    assert r.status_code == 200
    assert replies == ["語音 Kelly\n明天早上九點見"]


def test_webhook_audio_too_long(client, monkeypatch):
    c, main_mod = client
    replies: list[str] = []
    monkeypatch.setattr(main_mod.line, "reply_text", lambda token, text: replies.append(text))
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "tok-long",
                "source": {"type": "group", "groupId": "G1", "userId": "U1"},
                "message": {"type": "audio", "id": "m2", "duration": 11 * 60 * 1000},
            }
        ]
    }
    r = c.post("/webhook", json=payload)
    assert r.status_code == 200
    assert len(replies) == 1
    assert "10 分鐘" in replies[0]


def test_webhook_ignores_chat(client, monkeypatch):
    c, main_mod = client
    called = []

    monkeypatch.setattr(
        main_mod.line, "reply_text", lambda *a, **k: called.append(1)
    )
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "tok",
                "source": {"type": "group", "groupId": "G1", "userId": "U1"},
                "message": {"type": "text", "text": "大家好"},
            }
        ]
    }
    r = c.post("/webhook", json=payload)
    assert r.status_code == 200
    assert called == []


def test_webhook_multi_line_add(client, monkeypatch):
    c, main_mod = client
    replies: list[str] = []
    monkeypatch.setattr(main_mod.line, "reply_text", lambda t, text: replies.append(text))
    monkeypatch.setattr(main_mod.line, "get_display_name", lambda *a, **k: "Admin")

    text = "7/21 9-12 Morris\n7/22 9-21 Kelly\n7/23 13-21 Annie"
    payload = {
        "events": [
            {
                "type": "message",
                "replyToken": "tok-ml",
                "source": {"type": "group", "groupId": "G1", "userId": "U1"},
                "message": {"type": "text", "text": text},
            }
        ]
    }
    r = c.post("/webhook", json=payload)
    assert r.status_code == 200
    assert any("已新增 3 筆" in t for t in replies)


def test_invalid_signature_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_SECRET", "test_secret")
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "sig.db"))
    monkeypatch.setenv("SKIP_SIGNATURE_VERIFY", "false")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    import importlib

    import app.config as config_mod
    import app.main as main_mod
    import app.storage as storage_mod

    importlib.reload(config_mod)
    importlib.reload(storage_mod)
    importlib.reload(main_mod)
    c = TestClient(main_mod.app)

    body = json.dumps({"events": []}).encode()
    r = c.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Line-Signature": "invalid",
        },
    )
    assert r.status_code == 400
