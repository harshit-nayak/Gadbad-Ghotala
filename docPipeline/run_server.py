"""Launches the docsign Flask backend (Verify / Sign / Admin API) against
this directory's trust/.ca/.docsign state and its migrated docsign.db
signature registry, so /api/sign registers signatures and /api/verify
(DB mode) finds them without needing a .sig file at all.

Run from docPipeline/:  python run_server.py
The frontend/ Vite dev server proxies /api and /root_ca.pem to this
process on 127.0.0.1:8765 — see frontend/vite.config.ts.

On a server (call-monitor/deploy/aws) the same script runs with:
  DOCSIGN_DATA_DIR       where trust/, .ca/, .docsign/ and docsign.db live
                         (default: this directory, as before)
  DOCSIGN_PORT           default 8765
  DOCSIGN_ACTIVITY_FILE  touched on every sign/verify/enrol, so the idle
                         auto-stop knows the machine is in use
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DATA = Path(os.environ.get("DOCSIGN_DATA_DIR") or ROOT)
PORT = int(os.environ.get("DOCSIGN_PORT") or 8765)
ACTIVITY_FILE = os.environ.get("DOCSIGN_ACTIVITY_FILE")

# config.py reads DOCSIGN_DATABASE_URL at import time, so this must be set
# before `docsign.web` (which imports `docsign.config`) is imported.
os.environ.setdefault("DOCSIGN_DATABASE_URL", f"sqlite:///{(DATA / 'docsign.db').as_posix()}")

sys.path.insert(0, str(ROOT / "src"))

from docsign import registry  # noqa: E402
from docsign.web import create_app  # noqa: E402

if __name__ == "__main__":
    DATA.mkdir(parents=True, exist_ok=True)
    # Creates the signature table on a fresh deployment; a no-op otherwise.
    registry.init_db()
    app = create_app(
        trust_dir=str(DATA / "trust"),
        ca_dir=str(DATA / ".ca"),
        state_dir=str(DATA / ".docsign"),
    )

    if ACTIVITY_FILE:
        from flask import request

        @app.before_request
        def _mark_activity():
            # Only real work counts: page views (GET status/history) must not
            # keep a paid machine awake.
            if request.method == "POST":
                Path(ACTIVITY_FILE).touch()

    print(f"docsign API -> http://127.0.0.1:{PORT}/  (data: {DATA})")
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False, threaded=True)
