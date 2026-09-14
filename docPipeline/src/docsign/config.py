"""Runtime configuration for the signature registry.

Everything here is environment-driven so a deployment can point at a real
database without touching code. There is no on-disk config file — env vars
only, with defaults appropriate for local prototyping.
"""

from __future__ import annotations

import os

# Whether the operator has opted into the registry at all. CLI signing and
# verification use this to decide whether to attempt DB mode by default or
# go straight to the .sig-only path — deliberately *not* set merely because
# DATABASE_URL below resolves to a usable value, so an existing .sig-only
# deployment sees no behaviour change unless DOCSIGN_DATABASE_URL is set.
_env_url = os.environ.get("DOCSIGN_DATABASE_URL")
DATABASE_CONFIGURED = bool(_env_url)

# SQLAlchemy connection string. ``sqlite:///docsign.db`` by default — a single
# file in the current working directory, zero infrastructure. Point this at
# PostgreSQL (e.g. ``postgresql+psycopg://user:pass@host/db``) for a real
# deployment; the application code does not change, only this string. Used
# whenever a caller explicitly asks for DB mode (e.g. ``docsign import-sig``)
# regardless of DATABASE_CONFIGURED, which only gates *default* behaviour.
DATABASE_URL = _env_url if _env_url else "sqlite:///docsign.db"

# Every registry query (lookup, store, revoke) must fail fast rather than
# hang. A hung connection must not block verification indefinitely — see
# VERIFICATION_UNAVAILABLE in verify.py.
QUERY_TIMEOUT_SECONDS = int(os.environ.get("DOCSIGN_QUERY_TIMEOUT", "3"))

# Best-effort audit logging toggle. Audit logging is operational evidence,
# not part of the cryptographic trust model — see docsign.md.
AUDIT_LOG_ENABLED = os.environ.get("DOCSIGN_AUDIT_LOG", "1") not in ("0", "false", "False", "")
