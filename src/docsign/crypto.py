"""Core cryptographic primitives: hashing, signing, verifying.

Pure by design — no CLI, no printing, no side effects beyond reading the file
handed to :func:`hash_file`. The adversarial test suite calls this module
directly.

The algorithm is fixed here as a single constant per the build guide. Do not
scatter algorithm choices across modules.
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from typing import Union

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# --- the one place the scheme is chosen -------------------------------------
SIGNATURE_ALGORITHM = "Ed25519"
HASH_ALGORITHM = "SHA-256"
_DIGEST_SIZE = 32  # SHA-256 output, and what Ed25519 signs here
_CHUNK_SIZE = 1024 * 1024

PathLike = Union[str, Path]


def hash_file(path: PathLike) -> bytes:
    """Return the raw SHA-256 digest of a file, streamed in chunks.

    Streaming keeps this O(1) in memory regardless of document size.
    """
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK_SIZE), b""):
            h.update(chunk)
    return h.digest()


def hash_bytes(data: bytes) -> bytes:
    """Return the raw SHA-256 digest of an in-memory byte string."""
    return hashlib.sha256(data).digest()


def sign_digest(private_key: Ed25519PrivateKey, digest: bytes) -> bytes:
    """Sign a 32-byte digest with an Ed25519 private key.

    We sign the digest, never the whole file — that is why signing is O(1) in
    document size. Callers must pass the raw digest bytes, not a hex string.
    """
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError(
            "sign_digest requires an Ed25519 private key; "
            f"got {type(private_key).__name__}"
        )
    if not isinstance(digest, (bytes, bytearray)) or len(digest) != _DIGEST_SIZE:
        raise ValueError(f"digest must be {_DIGEST_SIZE} raw bytes (SHA-256 output)")
    return private_key.sign(bytes(digest))


def verify_digest(
    public_key: Ed25519PublicKey, digest: bytes, signature: bytes
) -> bool:
    """Return True iff *signature* is a valid Ed25519 signature over *digest*.

    The *public* key verifies; the *private* key signs. Passing a private key
    here is a programming error and raises rather than silently succeeding —
    this is the classic direction-of-keys bug and we refuse to hide it.
    """
    if isinstance(public_key, Ed25519PrivateKey):
        raise TypeError(
            "verify_digest requires a PUBLIC key, but was given a private key. "
            "The private key signs; the public key verifies."
        )
    if not isinstance(public_key, Ed25519PublicKey):
        raise TypeError(
            "verify_digest requires an Ed25519 public key; "
            f"got {type(public_key).__name__}"
        )
    if not isinstance(digest, (bytes, bytearray)) or len(digest) != _DIGEST_SIZE:
        raise ValueError(f"digest must be {_DIGEST_SIZE} raw bytes (SHA-256 output)")
    try:
        public_key.verify(bytes(signature), bytes(digest))
        return True
    except InvalidSignature:
        return False


def digests_equal(a: bytes, b: bytes) -> bool:
    """Constant-time comparison of two digests."""
    return hmac.compare_digest(a, b)
