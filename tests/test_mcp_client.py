import json

import requests

from api.mcp_client import StreamableHttpClient


class FakeResponse:
    def __init__(self, payload, headers=None, fail=False):
        self._payload = payload
        self.headers = headers or {"content-type": "application/json"}
        self.text = json.dumps(payload)
        self.fail = fail

    def raise_for_status(self):
        if self.fail:
            raise requests.HTTPError("unsupported protocol")
        return None

    def json(self):
        return self._payload


def test_stateless_mcp_tool_listing(monkeypatch):
    calls = []

    def fake_post(url, json, headers, timeout, **kwargs):
        calls.append((url, json, headers, timeout))
        return FakeResponse({"jsonrpc": "2.0", "id": 2, "result": {"tools": [
            {"name": "read_issue", "annotations": {"readOnlyHint": True}},
        ]}})

    monkeypatch.setattr("api.mcp_client.requests.post", fake_post)
    tools = StreamableHttpClient("https://mcp.example.test/mcp", "secret").list_tools()
    assert tools[0]["name"] == "read_issue"
    assert calls[0][2]["MCP-Protocol-Version"] == "2026-07-28"
    assert calls[0][2]["Mcp-Method"] == "tools/list"
    assert calls[0][2]["Authorization"] == "Bearer secret"


def test_stateless_mcp_tool_call_sets_routing_headers(monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout, **kwargs):
        captured.update(headers)
        return FakeResponse({"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text": "ok"}]}})

    monkeypatch.setattr("api.mcp_client.requests.post", fake_post)
    result = StreamableHttpClient("https://mcp.example.test/mcp").call_tool("read_issue", {"id": 42})
    assert result["content"][0]["text"] == "ok"
    assert captured["Mcp-Method"] == "tools/call"
    assert captured["Mcp-Name"] == "read_issue"


def test_mcp_falls_back_to_legacy_session(monkeypatch):
    calls = []

    def fake_post(url, json, headers, timeout, **kwargs):
        calls.append((json, headers))
        if len(calls) == 1:
            return FakeResponse({}, fail=True)
        if json.get("method") == "initialize":
            return FakeResponse({"jsonrpc": "2.0", "id": 1, "result": {
                "protocolVersion": "2025-11-25", "capabilities": {"tools": {}},
                "serverInfo": {"name": "legacy", "version": "1"},
            }}, {"content-type": "application/json", "MCP-Session-Id": "session-42"})
        if json.get("method") == "notifications/initialized":
            return FakeResponse({})
        return FakeResponse({"jsonrpc": "2.0", "id": 2, "result": {"tools": []}})

    monkeypatch.setattr("api.mcp_client.requests.post", fake_post)
    assert StreamableHttpClient("https://legacy.example.test/mcp").list_tools() == []
    assert calls[-1][1]["MCP-Session-Id"] == "session-42"
    assert calls[-1][1]["MCP-Protocol-Version"] == "2025-11-25"
