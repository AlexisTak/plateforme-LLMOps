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
"""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlsplit

from fastapi import HTTPException

_DEFAULT_ALLOW = "127.0.0.1:11434,localhost:11434"


def _allowed_private() -> set[str]:
    raw = os.getenv("BISCUITS_OUTBOUND_ALLOW_PRIVATE", _DEFAULT_ALLOW)
    return {entry.strip().lower() for entry in raw.split(",") if entry.strip()}


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
