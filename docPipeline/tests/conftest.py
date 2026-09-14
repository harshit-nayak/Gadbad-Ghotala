"""Shared fixtures: an in-memory CA, an enrolled employee, and helpers to
produce signature bundles (valid or deliberately broken)."""

from __future__ import annotations

import base64
import datetime as _dt
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import NameOID

from docsign import bundle as _bundle
from docsign import ca as _ca
from docsign import crypto

# Registry (DB) support needs the optional 'db' extra (sqlalchemy). Import it
# lazily, inside the Env methods that need it, so conftest.py itself — and
# every test file that doesn't touch the registry — works without it.


def _self_signed(name: str) -> tuple[x509.Certificate, Ed25519PrivateKey]:
    key = Ed25519PrivateKey.generate()
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, name),
            x509.NameAttribute(NameOID.SERIAL_NUMBER, "EMP-ROGUE"),
            x509.NameAttribute(NameOID.EMAIL_ADDRESS, "rogue@example.invalid"),
        ]
    )
    now = _dt.datetime.now(_dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(days=1))
        .not_valid_after(now + _dt.timedelta(days=90))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, algorithm=None)
    )
    return cert, key


@dataclass
class Env:
    tmp: Path
    root_cert_path: Path
    root_cert: x509.Certificate
    root_key: Ed25519PrivateKey
    emp_cert: x509.Certificate
    emp_key: Ed25519PrivateKey
    db_url: str

    # -- document + signing helpers ---------------------------------------- #
    def document(self, content: bytes, name: str = "invoice_q3.pdf") -> Path:
        p = self.tmp / name
        p.write_bytes(content)
        return p

    def sign(
        self,
        document: Path,
        *,
        cert: Optional[x509.Certificate] = None,
        key: Optional[Ed25519PrivateKey] = None,
        sign_over_digest: Optional[bytes] = None,
        store_digest: Optional[bytes] = None,
        signed_at: Optional[_dt.datetime] = None,
        sig_path: Optional[Path] = None,
    ) -> Path:
        """Write a ``.sig`` next to *document*.

        ``sign_over_digest`` / ``store_digest`` let a test decouple the digest
        that is signed from the digest written into the bundle.
        """
        cert = cert or self.emp_cert
        key = key or self.emp_key
        file_digest = crypto.hash_file(document)
        signed_digest = sign_over_digest or file_digest
        stored_digest = store_digest or file_digest
        signature = key.sign(signed_digest)
        data = _bundle.build_bundle(
            digest=stored_digest,
            signature=signature,
            certificate_pem=cert.public_bytes(serialization.Encoding.PEM),
            filename=document.name,
            signed_at=signed_at,
        )
        out = sig_path or _bundle.sig_path_for(document)
        _bundle.write_bundle(out, data)
        return out

    def issue(
        self,
        *,
        name: str = "Priya Sharma",
        email: str = "priya.sharma@company.internal",
        employee_id: str = "EMP10452",
        not_valid_before: Optional[_dt.datetime] = None,
    ) -> tuple[x509.Certificate, Ed25519PrivateKey]:
        return _ca.issue_employee_cert(
            self.root_key,
            self.root_cert,
            name,
            email,
            employee_id,
            not_valid_before=not_valid_before,
        )

    @staticmethod
    def self_signed(name: str = "Mallory") -> tuple[x509.Certificate, Ed25519PrivateKey]:
        return _self_signed(name)

    def foreign_ca(self) -> tuple[x509.Certificate, Ed25519PrivateKey]:
        """A completely separate root CA + an employee cert issued by it."""
        other_root_cert, other_root_key = _ca.init_root(
            trust_dir=self.tmp / "other_trust", ca_dir=self.tmp / "other_ca"
        )
        return _ca.issue_employee_cert(
            other_root_key,
            other_root_cert,
            "Priya Sharma",
            "priya.sharma@company.internal",
            "EMP10452",
        )

    # -- registry (DB) helpers ----------------------------------------------- #
    def db_sign(
        self,
        document: Path,
        *,
        cert: Optional[x509.Certificate] = None,
        key: Optional[Ed25519PrivateKey] = None,
        sign_over_digest: Optional[bytes] = None,
        store_digest: Optional[bytes] = None,
        timestamp_token: Optional[str] = None,
        source: str = "signed",
        filename: Optional[str] = None,
    ) -> int:
        """Sign *document* and store the record straight in the registry
        (no ``.sig`` file). Mirrors :meth:`sign`'s digest-decoupling knobs so
        DB-mode tests can construct the same kinds of inconsistent records."""
        from docsign import registry as _registry

        cert = cert or self.emp_cert
        key = key or self.emp_key
        file_digest = crypto.hash_file(document)
        signed_digest = sign_over_digest or file_digest
        stored_digest = store_digest or file_digest
        signature = key.sign(signed_digest)
        name, emp_id = _ca.cert_identity(cert)
        return _registry.store_signature(
            document_hash=stored_digest.hex(),
            signature=b64(signature),
            certificate_pem=cert.public_bytes(serialization.Encoding.PEM).decode("ascii"),
            employee_id=emp_id or "UNKNOWN",
            employee_name=name or "Unknown",
            key_id=_registry.compute_key_id(cert),
            signed_at=_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            filename=filename or document.name,
            timestamp_token=timestamp_token,
            source=source,
            database_url=self.db_url,
        )

    def corrupt_record(self, record_id: int, **fields) -> None:
        """Directly rewrite columns of a stored record via raw SQL, bypassing
        the registry API — for simulating a corrupted/tampered DB row."""
        path = self.db_url.removeprefix("sqlite:///")
        conn = sqlite3.connect(path)
        try:
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE document_signatures SET {set_clause} WHERE id = ?",
                (*fields.values(), record_id),
            )
            conn.commit()
        finally:
            conn.close()


@pytest.fixture
def env(tmp_path: Path) -> Env:
    root_cert, root_key = _ca.init_root(
        trust_dir=tmp_path / "trust", ca_dir=tmp_path / "ca"
    )
    emp_cert, emp_key = _ca.issue_employee_cert(
        root_key,
        root_cert,
        "Priya Sharma",
        "priya.sharma@company.internal",
        "EMP10452",
    )
    db_url = (tmp_path / "docsign.db").as_posix()
    db_url = "sqlite:///" + db_url
    return Env(
        tmp=tmp_path,
        root_cert_path=tmp_path / "trust" / _ca.ROOT_CERT_FILENAME,
        root_cert=root_cert,
        root_key=root_key,
        emp_cert=emp_cert,
        emp_key=emp_key,
        db_url=db_url,
    )


@pytest.fixture
def db_env(env: Env) -> Env:
    """``env`` with the registry schema already created."""
    pytest.importorskip("sqlalchemy", reason="registry (DB) tests need the 'db' extra")
    from docsign import registry as _registry

    _registry.init_db(env.db_url)
    return env


# convenience for tests that want to hand-edit a bundle
def rewrite_bundle(path: Path, **changes) -> None:
    data = json.loads(Path(path).read_text())
    data.update(changes)
    Path(path).write_text(json.dumps(data, indent=2) + "\n")


def b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")
