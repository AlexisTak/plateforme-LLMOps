"""Offline mode toggle (/api/system/offline): persisted across restarts, admin-only,
locked on by BISCUITS_OFFLINE, and actually enforced by the outbound policy and the
HuggingFace offline switch."""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api import outbound

PROXY = {"BISCUITS_AUTH_MODE": "proxy", "BISCUITS_PROXY_SECRET": "test-secret"}


def _headers(role: str) -> dict[str, str]:
    return {
        "x-biscuits-proxy-secret": "test-secret", "x-biscuits-user-id": f"u-{role}",
        "x-biscuits-user-email": f"{role}@example.test", "x-biscuits-role": role,
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("BISCUITS_OFFLINE", raising=False)
    from api.main import app
    yield TestClient(app)
    outbound.set_offline(False)  # the flag file lives in the session's temp control-plane dir


def test_toggle_blocks_outbound_and_hf_then_restores(client, monkeypatch):
    monkeypatch.setattr(outbound, "_resolve", lambda host, port: {"93.184.216.34"})
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    import huggingface_hub.constants as hub_constants

    assert client.get("/api/system/offline").json() == {"enabled": False, "locked": False}
    assert client.put("/api/system/offline", json={"enabled": True}).json() == {"enabled": True, "locked": False}
    with pytest.raises(HTTPException) as exc:
        outbound.validate_outbound_url("https://api.provider.test")
    assert exc.value.status_code == 403
    assert os.environ["HF_HUB_OFFLINE"] == "1" and hub_constants.HF_HUB_OFFLINE is True

    assert client.put("/api/system/offline", json={"enabled": False}).json()["enabled"] is False
    assert outbound.validate_outbound_url("https://api.provider.test") == "https://api.provider.test"
    assert "HF_HUB_OFFLINE" not in os.environ and hub_constants.HF_HUB_OFFLINE is False


def test_toggle_survives_restart(client):
    client.put("/api/system/offline", json={"enabled": True})
    assert outbound._flag_path().exists()
    assert outbound.offline_mode()  # a fresh process only reads the flag file


def test_env_lock_cannot_be_disabled_from_console(client, monkeypatch):
    monkeypatch.setenv("BISCUITS_OFFLINE", "1")
    assert client.get("/api/system/offline").json() == {"enabled": True, "locked": True}
    assert client.put("/api/system/offline", json={"enabled": False}).status_code == 409


@pytest.mark.parametrize("role", ["viewer", "operator", "reviewer"])
def test_only_admin_can_toggle(monkeypatch, role):
    for key, value in PROXY.items():
        monkeypatch.setenv(key, value)
    from api.main import app
    client = TestClient(app)
    assert client.put("/api/system/offline", json={"enabled": True}, headers=_headers(role)).status_code == 403
    assert not outbound.offline_mode()
    assert client.get("/api/system/offline", headers=_headers(role)).status_code == 200


def test_hf_constant_untouched_when_hub_not_imported(monkeypatch):
    monkeypatch.delitem(sys.modules, "huggingface_hub.constants", raising=False)
    outbound.apply_offline_env()  # must not import huggingface_hub itself
    assert "huggingface_hub.constants" not in sys.modules
