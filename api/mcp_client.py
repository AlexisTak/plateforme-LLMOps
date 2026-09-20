"""Small Streamable HTTP MCP client used by the enterprise tool catalog."""

from __future__ import annotations

import json
from typing import Any

import requests

CURRENT_PROTOCOL = "2026-07-28"
LEGACY_PROTOCOL = "2025-11-25"
ACCEPT = "application/json, text/event-stream"


class McpError(RuntimeError):
    pass


def _payload(response: requests.Response, request_id: int) -> dict[str, Any]:
    try:
        if "text/event-stream" in response.headers.get("content-type", ""):
            candidates = [line[5:].strip() for line in response.text.splitlines() if line.startswith("data:")]
            messages = [json.loads(value) for value in candidates if value]
            value = next((item for item in messages if item.get("id") == request_id), None)
        else:
            value = response.json()
    except (ValueError, TypeError) as exc:
        raise McpError("Réponse MCP invalide") from exc
    if not isinstance(value, dict):
        raise McpError("Réponse MCP JSON-RPC absente")
    if value.get("error"):
        error = value["error"]
        raise McpError(str(error.get("message", error)) if isinstance(error, dict) else str(error))
    if not isinstance(value.get("result"), dict):
        raise McpError("Résultat MCP invalide")
    return value["result"]


class StreamableHttpClient:
    def __init__(self, url: str, token: str | None = None, timeout: int = 10) -> None:
        self.url = url
        self.timeout = timeout
        self.headers = {"Accept": ACCEPT, "Content-Type": "application/json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def _post(self, body: dict[str, Any], headers: dict[str, str] | None = None) -> requests.Response:
        from api.outbound import validate_outbound_url

        url = validate_outbound_url(self.url)
        return requests.post(url, json=body, headers={**self.headers, **(headers or {})}, timeout=self.timeout,
                             allow_redirects=False)

    def _stateless(self, method: str, params: dict[str, Any], request_id: int) -> dict[str, Any]:
        params = {**params, "_meta": {"io.modelcontextprotocol/clientInfo": {"name": "openagent", "version": "0.1"}}}
        headers = {"MCP-Protocol-Version": CURRENT_PROTOCOL, "Mcp-Method": method}
        if method == "tools/call" and isinstance(params.get("name"), str):
            headers["Mcp-Name"] = params["name"]
        response = self._post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}, headers)
        response.raise_for_status()
        return _payload(response, request_id)

    def _legacy_session(self) -> str | None:
        response = self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": LEGACY_PROTOCOL, "capabilities": {},
            "clientInfo": {"name": "openagent", "version": "0.1"},
        }})
        response.raise_for_status()
        _payload(response, 1)
        session_id = response.headers.get("MCP-Session-Id")
        headers = {"MCP-Protocol-Version": LEGACY_PROTOCOL}
        if session_id:
            headers["MCP-Session-Id"] = session_id
        ready = self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, headers)
        ready.raise_for_status()
        return session_id

    def _legacy(self, method: str, params: dict[str, Any], request_id: int) -> dict[str, Any]:
        session_id = self._legacy_session()
        headers = {"MCP-Protocol-Version": LEGACY_PROTOCOL}
        if session_id:
            headers["MCP-Session-Id"] = session_id
        response = self._post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}, headers)
        response.raise_for_status()
        return _payload(response, request_id)

    def request(self, method: str, params: dict[str, Any], request_id: int = 2) -> dict[str, Any]:
        try:
            return self._stateless(method, params, request_id)
        except (requests.RequestException, McpError) as current_error:
            try:
                return self._legacy(method, params, request_id)
            except (requests.RequestException, McpError) as legacy_error:
                raise McpError(f"Connexion MCP impossible : {legacy_error}") from current_error

    def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        for page in range(100):
            result = self.request("tools/list", {"cursor": cursor} if cursor else {}, page + 2)
            values = result.get("tools")
            if not isinstance(values, list):
                raise McpError("Le serveur MCP ne retourne pas de catalogue d’outils")
            tools.extend(item for item in values if isinstance(item, dict))
            cursor = result.get("nextCursor")
            if not cursor:
                return tools
        raise McpError("Pagination MCP trop longue")

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})
