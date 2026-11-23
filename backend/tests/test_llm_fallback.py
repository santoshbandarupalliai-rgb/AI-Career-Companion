"""Provider fallback in app/llm/client.py. No network: provider functions are replaced by fakes."""

import json

import httpx
import pytest
from pydantic import BaseModel

from app.config import get_settings
from app.llm import client
from app.llm.client import LLMError, LLMUnavailable


class Out(BaseModel):
    answer: str


@pytest.fixture()
def settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "gem-secret-key")
    monkeypatch.setattr(s, "groq_api_key", "groq-secret-key")
    monkeypatch.setattr(s, "llm_providers", "gemini,groq")
    return s


def _providers(monkeypatch, gemini, groq):
    monkeypatch.setitem(client._PROVIDERS, "gemini", (lambda: get_settings().gemini_api_key, gemini))
    monkeypatch.setitem(client._PROVIDERS, "groq", (lambda: get_settings().groq_api_key, groq))


def test_uses_primary_when_it_works(settings, monkeypatch):
    calls = []
    _providers(monkeypatch, lambda *a: calls.append("gemini") or '{"answer": "g"}', lambda *a: calls.append("groq") or '{"answer": "q"}')
    assert client.generate_structured("hi", Out).answer == "g"
    assert calls == ["gemini"]


def test_falls_back_when_primary_is_rate_limited(settings, monkeypatch):
    def gem(*a):
        raise LLMError("rate limited")

    _providers(monkeypatch, gem, lambda *a: '{"answer": "from groq"}')
    assert client.generate_structured("hi", Out).answer == "from groq"
    assert client.generate_text("hi") == '{"answer": "from groq"}'


def test_falls_back_on_invalid_json_shape(settings, monkeypatch):
    _providers(monkeypatch, lambda *a: '{"wrong": 1}', lambda *a: '{"answer": "ok"}')
    assert client.generate_structured("hi", Out).answer == "ok"


def test_primary_gets_a_single_attempt_when_a_fallback_exists(settings, monkeypatch):
    seen = {}

    def gem(prompt, schema, system, temperature, thinking, attempts):
        seen["gemini"] = attempts
        raise LLMError("x")

    def groq(prompt, schema, system, temperature, thinking, attempts):
        seen["groq"] = attempts
        return '{"answer": "ok"}'

    _providers(monkeypatch, gem, groq)
    client.generate_structured("hi", Out)
    assert seen == {"gemini": 1, "groq": client._MAX_ATTEMPTS}


def test_all_providers_failing_raises_user_safe_error(settings, monkeypatch):
    def boom(*a):
        raise LLMError("The AI service request failed.")

    _providers(monkeypatch, boom, boom)
    with pytest.raises(LLMError, match="request failed"):
        client.generate_structured("hi", Out)


def test_provider_without_key_is_skipped(settings, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    calls = []
    _providers(monkeypatch, lambda *a: calls.append("gemini") or "{}", lambda *a: calls.append("groq") or '{"answer": "ok"}')
    assert client.generate_structured("hi", Out).answer == "ok"
    assert calls == ["groq"]


def test_no_keys_means_unavailable(settings, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "groq_api_key", "")
    with pytest.raises(LLMUnavailable):
        client.generate_text("hi")


def test_provider_order_is_configurable(settings, monkeypatch):
    monkeypatch.setattr(settings, "llm_providers", "groq,gemini")
    calls = []
    _providers(monkeypatch, lambda *a: calls.append("gemini") or '{"answer": "g"}', lambda *a: calls.append("groq") or '{"answer": "q"}')
    assert client.generate_structured("hi", Out).answer == "q"
    assert calls == ["groq"]


def test_groq_request_shape_and_key_masking(settings, monkeypatch):
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, body=json, auth=headers["Authorization"])
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"answer": "hello"}'}}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(client.httpx, "post", fake_post)
    out = client._groq("question", Out, "be brief", 0.1, False, 1)
    assert json.loads(out) == {"answer": "hello"}
    assert sent["auth"] == "Bearer groq-secret-key"
    assert sent["body"]["response_format"] == {"type": "json_object"}
    system = sent["body"]["messages"][0]["content"]
    assert "be brief" in system and '"answer"' in system  # schema is in the prompt
    assert sent["body"]["messages"][-1] == {"role": "user", "content": "question"}


def test_groq_rate_limit_maps_to_friendly_error_and_hides_key(settings, monkeypatch, caplog):
    def fake_post(url, json=None, headers=None, timeout=None):
        return httpx.Response(429, text="slow down groq-secret-key", request=httpx.Request("POST", url))

    monkeypatch.setattr(client.httpx, "post", fake_post)
    with caplog.at_level("WARNING"), pytest.raises(LLMError, match="rate-limited"):
        client._groq("q", None, None, 0.3, False, 1)
    assert "groq-secret-key" not in caplog.text
