"""Translate command parsing and xAI client behavior."""

from datetime import date

import httpx
import pytest

from app.models import CommandType
from app.parser import parse_command, parse_message
from app.translator import (
    Translator,
    TranslateError,
    detect_target,
    translation_reply,
)


def test_translate_auto_chinese():
    cmd = parse_command("翻譯 早安，明天九點見")
    assert cmd is not None
    assert cmd.type == CommandType.TRANSLATE
    assert cmd.translate_target is None
    assert cmd.source_text == "早安，明天九點見"


def test_translate_auto_indonesian():
    cmd = parse_command("翻譯 Selamat pagi")
    assert cmd is not None
    assert cmd.source_text == "Selamat pagi"
    assert cmd.translate_target is None


def test_translate_forced_direction():
    to_id = parse_command("翻印尼 明天九點見")
    assert to_id is not None
    assert to_id.translate_target == "id"
    assert to_id.source_text == "明天九點見"

    to_zh = parse_command("翻中文 Besok masuk jam 9")
    assert to_zh is not None
    assert to_zh.translate_target == "zh"
    assert to_zh.source_text == "Besok masuk jam 9"

    long_head = parse_command("翻譯成印尼文：請帶證件")
    assert long_head is not None
    assert long_head.translate_target == "id"
    assert long_head.source_text == "請帶證件"


def test_translate_direction_word_after_keyword():
    cmd = parse_command("翻譯 印尼 你好")
    assert cmd is not None
    assert cmd.translate_target == "id"
    assert cmd.source_text == "你好"

    only_dir = parse_command("翻譯 中文")
    assert only_dir is not None
    assert only_dir.translate_target == "zh"
    assert only_dir.source_text == ""


def test_translate_multiline_is_one_command():
    text = "翻譯\n明天請早點到\n記得帶證件"
    result = parse_message(text)
    assert len(result.commands) == 1
    assert not result.line_errors
    cmd = result.commands[0]
    assert cmd.type == CommandType.TRANSLATE
    assert cmd.source_text == "明天請早點到\n記得帶證件"


def test_translate_empty_is_usage_command():
    result = parse_message("翻譯")
    assert not result.ignore
    assert result.commands[0].source_text == ""


def test_plain_chat_not_translated():
    assert parse_message("大家好").ignore
    assert parse_message("Selamat pagi").ignore
    assert parse_command("翻桌") is None


def test_schedule_batch_unchanged_and_translate_line_rejected():
    today = date(2026, 7, 20)
    text = "7/21 9-12 Morris\n翻譯 早安"
    result = parse_message(text, today=today)
    assert len(result.commands) == 1
    assert result.commands[0].type == CommandType.ADD
    assert len(result.line_errors) == 1
    assert "翻譯" in (result.line_errors[0].error or "")


def test_detect_target():
    assert detect_target("早安，明天九點見") == "id"
    assert detect_target("Selamat pagi, sampai jumpa") == "zh"
    assert detect_target("明天要 jam 9") == "id"
    assert detect_target("123") == "zh"


def test_translation_reply_usage_and_missing_key():
    cmd = parse_command("翻譯")
    assert cmd is not None
    reply = translation_reply(cmd, Translator(""))
    assert "翻印尼" in reply

    too_long = parse_command("翻譯 " + ("啊" * 2001))
    assert too_long is not None
    assert "2000" in translation_reply(too_long, Translator("key"))

    missing = parse_command("翻譯 早安")
    assert missing is not None
    assert "XAI_API_KEY" in translation_reply(missing, Translator(""))


def test_translation_reply_formats_result(monkeypatch: pytest.MonkeyPatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "output": [
                    {"type": "reasoning", "summary": []},
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "Selamat pagi"}
                        ],
                    },
                ]
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

    monkeypatch.setattr("app.translator.httpx.Client", FakeClient)
    cmd = parse_command("翻譯 早安")
    assert cmd is not None
    reply = translation_reply(cmd, Translator("secret-key", model="grok-4.7"))
    assert reply == "印尼文：\nSelamat pagi"
    assert captured["url"].endswith("/v1/responses")
    assert captured["headers"]["Authorization"] == "Bearer secret-key"
    body = captured["json"]
    assert body["model"] == "grok-4.7"
    assert body["store"] is False
    assert body["reasoning"] == {"effort": "low"}
    assert "早安" in body["input"][1]["content"]
    assert "Indonesian" in body["input"][1]["content"]


def test_translate_api_error(monkeypatch: pytest.MonkeyPatch):
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

    monkeypatch.setattr("app.translator.httpx.Client", FakeClient)
    cmd = parse_command("翻中文 Selamat")
    assert cmd is not None
    reply = translation_reply(cmd, Translator("secret-key"))
    assert reply == "翻譯失敗，請稍後再試。"


def test_translate_timeout(monkeypatch: pytest.MonkeyPatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, headers, json):
            raise httpx.TimeoutException("timed out")

    monkeypatch.setattr("app.translator.httpx.Client", FakeClient)
    translator = Translator("secret-key")
    with pytest.raises(TranslateError) as exc:
        translator.translate("早安", "id")
    assert exc.value.code == "api"