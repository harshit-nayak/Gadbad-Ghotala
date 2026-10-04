"""The detached signature bundle (``document.pdf.sig``).

JSON sitting alongside the document. Detached rather than embedded to avoid the
circular dependency of writing a signature into the file it signs.

Wire format (version 1)::

    {
      "version": 1,
      "algorithm": "Ed25519",
      "hash": "SHA-256",
      "digest": "<hex of SHA-256(document bytes)>",
      "signature": "<base64 Ed25519 signature over the raw digest bytes>",
      "certificate": "<PEM employee certificate>",
      "signed_at": "2026-09-10T14:03:22Z",
      "filename": "invoice_q3.pdf"
    }

``signed_at`` and ``filename`` are informational only and are never used in a
verification decision.
"""

from __future__ import annotations

import base64
import binascii
import datetime as _dt
import json
from pathlib import Path
from typing import Any, Dict, Union

from . import crypto

BUNDLE_VERSION = 1
SUPPORTED_VERSIONS = frozenset({1})
SIG_SUFFIX = ".sig"

PathLike = Union[str, Path]


class BundleError(Exception):
    """The ``.sig`` file is missing, malformed, truncated, or an unknown version."""


def sig_path_for(document_path: PathLike) -> Path:
    """``invoice.pdf`` -> ``invoice.pdf.sig`` (the signature sits next to the doc)."""
    p = Path(document_path)
    return p.with_name(p.name + SIG_SUFFIX)


def build_bundle(
    *,
    digest: bytes,
    signature: bytes,
    certificate_pem: bytes,
    filename: str,
    signed_at: _dt.datetime | None = None,
) -> Dict[str, Any]:
    ts = signed_at or _dt.datetime.now(_dt.timezone.utc)
    return {
        "version": BUNDLE_VERSION,
        "algorithm": crypto.SIGNATURE_ALGORITHM,
        "hash": crypto.HASH_ALGORITHM,
        "digest": digest.hex(),
        "signature": base64.b64encode(signature).decode("ascii"),
        "certificate": certificate_pem.decode("ascii"),
        "signed_at": ts.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "filename": filename,
    }


def write_bundle(path: PathLike, bundle: Dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")


def read_bundle(path: PathLike) -> Dict[str, Any]:
    """Parse and structurally validate a ``.sig`` file.

    Raises :class:`BundleError` for anything the verifier should treat as
    ``UNVERIFIABLE``: missing file, bad JSON, unknown version, missing or
    malformed required fields. It does **not** do any cryptography.
    """
    p = Path(path)
    if not p.exists():
        raise BundleError("no signature file found")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise BundleError(f"signature file is not valid JSON: {exc}")

    if not isinstance(data, dict):
        raise BundleError("signature file is not a JSON object")

    version = data.get("version")
    if version not in SUPPORTED_VERSIONS:
        raise BundleError(f"unknown signature format version: {version!r}")

    required = ("algorithm", "hash", "digest", "signature", "certificate")
    missing = [k for k in required if not isinstance(data.get(k), str) or not data[k]]
    if missing:
        raise BundleError(f"signature file missing fields: {', '.join(missing)}")

    return data


def decode_digest(bundle: Dict[str, Any]) -> bytes:
    try:
        return bytes.fromhex(bundle["digest"])
    except (ValueError, TypeError) as exc:
        raise BundleError(f"digest field is not valid hex: {exc}")


def decode_signature(bundle: Dict[str, Any]) -> bytes:
    try:
        return base64.b64decode(bundle["signature"], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BundleError(f"signature field is not valid base64: {exc}")
