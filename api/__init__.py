"""Loads the repo-root .env (see .env.example) before any api module reads its
settings — api.enterprise and api.jobs resolve paths from the environment at
import time. Variables already set in the process win over the file, so the
launchers and tests/conftest.py keep control. BISCUITS_SKIP_DOTENV=1 disables it."""

import os
from pathlib import Path

if os.getenv("BISCUITS_SKIP_DOTENV") != "1":
    try:
        from dotenv import load_dotenv
    except ImportError:  # python-dotenv is in requirements.txt; a bare venv just skips .env
        pass
    else:
        load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
