import pytest

from api.ai_provider_client import ProviderCallError, generate


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_generate_ollama(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout, **kwargs):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse({"response": "hello"})

    monkeypatch.setattr("api.ai_provider_client.requests.post", fake_post)
    provider = {"type": "ollama", "base_url": "http://localhost:11434", "model": "llama3", "api_key_env": None}
    assert generate(provider, "prompt") == "hello"
    assert captured["url"] == "http://localhost:11434/api/generate"
    assert captured["json"]["prompt"] == "prompt"


def test_generate_openai_compatible_requires_api_key(monkeypatch):
    monkeypatch.delenv("TEST_KEY", raising=False)
    provider = {"type": "openai-compatible", "base_url": "https://api.example.test", "model": "gpt",
                "api_key_env": "TEST_KEY"}
    with pytest.raises(ProviderCallError):
        generate(provider, "prompt")


def test_generate_openai_compatible(monkeypatch):
    monkeypatch.setenv("TEST_KEY", "secret")
    captured = {}

    def fake_post(url, json, headers, timeout, **kwargs):
        captured["headers"] = headers
        return FakeResponse({"choices": [{"message": {"content": "answer"}}]})

    monkeypatch.setattr("api.ai_provider_client.requests.post", fake_post)
    provider = {"type": "openai-compatible", "base_url": "https://api.example.test", "model": "gpt",
                "api_key_env": "TEST_KEY"}
    assert generate(provider, "prompt") == "answer"
    assert captured["headers"]["Authorization"] == "Bearer secret"


def test_generate_anthropic_compatible(monkeypatch):
    monkeypatch.setenv("TEST_KEY", "secret")

    def fake_post(url, json, headers, timeout, **kwargs):
        return FakeResponse({"content": [{"text": "answer"}]})

    monkeypatch.setattr("api.ai_provider_client.requests.post", fake_post)
    provider = {"type": "anthropic-compatible", "base_url": "https://api.anthropic.test", "model": "claude",
                "api_key_env": "TEST_KEY"}
    assert generate(provider, "prompt") == "answer"
