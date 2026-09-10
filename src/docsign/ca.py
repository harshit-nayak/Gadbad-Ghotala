"""Internal Certificate Authority: root init and employee cert issuance.

Trust model (see build guide section 3)::

    Company Root CA  (self-signed, offline key)
            | signs
    Employee Certificate  (name, email, employee_id, 90-day validity)
            | its private key signs
    Document Signature

The root public key is the single trust anchor. This module writes it to
``trust/root_ca.pem`` for distribution; the root *private* key is written to a
gitignored directory and must move to hardware-backed storage for any real
deployment.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Tuple, Union

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import NameOID

ORG_NAME = "Company Name"
ROOT_COMMON_NAME = "Company Root CA"
ROOT_VALIDITY_DAYS = 365 * 5
EMPLOYEE_VALIDITY_DAYS = 90

PathLike = Union[str, Path]

ROOT_CERT_FILENAME = "root_ca.pem"
ROOT_KEY_FILENAME = "root_ca_key.pem"


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def init_root(
    trust_dir: PathLike = "trust",
    ca_dir: PathLike = ".ca",
) -> Tuple[x509.Certificate, Ed25519PrivateKey]:
    """Generate a self-signed root CA.

    - 5-year validity, ``CA:TRUE`` basic constraint, ``keyCertSign`` usage.
    - Public cert -> ``<trust_dir>/root_ca.pem`` (distribute this everywhere).
    - Private key -> ``<ca_dir>/root_ca_key.pem`` (gitignored; prototype only).
    """
    trust_dir = Path(trust_dir)
    ca_dir = Path(ca_dir)

    key = Ed25519PrivateKey.generate()
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, ROOT_COMMON_NAME),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, ORG_NAME),
        ]
    )
    now = _now()
    ski = x509.SubjectKeyIdentifier.from_public_key(key.public_key())
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(minutes=1))
        .not_valid_after(now + _dt.timedelta(days=ROOT_VALIDITY_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(ski, critical=False)
        .sign(key, algorithm=None)  # Ed25519 has no separate hash algorithm
    )

    _write(trust_dir / ROOT_CERT_FILENAME, cert.public_bytes(serialization.Encoding.PEM))
    _write(
        ca_dir / ROOT_KEY_FILENAME,
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    return cert, key


def load_root(
    trust_dir: PathLike = "trust", ca_dir: PathLike = ".ca"
) -> Tuple[x509.Certificate, Ed25519PrivateKey]:
    """Load the root cert (public) and root key (private) from disk."""
    cert = x509.load_pem_x509_certificate(
        (Path(trust_dir) / ROOT_CERT_FILENAME).read_bytes()
    )
    key = serialization.load_pem_private_key(
        (Path(ca_dir) / ROOT_KEY_FILENAME).read_bytes(), password=None
    )
    return cert, key


def issue_employee_cert(
    root_key: Ed25519PrivateKey,
    root_cert: x509.Certificate,
    name: str,
    email: str,
    employee_id: str,
    *,
    validity_days: int = EMPLOYEE_VALIDITY_DAYS,
    not_valid_before: _dt.datetime | None = None,
) -> Tuple[x509.Certificate, Ed25519PrivateKey]:
    """Issue an employee signing certificate.

    90-day validity, ``CA:FALSE``, ``digitalSignature`` key usage. The employee
    ID is stored as ``serialNumber`` — the durable identifier the verifier
    surfaces (CN and email can change).

    ``not_valid_before`` is exposed only so tests can mint an already-expired
    certificate; normal callers should not pass it.
    """
    emp_key = Ed25519PrivateKey.generate()
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, name),
            x509.NameAttribute(NameOID.EMAIL_ADDRESS, email),
            x509.NameAttribute(NameOID.SERIAL_NUMBER, employee_id),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, ORG_NAME),
        ]
    )
    start = not_valid_before or (_now() - _dt.timedelta(minutes=1))
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(root_cert.subject)
        .public_key(emp_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(start + _dt.timedelta(days=validity_days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(emp_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()),
            critical=False,
        )
        .sign(root_key, algorithm=None)
    )
    return cert, emp_key


def cert_identity(cert: x509.Certificate) -> Tuple[str | None, str | None]:
    """Return ``(common_name, employee_id)`` from a certificate subject."""

    def _first(oid) -> str | None:
        values = cert.subject.get_attributes_for_oid(oid)
        return values[0].value if values else None

    return _first(NameOID.COMMON_NAME), _first(NameOID.SERIAL_NUMBER)
