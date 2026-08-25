"""
What a research script needs before it can import from `app`.

Deliberately less than `scripts/evaluate_scores.py` does: no `get_settings()`,
no `initialize_database()`. Most of the research area needs no database at all —
the sheet is a CSV, prices come from yfinance, and the scoring functions are
pure. Pulling `Settings` in here would make the whole area fail on a machine
without `backend/.env`, which defeats the word "offline".

The one thing that does need a session (scanning the live portfolio) asks for it
explicitly through `session()` below, and pays the import cost only then.

Import this first, before anything from `app`:

    from research import _bootstrap  # noqa: F401
"""

from __future__ import annotations

import os
import pathlib
import sys

#: backend/ — the directory `app` and `research` both live under.
BACKEND = pathlib.Path(__file__).resolve().parent.parent

# Settings reads .env relative to the working directory, and every relative path
# in the app assumes this is cwd.
os.chdir(BACKEND)
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# The Windows console this runs on is cp1250. Anything outside that page — an
# arrow, a typographic quote, a Czech quote — raises UnicodeEncodeError and takes
# the whole run down. Replace rather than crash. Same reasoning as
# scripts/evaluate_scores.py.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

#: backend/research/data — committed inputs and human rulings.
DATA = pathlib.Path(__file__).resolve().parent / "data"

#: backend/research/out — derived artefacts. Gitignored: everything here is a
#: function of (committed inputs + yfinance on a given day), and yfinance
#: rewrites adjusted history backwards on every split.
OUT = pathlib.Path(__file__).resolve().parent / "out"


def out_dir(name: str = "") -> pathlib.Path:
    """`out/`, or a named subdirectory of it, created if missing."""
    path = OUT / name if name else OUT
    path.mkdir(parents=True, exist_ok=True)
    return path


def session():
    """
    A database session, for the two commands that genuinely need one.

    Imported lazily and on purpose: a research run that only reads CSVs and
    yfinance must not require `backend/.env` to exist.
    """
    from app.config.settings import get_settings
    from app.database.connection import initialize_database, session_scope
    import app.models  # noqa: F401 — SQLAlchemy needs every mapper registered

    initialize_database(get_settings().database_url)
    return session_scope()
