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
    certificate_valid_until: Optional[_dt.datetime]
    document_digest: Optional[str]  # full 64-char hex, set once recomputed
    filename: Optional[str]
    reason: str


def _load_root(root_cert_path: PathLike) -> x509.Certificate:
    return x509.load_pem_x509_certificate(Path(root_cert_path).read_bytes())


def verify_document(
    document_path: PathLike,
    sig_path: PathLike | None = None,
    *,
    root_cert_path: PathLike = DEFAULT_ROOT_PATH,
) -> VerificationResult:
    """Run the pipeline in order, short-circuiting on the first failure.

    Step 5 (signature) always runs before step 6 (digest comparison): the
    Ed25519 signature is what makes the bundle's ``digest`` field trustworthy
    in the first place. Comparing digests first would let an attacker who
    controls the ``.sig`` substitute any digest they like before the check
    that is supposed to catch exactly that.
    """
    document_path = Path(document_path)
    sig_path = Path(sig_path) if sig_path else _bundle.sig_path_for(document_path)
    filename = document_path.name

    # 1. .sig present, valid JSON, known version, required fields, decodable.
    try:
        data = _bundle.read_bundle(sig_path)
        claimed_digest = _bundle.decode_digest(data)
        signature = _bundle.decode_signature(data)
    except _bundle.BundleError as exc:
        return VerificationResult(
            Status.UNVERIFIABLE,
            None, None, None, None, filename,
            _unverifiable_reason(sig_path, exc),
        )

    # 2. Embedded certificate parses.
    try:
        cert = x509.load_pem_x509_certificate(data["certificate"].encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return VerificationResult(
            Status.INVALID, None, None, None, None, filename,
            "The embedded certificate could not be parsed.",
        )

    # 3. Certificate chains to the local root.
    try:
        root_cert = _load_root(root_cert_path)
    except (FileNotFoundError, ValueError) as exc:
        return VerificationResult(
            Status.INVALID, None, None, None, None, filename,
            f"The local root certificate could not be loaded ({exc}).",
        )
    try:
        cert.verify_directly_issued_by(root_cert)
    except Exception:  # noqa: BLE001 - any failure here means "not trusted"
        return VerificationResult(
            Status.INVALID, None, None, None, None, filename,
            "The signer's certificate was not issued by the trusted internal root CA.",
        )

    # Identity is trustworthy from here on — surface it even on later failures.
    name, emp_id = _ca.cert_identity(cert)
    who = _describe(name, emp_id)
    valid_until = cert.not_valid_after_utc

    # 4. Certificate is within its validity window.
    now = _dt.datetime.now(_dt.timezone.utc)
    if not (cert.not_valid_before_utc <= now <= cert.not_valid_after_utc):
        expiry = valid_until.strftime("%Y-%m-%d")
        return VerificationResult(
            Status.EXPIRED, name, emp_id, valid_until, None, filename,
            f"{who}'s certificate was outside its validity window "
            f"(expired {expiry}). The document itself may be intact — this is "
            "a different situation from a modified document.",
        )

    # 5. Ed25519 signature verifies over the digest claimed in the bundle.
    # This must happen before step 6: it is what makes claimed_digest trustworthy.
    pub = cert.public_key()
    if not isinstance(pub, Ed25519PublicKey):
        return VerificationResult(
            Status.INVALID, name, emp_id, valid_until, None, filename,
            "The certificate does not carry an Ed25519 key.",
        )
    try:
        sig_ok = crypto.verify_digest(pub, claimed_digest, signature)
    except (ValueError, TypeError):
        sig_ok = False
    if not sig_ok:
        return VerificationResult(
            Status.TAMPERED, name, emp_id, valid_until, None, filename,
            "The signature does not match the claimed digest. The signature "
            "bundle is inconsistent — do not act on this document.",
        )

    # 6. Recomputed SHA-256 of the file matches the now-trustworthy digest.
    actual_digest = crypto.hash_file(document_path)
    if not crypto.digests_equal(actual_digest, claimed_digest):
        return VerificationResult(
            Status.TAMPERED, name, emp_id, valid_until, actual_digest.hex(), filename,
            "Document has been modified after signing. Do not act on it.",
        )

    # 7. Everything checks out.
    return VerificationResult(
        Status.VALID, name, emp_id, valid_until, actual_digest.hex(), filename,
        "Document unchanged since signing.",
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
