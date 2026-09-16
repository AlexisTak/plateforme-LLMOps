"""Minimal example client for Biscuits Focus's HTTP API.

There is no separate hand-maintained Python package to install here: the API
already publishes a full OpenAPI schema at /openapi.json, and /api/v1/* mirrors
every endpoint under a stable, versioned prefix (api/main.py's
ApiV1AliasMiddleware) — so a typed client can be generated with any standard
codegen tool instead of us hand-maintaining (and inevitably drifting from) a
second implementation, e.g.:

    pip install openapi-python-client
    openapi-python-client generate --url http://localhost:8000/openapi.json

The one thing codegen can't infer is the auth header contract, demonstrated
below (see api/enterprise.py:actor_from_request for the authoritative version).

Run: python sdk/python/quickstart.py
"""

from __future__ import annotations

import os

import requests

BASE_URL = os.environ.get("BISCUITS_FOCUS_URL", "http://localhost:8000")


def _headers() -> dict[str, str]:
    # local mode (the default) needs no headers at all. proxy mode needs the
    # identity headers your reverse proxy / SSO gateway is expected to set.
    proxy_secret = os.environ.get("BISCUITS_PROXY_SECRET")
    if not proxy_secret:
        return {}
    return {
        "x-biscuits-proxy-secret": proxy_secret,
        "x-biscuits-user-id": os.environ["BISCUITS_USER_ID"],
        "x-biscuits-user-email": os.environ["BISCUITS_USER_EMAIL"],
        "x-biscuits-role": os.environ.get("BISCUITS_USER_ROLE", "viewer"),
    }


def list_projects() -> list[dict]:
    response = requests.get(f"{BASE_URL}/api/v1/projects", headers=_headers(), timeout=10)
    response.raise_for_status()
    return response.json()


def demo() -> None:
    projects = list_projects()
    assert isinstance(projects, list)
    print(f"{len(projects)} project(s): {[p['id'] for p in projects]}")


if __name__ == "__main__":
    demo()
