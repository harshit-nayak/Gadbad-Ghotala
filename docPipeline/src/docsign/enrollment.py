"""A local index of who has been enrolled on this machine.

This is a *convenience* index only — it lets the CLI and the web UI show a list
of enrolled identities without needing an enumeration API from the OS keystore
(which most backends don't provide). It holds only public metadata; private
keys never touch this file and stay in the keystore.

Stored at ``<state_dir>/enrolled.json``.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Dict

from cryptography import x509

from .ca import cert_identity

REGISTRY_FILENAME = "enrolled.json"


def _path(state_dir) -> Path:
    return Path(state_dir) / REGISTRY_FILENAME


def _load(state_dir) -> Dict[str, dict]:
    p = _path(state_dir)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save(state_dir, data: Dict[str, dict]) -> None:
    p = _path(state_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def register(state_dir, certificate: x509.Certificate, email: str) -> None:
    """Record an enrolment (idempotent — keyed by employee ID)."""
    name, emp_id = cert_identity(certificate)
    if not emp_id:
        return
    data = _load(state_dir)
    data[emp_id] = {
        "name": name,
        "email": email,
        "not_before": certificate.not_valid_before_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "not_after": certificate.not_valid_after_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "enrolled_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    _save(state_dir, data)


def unregister(state_dir, employee_id: str) -> None:
    data = _load(state_dir)
    if data.pop(employee_id, None) is not None:
        _save(state_dir, data)


def list_enrolled(state_dir) -> Dict[str, dict]:
    """Return ``{employee_id: {name, email, not_before, not_after, ...}}``."""
    now = _dt.datetime.now(_dt.timezone.utc)
    out = {}
    for emp_id, meta in sorted(_load(state_dir).items()):
        meta = dict(meta)
        try:
            not_after = _dt.datetime.strptime(
                meta["not_after"], "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=_dt.timezone.utc)
            meta["expired"] = now > not_after
        except (KeyError, ValueError):
            meta["expired"] = None
        out[emp_id] = meta
    return out
