"""機器人 command parsing and xAI client behavior."""

from datetime import date

import httpx
import pytest

from app.assistant import Assistant, ask_reply
from app.models import CommandType
from app.parser import parse_command, parse_message


def test_ask_prompt():
    cmd = parse_command("機器人 台北現在幾點？")
    assert cmd is not None
    assert cmd.type == CommandType.ASK
    assert cmd.source_text == "台北現在幾點？"


def test_ask_colon_and_multiline():
    colon = parse_command("機器人：為什麼天空是藍色的？")
    assert colon is not None
    assert colon.source_text == "為什麼天空是藍色的？"

    result = parse_message("機器人\n第一行\n第二行")
    assert len(result.commands) == 1
    assert not result.line_errors
    assert result.commands[0].source_text == "第一行\n第二行"


def test_ask_alone_is_usage():
    result = parse_message("機器人")
    assert not result.ignore
    assert result.commands[0].source_text == ""
    reply = ask_reply(result.commands[0], Assistant(""))
    assert "機器人 台北現在幾點" in reply
    assert "查詢" in reply


def test_ask_without_separator_is_chat():
    assert parse_command("機器人不回") is None
    assert parse_message("機器人不回").ignore
    assert parse_message("大家好").ignore


def test_ask_does_not_steal_translate_or_schedule():
    translated = parse_command("翻譯 機器人")
    assert translated is not None
    assert translated.type == CommandType.TRANSLATE

    today = date(2026, 7, 20)
    mixed = parse_message("7/21 9-12 Morris\n機器人 天氣", today=today)
    assert len(mixed.commands) == 1
    assert mixed.commands[0].type == CommandType.ADD
    assert len(mixed.line_errors) == 1
    assert "機器人" in (mixed.line_errors[0].error or "")


def test_ask_reply_limits_and_missing_key():
    too_long = parse_command("機器人 " + ("啊" * 2001))
    assert too_long is not None
    assert "2000" in ask_reply(too_long, Assistant("key"))

    missing = parse_command("機器人 早安")
    assert missing is not None
    assert "XAI_API_KEY" in ask_reply(missing, Assistant(""))


def test_ask_reply_formats_result(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "output_text": "台北現在是下午三點。",
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.assistant.httpx.Client", FakeClient)
    cmd = parse_command("機器人 台北現在幾點")
    assert cmd is not None
    reply = ask_reply(cmd, Assistant("secret-key", model="grok-4.7"))
    assert reply == "台北現在是下午三點。"
    assert captured["url"].endswith("/v1/responses")
    assert captured["headers"]["Authorization"] == "Bearer secret-key"
    body = captured["json"]
    assert body["model"] == "grok-4.7"
    assert body["store"] is False
    assert body["reasoning"] == {"effort": "low"}
    assert body["input"][0]["role"] == "system"
    assert "Grok" in body["input"][0]["content"]
    assert body["input"][1]["content"] == "台北現在幾點"


def test_ask_api_error_and_timeout(monkeypatch: pytest.MonkeyPatch):
    class FakeResponse:
        status_code = 500
        text = "boom"

        def json(self):
            return {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers, json):
            return FakeResponse()

    monkeypatch.setattr("app.assistant.httpx.Client", FakeClient)
    cmd = parse_command("機器人 早安")
    assert cmd is not None
    assert ask_reply(cmd, Assistant("secret-key")) == "回答失敗，請稍後再試。"

    class TimeoutClient(FakeClient):
        def post(self, url, headers, json):
            raise httpx.TimeoutException("slow")

    monkeypatch.setattr("app.assistant.httpx.Client", TimeoutClient)
    assert "逾時" in ask_reply(cmd, Assistant("secret-key"))


def test_ask_reply_truncates(monkeypatch: pytest.MonkeyPatch):
    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"output_text": "答" * 5000}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers, json):
            return FakeResponse()

    monkeypatch.setattr("app.assistant.httpx.Client", FakeClient)
    cmd = parse_command("機器人 寫長一點")
    assert cmd is not None
    reply = ask_reply(cmd, Assistant("secret-key"))
    assert len(reply) <= 4800
    assert reply.endswith("…（回答過長已截斷）")
