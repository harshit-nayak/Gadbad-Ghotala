"""The verification pipeline.

Two verification paths, both cryptographic, sharing the same result shape:

- ``verify_from_sig`` (alias of the original ``verify_document``) — fully
  offline, reads a ``.sig`` bundle from disk. Zero network calls.
- ``verify_from_db`` — looks a document's hash up in the signature registry
  instead of requiring a ``.sig`` file on hand. The database is a lookup
  convenience only: every record it returns still goes through the same
  certificate-chain, expiry and Ed25519 checks as the offline path. See
  ``registry.py``'s module docstring — the database is a signature registry,
  not a trust authority.

No ``print`` here. Both functions return a structured
:class:`VerificationResult`; the CLI renders it.
"""

from __future__ import annotations

import base64
import binascii
import datetime as _dt
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Union

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
    VERIFICATION_UNAVAILABLE = "VERIFICATION_UNAVAILABLE"


@dataclass
class SignerInfo:
    """One signer's identity and per-record verification detail.

    Populated by :func:`verify_from_db` — DB mode may retrieve several
    signature records for one document hash, so a single flat
    ``signer_name``/``signer_id`` pair on :class:`VerificationResult` isn't
    enough. The offline ``.sig`` path never has more than one signer and
    leaves this empty; its flat fields are sufficient.
    """

    employee_id: Optional[str]
    employee_name: Optional[str]
    key_id: Optional[str]
    certificate_serial: Optional[str]
    certificate_status: str  # "VALID" | "EXPIRED"
    certificate_valid_from: Optional[_dt.datetime]
    certificate_valid_until: Optional[_dt.datetime]
    signature_verified: Optional[bool]
    timestamp_present: bool
    timestamp_trusted: Optional[bool]


@dataclass
class VerificationResult:
    status: Status
    signer_name: Optional[str]
    signer_id: Optional[str]
    certificate_valid_until: Optional[_dt.datetime]
    document_digest: Optional[str]  # full 64-char hex, set once recomputed
    filename: Optional[str]
    reason: str
    # Fields below are additive (all have defaults) so verify_document's
    # existing positional construction calls are untouched, per the spec's
    # "do not modify the existing function."
    failure_reason: Optional[str] = None  # e.g. "NO_REGISTERED_SIGNATURE"
    signers: List[SignerInfo] = field(default_factory=list)  # DB mode, 0+ signers


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


# The offline path under its new spec name. Same function, not a copy — see
# the "do not modify the existing function" note in the signature registry
# guide. `docsign.md` and the registry guide both call this path
# `verify_from_sig`; existing callers and tests keep using `verify_document`.
verify_from_sig = verify_document


@dataclass
class _RecordOutcome:
    status: Status  # VALID | EXPIRED | INVALID | TAMPERED (never UNVERIFIABLE)
    signer: Optional[SignerInfo]
    reason: str


def _verify_record(
    document_hash: bytes,
    record: "object",
    root_cert_path: PathLike,
) -> _RecordOutcome:
    """Cryptographically verify one registry record against a trusted digest.

    Mirrors ``verify_from_sig``'s steps 2-5 (parse cert, chain, expiry,
    signature) applied to one DB row instead of one ``.sig`` file. Kept as a
    separate implementation rather than sharing code with
    ``verify_document`` because that function must not be modified (see
    above) and is structured around reading a bundle file, not iterating
    database rows — the pipeline *order* is identical by design even though
    the code is not literally shared.

    ``document_hash`` is the digest recomputed from the actual file bytes
    (never the record's own stored copy) — the same "never trust the
    claimed digest by itself" rule the offline path follows.
    """
    # 3. Parse certificate_pem.
    try:
        cert = x509.load_pem_x509_certificate(record.certificate_pem.encode("ascii"))
    except (ValueError, UnicodeEncodeError, AttributeError):
        return _RecordOutcome(
            Status.INVALID, None,
            f"record {record.id}: stored certificate could not be parsed.",
        )

    # 4. Certificate chains to the local root.
    try:
        root_cert = _load_root(root_cert_path)
    except (FileNotFoundError, ValueError) as exc:
        return _RecordOutcome(
            Status.INVALID, None,
            f"local root certificate could not be loaded ({exc}).",
        )
    try:
        cert.verify_directly_issued_by(root_cert)
    except Exception:  # noqa: BLE001 - any failure here means "not trusted"
        return _RecordOutcome(
            Status.INVALID, None,
            f"record {record.id}: certificate does not chain to the trusted root.",
        )

    name, emp_id = _ca.cert_identity(cert)
    valid_from = cert.not_valid_before_utc
    valid_until = cert.not_valid_after_utc
    timestamp_present = bool(record.timestamp_token)

    # 5. Certificate is within its validity window.
    now = _dt.datetime.now(_dt.timezone.utc)
    if not (valid_from <= now <= valid_until):
        signer = SignerInfo(
            emp_id, name, record.key_id, record.certificate_serial, "EXPIRED",
            valid_from, valid_until, None, timestamp_present, None,
        )
        return _RecordOutcome(
            Status.EXPIRED, signer,
            f"record {record.id}: certificate expired {valid_until:%Y-%m-%d}.",
        )

    # 6. Ed25519 signature verifies over the (already hash-matched) digest.
    pub = cert.public_key()
    sig_ok = False
    if isinstance(pub, Ed25519PublicKey):
        try:
            sig_bytes = base64.b64decode(record.signature, validate=True)
            sig_ok = crypto.verify_digest(pub, document_hash, sig_bytes)
        except (ValueError, TypeError, binascii.Error):
            sig_ok = False
    if not sig_ok:
        signer = SignerInfo(
            emp_id, name, record.key_id, record.certificate_serial, "VALID",
            valid_from, valid_until, False, timestamp_present, None,
        )
        return _RecordOutcome(
            Status.TAMPERED, signer,
            f"record {record.id}: stored signature does not verify against "
            "this document's hash — the registry record is inconsistent.",
        )

    # 7. Optional trusted timestamp — presence is surfaced; no RFC 3161
    # client is wired up here, so trust is never asserted, only availability.
    signer = SignerInfo(
        emp_id, name, record.key_id, record.certificate_serial, "VALID",
        valid_from, valid_until, True, timestamp_present, None,
    )
    return _RecordOutcome(Status.VALID, signer, f"record {record.id}: valid.")


def verify_from_db(
    document_path: PathLike,
    *,
    root_cert_path: PathLike = DEFAULT_ROOT_PATH,
    database_url: Optional[str] = None,
) -> VerificationResult:
    """Verify a document against the signature registry instead of a ``.sig`` file.

    A hash miss cannot be distinguished from "never signed" — see the
    registry guide's "Tamper detection in DB mode" section — so it is
    reported as ``UNVERIFIABLE`` with ``failure_reason=NO_REGISTERED_SIGNATURE``,
    never ``TAMPERED``. ``TAMPERED`` is still possible in DB mode, but means
    something narrower here: a *stored* signature that fails to verify
    against its own recorded hash (a corrupted registry row), not "the
    document was modified after signing" — that requires a ``.sig`` to
    compare against. Database unavailability (unreachable or timed out) is
    an operational failure, never a cryptographic one, and is reported as
    ``VERIFICATION_UNAVAILABLE`` rather than any verdict about the document.
    """
    document_path = Path(document_path)
    filename = document_path.name
    digest_bytes = crypto.hash_file(document_path)
    digest_hex = digest_bytes.hex()

    try:
        from . import registry as _registry
    except ImportError as exc:
        return VerificationResult(
            Status.VERIFICATION_UNAVAILABLE, None, None, None, digest_hex, filename,
            f"The signature registry is not available ({exc}). Cryptographic "
            "verification was not performed. If you have the .sig file, "
            "verify with --offline.",
            failure_reason="REGISTRY_UNREACHABLE",
        )

    try:
        records = _registry.lookup_signatures(digest_hex, database_url=database_url)
    except _registry.RegistryUnavailableError as exc:
        return VerificationResult(
            Status.VERIFICATION_UNAVAILABLE, None, None, None, digest_hex, filename,
            f"The signature registry could not be reached ({exc}). "
            "Cryptographic verification was not performed. If you have the "
            ".sig file, verify with --offline.",
            failure_reason="REGISTRY_UNREACHABLE",
        )

    if not records:
        return VerificationResult(
            Status.UNVERIFIABLE, None, None, None, digest_hex, filename,
            "No registered signature found for this document. If you have "
            "a .sig file, verify with --offline.",
            failure_reason="NO_REGISTERED_SIGNATURE",
        )

    outcomes = [_verify_record(digest_bytes, r, root_cert_path) for r in records]
    valid = [o for o in outcomes if o.status is Status.VALID]
    tampered = [o for o in outcomes if o.status is Status.TAMPERED]
    expired = [o for o in outcomes if o.status is Status.EXPIRED]

    if valid:
        signers = [o.signer for o in valid if o.signer]
        best = signers[0]
        return VerificationResult(
            Status.VALID, best.employee_name, best.employee_id,
            best.certificate_valid_until, digest_hex, filename,
            f"{len(valid)} valid signature(s) found for this document.",
            signers=signers,
        )

    # No record verified. A TAMPERED-signal (broken stored signature) is
    # surfaced ahead of a plain chain/parse failure — it is the more
    # actionable anomaly: the registry itself looks corrupted, not merely
    # that nobody trusted has signed this document. See Assumption 5 in the
    # registry guide.
    if tampered:
        signers = [o.signer for o in tampered if o.signer]
        best = signers[0] if signers else None
        return VerificationResult(
            Status.TAMPERED,
            best.employee_name if best else None,
            best.employee_id if best else None,
            best.certificate_valid_until if best else None,
            digest_hex, filename,
            "A registered signature record for this document's hash failed "
            "signature verification. This indicates a corrupted registry "
            "record, not necessarily that the document itself was modified.",
            signers=signers,
        )

    if expired and len(expired) == len(outcomes):
        signers = [o.signer for o in expired if o.signer]
        best = signers[0] if signers else None
        return VerificationResult(
            Status.EXPIRED,
            best.employee_name if best else None,
            best.employee_id if best else None,
            best.certificate_valid_until if best else None,
            digest_hex, filename,
            "Every registered signature for this document was made with a "
            "since-expired certificate.",
            signers=signers,
        )

    # All-INVALID, or a mix of EXPIRED and INVALID with no VALID or TAMPERED:
    # nothing here is trustworthy, and identity is not surfaced (unlike
    # EXPIRED) because chain trust itself was never established.
    signers = [o.signer for o in outcomes if o.signer]
    return VerificationResult(
        Status.INVALID, None, None, None, digest_hex, filename,
        "No registered signature for this document could be validated "
        "against the trusted root.",
        signers=signers,
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


# --------------------------------------------------------------------------- #
# .sig import — verify first, only store what qualifies
# --------------------------------------------------------------------------- #
class ImportRejected(Exception):
    """A ``.sig`` bundle failed verification and must not enter the registry.

    Carries the :class:`VerificationResult` that caused the rejection so the
    caller (CLI / API) can explain exactly why.
    """

    def __init__(self, result: VerificationResult) -> None:
        self.result = result
        super().__init__(f"{result.status.value}: {result.reason}")


def import_verified_sig(
    document_path: PathLike,
    sig_path: PathLike | None = None,
    *,
    root_cert_path: PathLike = DEFAULT_ROOT_PATH,
    database_url: Optional[str] = None,
) -> tuple:
    """Verify a ``.sig`` bundle and, only if it qualifies, store it in the registry.

    A successful import means "this signature was cryptographically valid at
    time of import," not "trust it forever" — every subsequent lookup still
    re-verifies it in full. Only ``VALID`` is imported, plus ``EXPIRED``
    backed by a trusted timestamp; note that trusted-timestamp *verification*
    (RFC 3161) is not implemented here (see docsign.md, where it is marked
    optional) — the presence of a ``timestamp_token`` is used as a stand-in.
    Everything else raises :class:`ImportRejected` and nothing is written.

    Returns ``(record_id, result)`` on success.
    """
    document_path = Path(document_path)
    sig_path = Path(sig_path) if sig_path else _bundle.sig_path_for(document_path)

    result = verify_from_sig(document_path, sig_path, root_cert_path=root_cert_path)

    has_timestamp = False
    if result.status is Status.EXPIRED:
        try:
            has_timestamp = bool(_bundle.read_bundle(sig_path).get("timestamp_token"))
        except _bundle.BundleError:
            has_timestamp = False

    eligible = result.status is Status.VALID or (
        result.status is Status.EXPIRED and has_timestamp
    )
    if not eligible:
        raise ImportRejected(result)

    from . import registry as _registry

    data = _bundle.read_bundle(sig_path)
    record_id = _registry.import_from_sig_bundle(
        data,
        verified_at=_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        database_url=database_url,
    )
    return record_id, result
