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

    # Re-import app with new env
    import importlib

    import app.config as config_mod
    import app.main as main_mod

    importlib.reload(config_mod)
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


def test_invalid_signature_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LINE_CHANNEL_SECRET", "test_secret")
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "test_token")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "sig.db"))
    monkeypatch.setenv("SKIP_SIGNATURE_VERIFY", "false")

    import importlib

    import app.config as config_mod
    import app.main as main_mod

    importlib.reload(config_mod)
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
