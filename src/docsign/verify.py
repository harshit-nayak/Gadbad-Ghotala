"""The verification pipeline.

Offline only — this module makes zero network calls. Everything needed is in
the document, the ``.sig`` bundle, and the local root certificate.

No ``print`` here. :func:`verify_document` returns a structured
:class:`VerificationResult`; the CLI renders it.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Union

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import bundle as _bundle
from . import ca as _ca
from . import crypto

PathLike = Union[str, Path]
DEFAULT_ROOT_PATH = Path("trust") / "root_ca.pem"


class Status(str, Enum):
    VALID = "VALID"
    TAMPERED = "TAMPERED"
    EXPIRED = "EXPIRED"
    INVALID = "INVALID"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass
class VerificationResult:
    status: Status
    signer_name: Optional[str]
    signer_id: Optional[str]
    reason: str


def _load_root(root_cert_path: PathLike) -> x509.Certificate:
    return x509.load_pem_x509_certificate(Path(root_cert_path).read_bytes())


def verify_document(
    document_path: PathLike,
    sig_path: PathLike | None = None,
    *,
    root_cert_path: PathLike = DEFAULT_ROOT_PATH,
) -> VerificationResult:
    """Run the pipeline in order, short-circuiting on the first failure."""
    document_path = Path(document_path)
    sig_path = Path(sig_path) if sig_path else _bundle.sig_path_for(document_path)

    # 1. .sig present, valid JSON, known version, required fields, decodable.
    try:
        data = _bundle.read_bundle(sig_path)
        claimed_digest = _bundle.decode_digest(data)
        signature = _bundle.decode_signature(data)
    except _bundle.BundleError as exc:
        return VerificationResult(
            Status.UNVERIFIABLE,
            None,
            None,
            _unverifiable_reason(sig_path, exc),
        )

    # 2. Embedded certificate parses.
    try:
        cert = x509.load_pem_x509_certificate(data["certificate"].encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return VerificationResult(
            Status.INVALID, None, None,
            "The embedded certificate could not be parsed.",
        )

    # 3. Certificate chains to the local root.
    try:
        root_cert = _load_root(root_cert_path)
    except (FileNotFoundError, ValueError) as exc:
        return VerificationResult(
            Status.INVALID, None, None,
            f"The local root certificate could not be loaded ({exc}).",
        )
    try:
        cert.verify_directly_issued_by(root_cert)
    except Exception:  # noqa: BLE001 - any failure here means "not trusted"
        return VerificationResult(
            Status.INVALID, None, None,
            "The signer's certificate was not issued by the trusted internal root CA.",
        )

    # Identity is trustworthy from here on — surface it even on later failures.
    name, emp_id = _ca.cert_identity(cert)
    who = _describe(name, emp_id)

    # 4. Certificate is within its validity window.
    now = _dt.datetime.now(_dt.timezone.utc)
    if not (cert.not_valid_before_utc <= now <= cert.not_valid_after_utc):
        expiry = cert.not_valid_after_utc.strftime("%Y-%m-%d")
        return VerificationResult(
            Status.EXPIRED, name, emp_id,
            f"{who}'s certificate was outside its validity window "
            f"(expired {expiry}). The document itself may be intact — this is "
            "a different situation from a modified document.",
        )

    # 5. Recomputed SHA-256 of the file matches the signed digest.
    actual_digest = crypto.hash_file(document_path)
    if not crypto.digests_equal(actual_digest, claimed_digest):
        return VerificationResult(
            Status.TAMPERED, name, emp_id,
            "Document has been modified after signing. Do not act on it.",
        )

    # 6. Ed25519 signature verifies over the digest.
    pub = cert.public_key()
    if not isinstance(pub, Ed25519PublicKey):
        return VerificationResult(
            Status.INVALID, name, emp_id,
            "The certificate does not carry an Ed25519 key.",
        )
    try:
        sig_ok = crypto.verify_digest(pub, claimed_digest, signature)
    except (ValueError, TypeError):
        sig_ok = False
    if not sig_ok:
        return VerificationResult(
            Status.TAMPERED, name, emp_id,
            "The signature does not match the document. It may have been "
            "modified, or the signature was not produced over this content.",
        )

    # 7. Everything checks out.
    return VerificationResult(
        Status.VALID, name, emp_id, "Document unchanged since signing."
    )


def _describe(name: Optional[str], emp_id: Optional[str]) -> str:
    if name and emp_id:
        return f"{name} ({emp_id})"
    return name or emp_id or "the signer"


def _unverifiable_reason(sig_path: Path, exc: _bundle.BundleError) -> str:
    tail = "This document cannot be verified. Ask the sender to sign and resend."
    if not sig_path.exists():
        return f"No signature found. {tail}"
    return f"The signature file is unreadable ({exc}). {tail}"
