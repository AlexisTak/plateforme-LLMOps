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

_session_dir = Path(tempfile.mkdtemp(prefix="biscuits-focus-tests-"))
os.environ.setdefault("BISCUITS_ENTERPRISE_DB", str(_session_dir / "control-plane.db"))
os.environ.setdefault("BISCUITS_JOBS_DIR", str(_session_dir / "jobs"))
Path(os.environ["BISCUITS_JOBS_DIR"]).mkdir(parents=True, exist_ok=True)
