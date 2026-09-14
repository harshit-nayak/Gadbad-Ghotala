"""Private key storage.

By default, private keys live in the OS keystore via ``keyring``:

- macOS: Keychain
- Windows: Credential Locker (DPAPI/CNG backed)
- Linux: Secret Service, or an encrypted ``keyrings.alt`` file with a passphrase

A plaintext key file on disk is permitted **only** behind an explicit
``--insecure-keyfile`` flag, and every use of it prints a warning. The insecure
keyfile holds the employee certificate PEM followed by the private key PEM so a
single portable file is enough to sign.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Tuple, Union

import keyring
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

KEY_SERVICE = "docsign-private-key"
CERT_SERVICE = "docsign-certificate"

PathLike = Union[str, Path]


class KeyNotFound(Exception):
    """No stored key/cert for the requested employee ID."""


def _key_pem(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _warn_insecure(path: PathLike) -> None:
    print(
        f"WARNING: using plaintext key file {path!s} -- the private key is "
        "unprotected on disk. Do not use this outside local testing.",
        file=sys.stderr,
    )


def store_identity(
    employee_id: str,
    private_key: Ed25519PrivateKey,
    certificate: x509.Certificate,
    *,
    insecure_keyfile: PathLike | None = None,
) -> None:
    """Persist an employee's private key and certificate."""
    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    key_pem = _key_pem(private_key)

    if insecure_keyfile is not None:
        _warn_insecure(insecure_keyfile)
        path = Path(insecure_keyfile)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(cert_pem + key_pem)
        return

    keyring.set_password(KEY_SERVICE, employee_id, key_pem.decode("ascii"))
    keyring.set_password(CERT_SERVICE, employee_id, cert_pem.decode("ascii"))


def load_identity(
    employee_id: str | None = None,
    *,
    insecure_keyfile: PathLike | None = None,
) -> Tuple[Ed25519PrivateKey, x509.Certificate]:
    """Load ``(private_key, certificate)`` for signing."""
    if insecure_keyfile is not None:
        _warn_insecure(insecure_keyfile)
        blob = Path(insecure_keyfile).read_bytes()
        try:
            cert = x509.load_pem_x509_certificate(blob)
            key = serialization.load_pem_private_key(blob, password=None)
        except ValueError as exc:  # pragma: no cover - defensive
            raise KeyNotFound(f"could not read key file {insecure_keyfile}: {exc}")
        return key, cert

    if not employee_id:
        raise KeyNotFound("an employee ID is required to load a key from the keystore")

    key_pem = keyring.get_password(KEY_SERVICE, employee_id)
    cert_pem = keyring.get_password(CERT_SERVICE, employee_id)
    if key_pem is None or cert_pem is None:
        raise KeyNotFound(
            f"no stored signing identity for employee ID {employee_id!r}. "
            "Run 'docsign enrol' first."
        )
    key = serialization.load_pem_private_key(key_pem.encode("ascii"), password=None)
    cert = x509.load_pem_x509_certificate(cert_pem.encode("ascii"))
    return key, cert


def delete_identity(employee_id: str) -> None:
    """Remove a stored identity from the keystore (best effort)."""
    for service in (KEY_SERVICE, CERT_SERVICE):
        try:
            keyring.delete_password(service, employee_id)
        except keyring.errors.PasswordDeleteError:
            pass
