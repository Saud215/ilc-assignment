"""Tests for llm_adapter.call_llm. The OpenAI client is faked, so no test uses a network."""

import json
import os
import sys
from types import SimpleNamespace

import httpx2  # the HTTP library the installed openai package uses
import openai
import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

import llm_adapter  # noqa: E402

# One parameter the openai package knows, and one it has never heard of.
MAIN_PARAMS = {"reasoning_effort": "low", "future_option": {"level": 2}}

TEST_CONFIG = {
    # .invalid can never resolve, so even a mistake here cannot reach a real server.
    "provider": {"base_url": "http://llm.test.invalid/v1/", "api_key_env": "TEST_KEY"},
    "models": {"small": "test-small", "main": "test-main"},
    "params": {"small": {}, "main": MAIN_PARAMS},
    "max_retries": 2,
}

BASIC_KEYS = ["max_tokens", "messages", "model"]


def fake_response():
    """A minimal object shaped like a chat.completions reply."""
    message = SimpleNamespace(content="ok")
    choice = SimpleNamespace(message=message, finish_reason="stop")
    usage = SimpleNamespace(prompt_tokens=3, completion_tokens=1, total_tokens=10)
    return SimpleNamespace(choices=[choice], usage=usage)


def use_config(monkeypatch, config):
    monkeypatch.setattr(llm_adapter, "load_config", lambda: config)


@pytest.fixture
def fake_client(monkeypatch):
    """Replace the OpenAI client with a fake that records what create() receives."""
    state = {"create_calls": []}

    def fake_create(**kwargs):
        state["create_calls"].append(kwargs)
        return fake_response()

    def fake_openai(base_url, api_key, timeout):
        completions = SimpleNamespace(create=fake_create)
        return SimpleNamespace(chat=SimpleNamespace(completions=completions))

    monkeypatch.setattr(llm_adapter, "OpenAI", fake_openai)
    # Skip the real key lookup, so tests never load .env.
    monkeypatch.setattr(llm_adapter, "get_api_key", lambda config: "test-key")
    return state


def test_params_reach_create(fake_client, monkeypatch):
    use_config(monkeypatch, TEST_CONFIG)

    result = llm_adapter.call_llm("main", "system text", "user text", 50)

    kwargs = fake_client["create_calls"][0]
    assert kwargs["extra_body"] == MAIN_PARAMS
    assert kwargs["model"] == "test-main"
    assert kwargs["max_tokens"] == 50
    assert kwargs["messages"][0] == {"role": "system", "content": "system text"}
    assert kwargs["messages"][1] == {"role": "user", "content": "user text"}
    assert result["total_tokens"] == 10
    assert result["finish_reason"] == "stop"


def test_empty_params_add_nothing(fake_client, monkeypatch):
    use_config(monkeypatch, TEST_CONFIG)

    llm_adapter.call_llm("small", "system text", "user text", 50)

    kwargs = fake_client["create_calls"][0]
    assert sorted(kwargs) == BASIC_KEYS


def test_missing_params_section_adds_nothing(fake_client, monkeypatch):
    config = dict(TEST_CONFIG)
    del config["params"]
    use_config(monkeypatch, config)

    llm_adapter.call_llm("main", "system text", "user text", 50)

    kwargs = fake_client["create_calls"][0]
    assert sorted(kwargs) == BASIC_KEYS


def test_real_config_params_are_passed_as_they_are(fake_client):
    # Reads the real config.json (not .env), so this keeps working when you retune it.
    real_config = llm_adapter.load_config()

    for tier in real_config["models"]:
        llm_adapter.call_llm(tier, "system text", "user text", 50)
        kwargs = fake_client["create_calls"][-1]
        expected = llm_adapter.get_params(real_config, tier)
        assert kwargs.get("extra_body", {}) == expected


def test_params_cannot_override_app_values(fake_client, monkeypatch):
    config = dict(TEST_CONFIG)
    config["params"] = {"main": {"max_tokens": 5}}
    use_config(monkeypatch, config)

    with pytest.raises(ValueError, match="max_tokens"):
        llm_adapter.call_llm("main", "system text", "user text", 50)
    assert fake_client["create_calls"] == []


def test_params_land_in_request_json(monkeypatch):
    """Use the real openai client with a mock transport, to see the exact JSON it would send."""
    sent_bodies = []

    def handler(request):
        sent_bodies.append(json.loads(request.content))
        reply = {
            "id": "test",
            "object": "chat.completion",
            "created": 0,
            "model": "test-main",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "ok"},
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 10},
        }
        return httpx2.Response(200, json=reply)

    def openai_with_mock_transport(base_url, api_key, timeout):
        # MockTransport answers in-process, so no socket is ever opened.
        mock_http = httpx2.Client(transport=httpx2.MockTransport(handler))
        return openai.OpenAI(
            base_url=base_url, api_key=api_key, timeout=timeout,
            http_client=mock_http, max_retries=0,
        )

    monkeypatch.setattr(llm_adapter, "OpenAI", openai_with_mock_transport)
    monkeypatch.setattr(llm_adapter, "get_api_key", lambda config: "test-key")
    use_config(monkeypatch, TEST_CONFIG)

    llm_adapter.call_llm("main", "system text", "user text", 50)
    llm_adapter.call_llm("small", "system text", "user text", 50)

    main_body = sent_bodies[0]
    small_body = sent_bodies[1]
    # Known and unknown parameters both end up at the top level of the request JSON.
    assert main_body["reasoning_effort"] == "low"
    assert main_body["future_option"] == {"level": 2}
    assert main_body["max_tokens"] == 50
    assert sorted(small_body) == BASIC_KEYS
