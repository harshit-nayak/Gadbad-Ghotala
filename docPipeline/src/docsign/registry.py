"""The signature registry — a database of signed-document records.

Read the guiding rule before touching anything here:

    The database is a signature registry, not a trust authority.

A row in ``document_signatures`` proves nothing by itself. It exists only to
save the caller from having to supply a ``.sig`` file by hand; the actual
trust decision is always made by re-running the cryptographic pipeline
(certificate chain, expiry, Ed25519 signature) in ``verify.py``. Nothing in
this module returns a verdict, and there is deliberately no ``valid`` or
``status`` column — a compromised database admin cannot flip a bit to make a
bad signature look good.

No cryptographic logic lives here. This module only stores and retrieves
bytes; ``verify.py`` is what decides whether they mean anything.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Optional

from cryptography import x509
from sqlalchemy import (
    Column,
    Integer,
    String,
    create_engine,
    text,
)
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.engine import make_url

from . import ca as _ca
from . import config

__all__ = [
    "RegistryUnavailableError",
    "SignatureRecord",
    "compute_key_id",
    "compute_certificate_serial",
    "init_db",
    "store_signature",
    "lookup_signatures",
    "revoke_signature",
    "import_from_sig_bundle",
]


class RegistryUnavailableError(Exception):
    """The registry could not be reached, timed out, or errored unrecoverably.

    This is an *operational* failure, never a cryptographic one. Callers
    (verify.py) must map it to VERIFICATION_UNAVAILABLE, not INVALID or
    TAMPERED — the database being down says nothing about whether a
    signature is genuine.
    """


class Base(DeclarativeBase):
    pass


class DocumentSignature(Base):
    """ORM mapping for ``document_signatures``. See the module docstring:
    this table is a lookup convenience, not a trust source."""

    __tablename__ = "document_signatures"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Document identity
    document_hash = Column(String, nullable=False, index=True)
    filename = Column(String, nullable=True)  # informational only, never a lookup key

    # Cryptographic material
    signature = Column(String, nullable=False)
    certificate_pem = Column(String, nullable=False)
    algorithm = Column(String, nullable=False, default="Ed25519")
    hash_algorithm = Column(String, nullable=False, default="SHA-256")

    # Parsed certificate fields — display/query only, never trusted by verify.py
    employee_id = Column(String, nullable=False, index=True)
    employee_name = Column(String, nullable=False)
    key_id = Column(String, nullable=False)
    certificate_serial = Column(String, nullable=False, index=True)
    certificate_not_before = Column(String, nullable=False)
    certificate_not_after = Column(String, nullable=False)

    # Timestamp
    signed_at = Column(String, nullable=False)
    timestamp_token = Column(String, nullable=True)

    # Registry metadata
    created_at = Column(String, nullable=False)
    revoked_at = Column(String, nullable=True)

    # Source tracking
    source = Column(String, nullable=False, default="signed")
    import_verified_at = Column(String, nullable=True)


@dataclass
class SignatureRecord:
    """A detached, read-only view of one ``document_signatures`` row.

    Detached deliberately: callers (verify.py) must not be able to write
    back through this object, and it must remain usable after the DB
    session that produced it has closed.
    """

    id: int
    document_hash: str
    filename: Optional[str]
    signature: str
    certificate_pem: str
    algorithm: str
    hash_algorithm: str
    employee_id: str
    employee_name: str
    key_id: str
    certificate_serial: str
    certificate_not_before: str
    certificate_not_after: str
    signed_at: str
    timestamp_token: Optional[str]
    created_at: str
    revoked_at: Optional[str]
    source: str
    import_verified_at: Optional[str]

    @classmethod
    def _from_row(cls, row: DocumentSignature) -> "SignatureRecord":
        return cls(
            id=row.id,
            document_hash=row.document_hash,
            filename=row.filename,
            signature=row.signature,
            certificate_pem=row.certificate_pem,
            algorithm=row.algorithm,
            hash_algorithm=row.hash_algorithm,
            employee_id=row.employee_id,
            employee_name=row.employee_name,
            key_id=row.key_id,
            certificate_serial=row.certificate_serial,
            certificate_not_before=row.certificate_not_before,
            certificate_not_after=row.certificate_not_after,
            signed_at=row.signed_at,
            timestamp_token=row.timestamp_token,
            created_at=row.created_at,
            revoked_at=row.revoked_at,
            source=row.source,
            import_verified_at=row.import_verified_at,
        )


# --------------------------------------------------------------------------- #
# engine / session plumbing
# --------------------------------------------------------------------------- #
def _connect_args(database_url: str, timeout: float) -> dict:
    backend = make_url(database_url).get_backend_name()
    if backend == "sqlite":
        return {"timeout": timeout}
    if backend.startswith("postgresql"):
        return {"connect_timeout": timeout}
    # Unknown backend: no timeout knob we know how to set — rely on the
    # caller's statement-level handling instead of guessing a kwarg name.
    return {}


def _make_engine(database_url: Optional[str] = None, timeout: Optional[float] = None):
    url = database_url or config.DATABASE_URL
    to = config.QUERY_TIMEOUT_SECONDS if timeout is None else timeout
    return create_engine(url, connect_args=_connect_args(url, to))


def init_db(database_url: Optional[str] = None) -> None:
    """Create the ``document_signatures`` table if it does not exist yet.

    For the prototype this is a convenience (and what the tests use). A real
    deployment manages the schema with the Alembic migration in
    ``alembic/versions/0001_initial_registry.py`` instead.
    """
    engine = _make_engine(database_url)
    try:
        Base.metadata.create_all(engine)
    except OperationalError as exc:
        raise RegistryUnavailableError(f"could not initialise registry: {_short(exc)}") from exc
    finally:
        engine.dispose()


def _short(exc: Exception) -> str:
    """First line only — SQLAlchemy appends a verbose "Background on this
    error" doc-link line that is noise in a CLI/API error message."""
    return str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# certificate field derivation — display/query metadata only
# --------------------------------------------------------------------------- #
def _hex_colon(data: bytes) -> str:
    return ":".join(f"{b:02X}" for b in data)


def compute_key_id(certificate: x509.Certificate) -> str:
    """A colon-hex identifier for a certificate's key, for display/queries only.

    Prefers the SubjectKeyIdentifier extension (present on every cert this
    CA issues); falls back to a fresh SHA-256-derived identifier of the
    public key for certificates that lack the extension.
    """
    try:
        ski = certificate.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
        return _hex_colon(ski.value.digest)
    except x509.ExtensionNotFound:
        computed = x509.SubjectKeyIdentifier.from_public_key(certificate.public_key())
        return _hex_colon(computed.digest)


def compute_certificate_serial(certificate: x509.Certificate) -> str:
    """Colon-hex serial number, for display/queries only."""
    n = certificate.serial_number
    raw = n.to_bytes((n.bit_length() + 7) // 8 or 1, "big")
    return _hex_colon(raw)


def _parsed_certificate_fields(certificate_pem: str) -> dict:
    cert = x509.load_pem_x509_certificate(certificate_pem.encode("ascii"))
    return {
        "certificate_serial": compute_certificate_serial(cert),
        "certificate_not_before": cert.not_valid_before_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "certificate_not_after": cert.not_valid_after_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# --------------------------------------------------------------------------- #
# public interface
# --------------------------------------------------------------------------- #
def store_signature(
    document_hash: str,
    signature: str,
    certificate_pem: str,
    employee_id: str,
    employee_name: str,
    key_id: str,
    signed_at: str,
    filename: Optional[str],
    timestamp_token: Optional[str],
    source: str = "signed",
    *,
    import_verified_at: Optional[str] = None,
    database_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> int:
    """Store a signature record. Returns the new record id.

    Must be called only after successful cryptographic signing (or, for
    ``source="imported"``, only after a full verification pass — see
    :func:`import_from_sig_bundle`, which passes ``import_verified_at``).
    ``certificate_serial``, ``certificate_not_before`` and
    ``certificate_not_after`` are derived by parsing ``certificate_pem``
    here rather than trusted from the caller. ``timeout`` overrides
    :data:`config.QUERY_TIMEOUT_SECONDS` (mainly for tests).
    """
    try:
        parsed = _parsed_certificate_fields(certificate_pem)
    except ValueError as exc:
        raise ValueError(f"certificate_pem does not parse: {exc}") from exc

    engine = _make_engine(database_url, timeout)
    try:
        with Session(engine) as session:
            row = DocumentSignature(
                document_hash=document_hash,
                filename=filename,
                signature=signature,
                certificate_pem=certificate_pem,
                algorithm="Ed25519",
                hash_algorithm="SHA-256",
                employee_id=employee_id,
                employee_name=employee_name,
                key_id=key_id,
                signed_at=signed_at,
                timestamp_token=timestamp_token,
                created_at=_now_iso(),
                revoked_at=None,
                source=source,
                import_verified_at=import_verified_at,
                **parsed,
            )
            session.add(row)
            session.commit()
            return row.id
    except SQLAlchemyError as exc:
        raise RegistryUnavailableError(f"could not store signature: {_short(exc)}") from exc
    finally:
        engine.dispose()


def lookup_signatures(
    document_hash: str,
    *,
    database_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> list[SignatureRecord]:
    """Return all non-revoked signature records for this hash.

    Returns an empty list if none are found — a missing record is never an
    error, it just means "nothing registered for this document." Raises
    :class:`RegistryUnavailableError` if the database is unreachable or the
    query exceeds the configured timeout. ``timeout`` overrides
    :data:`config.QUERY_TIMEOUT_SECONDS` (mainly for tests).
    """
    engine = _make_engine(database_url, timeout)
    try:
        with Session(engine) as session:
            rows = (
                session.query(DocumentSignature)
                .filter(
                    DocumentSignature.document_hash == document_hash,
                    DocumentSignature.revoked_at.is_(None),
                )
                .order_by(DocumentSignature.id.asc())
                .all()
            )
            return [SignatureRecord._from_row(r) for r in rows]
    except SQLAlchemyError as exc:
        raise RegistryUnavailableError(f"registry lookup failed: {_short(exc)}") from exc
    finally:
        engine.dispose()


def list_recent(
    limit: int = 100,
    *,
    database_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> list[SignatureRecord]:
    """Return the most recently signed records, newest first.

    For a history/activity view, not a trust decision — same caveat as the
    module docstring: a row here proves nothing by itself. Raises
    :class:`RegistryUnavailableError` if the database is unreachable.
    """
    engine = _make_engine(database_url, timeout)
    try:
        with Session(engine) as session:
            rows = (
                session.query(DocumentSignature)
                .filter(DocumentSignature.revoked_at.is_(None))
                .order_by(DocumentSignature.id.desc())
                .limit(limit)
                .all()
            )
            return [SignatureRecord._from_row(r) for r in rows]
    except SQLAlchemyError as exc:
        raise RegistryUnavailableError(f"registry lookup failed: {_short(exc)}") from exc
    finally:
        engine.dispose()


def revoke_signature(
    record_id: int, reason: str, *, database_url: Optional[str] = None
) -> None:
    """Mark one specific signature record as revoked.

    Sets ``revoked_at`` to the current UTC time. The row is never deleted —
    the registry is append-only for auditability.
    """
    engine = _make_engine(database_url)
    try:
        with Session(engine) as session:
            row = session.get(DocumentSignature, record_id)
            if row is None:
                raise ValueError(f"no signature record with id {record_id}")
            row.revoked_at = _now_iso()
            session.commit()
    except SQLAlchemyError as exc:
        raise RegistryUnavailableError(f"could not revoke signature: {_short(exc)}") from exc
    finally:
        engine.dispose()


def import_from_sig_bundle(
    bundle: dict,
    verified_at: str,
    *,
    database_url: Optional[str] = None,
) -> int:
    """Store a previously verified ``.sig`` bundle.

    Callers must only invoke this after :func:`docsign.verify.verify_from_sig`
    has already returned ``VALID`` (or ``EXPIRED`` with a trusted timestamp)
    for this exact bundle — this function does no verification itself, it
    only records the outcome. Sets ``source='imported'`` and
    ``import_verified_at``.
    """
    cert = x509.load_pem_x509_certificate(bundle["certificate"].encode("ascii"))
    name, emp_id = _ca.cert_identity(cert)

    return store_signature(
        document_hash=bundle["digest"],
        signature=bundle["signature"],
        certificate_pem=bundle["certificate"],
        employee_id=emp_id or "UNKNOWN",
        employee_name=name or "Unknown",
        key_id=compute_key_id(cert),
        signed_at=bundle.get("signed_at") or verified_at,
        filename=bundle.get("filename"),
        timestamp_token=bundle.get("timestamp_token"),
        source="imported",
        import_verified_at=verified_at,
        database_url=database_url,
    )
