"""Outbound URL policy for project-configured tools, providers and MCP servers.

Those URLs are set by project admins/operators and then fetched by the API
process itself — the classic SSRF shape: without a check, a tool pointing at
127.0.0.1, 169.254.169.254 (cloud metadata) or an internal service lets any
operator probe the server's network with attacker-controlled arguments.

Policy: http(s) only, hostname must resolve, and every resolved address must be
globally routable — unless host:port is in BISCUITS_OUTBOUND_ALLOW_PRIVATE
(comma-separated, default "127.0.0.1:11434,localhost:11434" so a local Ollama
keeps working). Checked at registration *and* right before each request, so
entries stored before this policy existed are covered too. Redirects are never
followed by callers (allow_redirects=False) so a public host can't bounce us to
a private one.

Offline mode (BISCUITS_OFFLINE=1 or the console toggle) flips the policy to "nothing
leaves the machine": every outbound call is refused except allowlisted endpoints
resolving to loopback.
Every API egress (providers, MCP, tools) goes through validate_outbound_url.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException

_DEFAULT_ALLOW = "127.0.0.1:11434,localhost:11434"


def _allowed_private() -> set[str]:
    raw = os.getenv("BISCUITS_OUTBOUND_ALLOW_PRIVATE", _DEFAULT_ALLOW)
    return {entry.strip().lower() for entry in raw.split(",") if entry.strip()}


# --- Offline mode -------------------------------------------------------------------
# Two sources: BISCUITS_OFFLINE=1 in the environment/.env (locked on, the UI can't turn it
# off) or the console toggle, persisted as a flag file next to the control-plane DB so it
# survives restarts. Either way apply_offline_env() also cuts HuggingFace off.

_ROOT = Path(__file__).resolve().parent.parent
_HF_OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "ANONYMIZED_TELEMETRY": "False",
}
_applied_env: set[str] = set()


def _flag_path() -> Path:
    db = Path(os.getenv("BISCUITS_ENTERPRISE_DB", _ROOT / ".enterprise" / "control-plane.db"))
    return db.parent / "offline.flag"


def offline_locked() -> bool:
    return os.getenv("BISCUITS_OFFLINE", "").strip().lower() in {"1", "true", "yes", "on"}


def offline_mode() -> bool:
    return offline_locked() or _flag_path().exists()


def set_offline(enabled: bool) -> None:
    flag = _flag_path()
    if enabled:
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text("1", encoding="utf-8")
    else:
        flag.unlink(missing_ok=True)
    apply_offline_env()


def apply_offline_env() -> None:
    """Propagates the offline state to the ML libraries: env vars (inherited by the job
    subprocesses spawned afterwards) and huggingface_hub's constant, which
    is_offline_mode() — used by transformers and sentence-transformers — reads per call."""
    offline = offline_mode()
    if offline:
        for name, value in _HF_OFFLINE_ENV.items():
            if name not in os.environ:
                os.environ[name] = value
                _applied_env.add(name)
    else:
        for name in list(_applied_env):
            os.environ.pop(name, None)
            _applied_env.discard(name)
    hub_constants = sys.modules.get("huggingface_hub.constants")
    if hub_constants is not None:
        env_offline = os.getenv("HF_HUB_OFFLINE") or os.getenv("TRANSFORMERS_OFFLINE") or ""
        hub_constants.HF_HUB_OFFLINE = offline or env_offline.strip().upper() in {"1", "ON", "YES", "TRUE"}


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_reserved or ip.is_unspecified)


def _resolve(host: str, port: int) -> set[str]:
    """DNS resolution, isolated so tests can stub it (tests/conftest.py)."""
    try:
        return {info[4][0] for info in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)}
    except socket.gaierror:
        return set()


def validate_outbound_url(value: str) -> str:
    """Returns the URL stripped of its trailing slash, or raises 400."""
    value = value.strip().rstrip("/")
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise HTTPException(400, "L’URL doit commencer par http:// ou https:// et contenir un hôte")
    if parts.username or parts.password:
        raise HTTPException(400, "L’URL ne doit pas embarquer d’identifiants")

    host = parts.hostname.lower()
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if offline_mode():
        # Nothing may leave the machine: only allowlisted endpoints on loopback (local Ollama).
        resolved = _resolve(host, port) if f"{host}:{port}" in _allowed_private() else set()
        if not resolved or not all(ipaddress.ip_address(a).is_loopback for a in resolved):
            raise HTTPException(
                403,
                f"Mode hors ligne (BISCUITS_OFFLINE=1) : appel vers {host}:{port} bloqué — seuls les services "
                "locaux listés dans BISCUITS_OUTBOUND_ALLOW_PRIVATE (ex. Ollama sur 127.0.0.1) sont autorisés",
            )
        return value
    if f"{host}:{port}" in _allowed_private():
        return value

    resolved = _resolve(host, port)
    if not resolved:
        raise HTTPException(400, f"Hôte introuvable : {host}")
    for address in resolved:
        if not _is_public(address):
            raise HTTPException(
                400,
                f"{host} résout vers une adresse interne ({address}) — les outils ne peuvent viser que des hôtes "
                "publics, ou un hôte explicitement listé dans BISCUITS_OUTBOUND_ALLOW_PRIVATE",
            )
    return value


def read_capped(response, max_bytes: int) -> tuple[bytes, bool]:
    """Reads at most max_bytes from a streamed response. Returns (data, truncated)."""
    chunks: list[bytes] = []
    total = 0
    truncated = False
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        remaining = max_bytes - total
        if len(chunk) > remaining:
            chunks.append(chunk[:remaining])
            truncated = True
            break
        chunks.append(chunk)
        total += len(chunk)
    response.close()
    return b"".join(chunks), truncated
