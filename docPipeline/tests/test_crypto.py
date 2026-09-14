"""Phase 1 tests — core crypto primitives."""

from __future__ import annotations

import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from docsign import crypto


def test_sign_verify_round_trip():
    key = Ed25519PrivateKey.generate()
    digest = crypto.hash_bytes(b"the quick brown fox")
    sig = crypto.sign_digest(key, digest)
    assert crypto.verify_digest(key.public_key(), digest, sig) is True


def test_single_flipped_byte_in_digest_fails():
    key = Ed25519PrivateKey.generate()
    digest = bytearray(crypto.hash_bytes(b"payload"))
    sig = crypto.sign_digest(key, bytes(digest))
    digest[0] ^= 0x01
    assert crypto.verify_digest(key.public_key(), bytes(digest), sig) is False


def test_signature_from_a_different_key_fails():
    signer = Ed25519PrivateKey.generate()
    other = Ed25519PrivateKey.generate()
    digest = crypto.hash_bytes(b"payload")
    sig = crypto.sign_digest(signer, digest)
    assert crypto.verify_digest(other.public_key(), digest, sig) is False


def test_verifying_with_the_private_key_raises():
    """Direction of keys: the private key signs, the public key verifies.
    Passing a private key to verify must raise, not silently succeed."""
    key = Ed25519PrivateKey.generate()
    digest = crypto.hash_bytes(b"payload")
    sig = crypto.sign_digest(key, digest)
    with pytest.raises(TypeError):
        crypto.verify_digest(key, digest, sig)


def test_sign_rejects_non_digest_length():
    key = Ed25519PrivateKey.generate()
    with pytest.raises(ValueError):
        crypto.sign_digest(key, b"too short")


def test_hash_file_streams_and_matches_hashlib(tmp_path):
    blob = b"A" * (5 * 1024 * 1024 + 7)  # larger than one chunk
    p = tmp_path / "big.bin"
    p.write_bytes(blob)
    assert crypto.hash_file(p) == hashlib.sha256(blob).digest()


def test_digests_equal_is_constant_time_wrapper():
    a = crypto.hash_bytes(b"x")
    assert crypto.digests_equal(a, a) is True
    assert crypto.digests_equal(a, crypto.hash_bytes(b"y")) is False
