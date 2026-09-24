"""Session-wide isolation for the module-level singletons.

`api.enterprise.store` (SQLite control plane) and `api.jobs.registry` (job
history) resolve their on-disk location from the environment *at import time*.
Without this file every HTTP-level test wrote into the real `.enterprise/` and
`.jobs/` of the checkout — state leaked between test files and between runs on
the same day (budget/usage counters, audit events, seeded opportunities), and
tests had to invent globally-unique project ids to stay out of each other's way.

pytest imports conftest.py before any test module, so the variables are set
before `api.enterprise` / `api.jobs` are first imported. Each pytest session
gets a fresh, empty control plane in a temporary directory.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# A developer's .env (proxy secret, bootstrap admin...) must not leak into the tests.
os.environ["BISCUITS_SKIP_DOTENV"] = "1"
_session_dir = Path(tempfile.mkdtemp(prefix="biscuits-focus-tests-"))
os.environ.setdefault("BISCUITS_ENTERPRISE_DB", str(_session_dir / "control-plane.db"))
os.environ.setdefault("BISCUITS_JOBS_DIR", str(_session_dir / "jobs"))
# The API defaults to "login" (auth required); tests exercise routes as the local
# admin unless they monkeypatch a mode themselves (test_auth.py, test_rag_acl.py...).
os.environ.setdefault("BISCUITS_AUTH_MODE", "local")

import pytest  # noqa: E402  (after the env setup above, on purpose)


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    """Tests use fictitious hosts (*.test) and mock `requests`, so they must never
    hit real DNS. Every host resolves to a public address here; tests of the
    outbound policy itself override this with their own stub."""
    monkeypatch.setattr("api.outbound._resolve", lambda host, port: {"93.184.216.34"})
Path(os.environ["BISCUITS_JOBS_DIR"]).mkdir(parents=True, exist_ok=True)
