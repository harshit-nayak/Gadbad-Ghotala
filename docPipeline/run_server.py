"""Launches the docsign Flask backend (Verify / Sign / Admin API) against
this directory's trust/.ca/.docsign state and its migrated docsign.db
signature registry, so /api/sign registers signatures and /api/verify
(DB mode) finds them without needing a .sig file at all.

Run from docPipeline/:  python run_server.py
The frontend/ Vite dev server proxies /api and /root_ca.pem to this
process on 127.0.0.1:8765 — see frontend/vite.config.ts.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent

# config.py reads DOCSIGN_DATABASE_URL at import time, so this must be set
# before `docsign.web` (which imports `docsign.config`) is imported.
os.environ.setdefault("DOCSIGN_DATABASE_URL", f"sqlite:///{(ROOT / 'docsign.db').as_posix()}")

sys.path.insert(0, str(ROOT / "src"))

from docsign.web import run_server  # noqa: E402

if __name__ == "__main__":
    run_server(
        host="127.0.0.1",
        port=8765,
        trust_dir=str(ROOT / "trust"),
        ca_dir=str(ROOT / ".ca"),
        state_dir=str(ROOT / ".docsign"),
        open_browser=False,
    )
