"""Minimal text-completion call against configured project provider.
(Existing `providers` table only ever pinged /api/tags or /v1/models —
adds actual generation call, reused by opportunity AI analysis endpoint)."""

from __future__ import annotations

import os
from typing import Any

import requests


class ProviderCallError(Exception):
    pass


def generate(provider: dict[str, Any], prompt: str, timeout: int = 60) -> str:
    if provider["type"] == "ollama":
        response = requests.post(
            f"{provider['base_url']}/api/generate",
            json={"model": provider["model"], "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()["response"]

    headers: dict[str, str] = {}
    if provider.get("api_key_env"):
        secret = os.getenv(provider["api_key_env"], "")
        if not secret:
            raise ProviderCallError(f"Variable {provider['api_key_env']} absente")
        if provider["type"] == "anthropic-compatible":
            headers["x-api-key"] = secret
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["Authorization"] = f"Bearer {secret}"

    if provider["type"] == "anthropic-compatible":
        response = requests.post(
            f"{provider['base_url']}/v1/messages", headers=headers,
            json={"model": provider["model"], "max_tokens": 2000,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()["content"][0]["text"]

    response = requests.post(
        f"{provider['base_url']}/v1/chat/completions", headers=headers,
        json={"model": provider["model"], "messages": [{"role": "user", "content": prompt}]},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]
