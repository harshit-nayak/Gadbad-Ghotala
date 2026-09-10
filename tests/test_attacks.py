"""The adversarial suite (build guide section 9).

Each case asserts a *specific* status, not merely "not VALID". These are the
tests that demonstrate the system does what it claims.

Note on authorship: the build guide asks that attack cases be written by
someone who did not write ``verify.py``. In this prototype that separation is
not available; a real deployment must not treat this file as sufficient.
"""

from __future__ import annotations

import datetime as _dt

import pytest

from docsign.verify import Status, verify_document
from conftest import rewrite_bundle

# A small but structurally plausible PDF, so "re-saved" means real byte changes.
PDF_V1 = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
PDF_V2 = b"%PDF-1.7\n1 0 obj<</Type/Catalog/Lang(en)>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def _verify(env, document, **kw):
    return verify_document(document, root_cert_path=env.root_cert_path, **kw)


def test_01_unmodified_signed_document_is_valid(env):
    doc = env.document(b"authoritative content")
    env.sign(doc)
    assert _verify(env, doc).status is Status.VALID


def test_02_one_byte_flipped_is_tampered(env):
    doc = env.document(b"authoritative content")
    env.sign(doc)
    data = bytearray(doc.read_bytes())
    data[3] ^= 0x01
    doc.write_bytes(data)
    assert _verify(env, doc).status is Status.TAMPERED


def test_03_trailing_whitespace_appended_is_tampered(env):
    doc = env.document(b"authoritative content")
    env.sign(doc)
    doc.write_bytes(doc.read_bytes() + b"   \n")
    assert _verify(env, doc).status is Status.TAMPERED


def test_04_pdf_resaved_through_another_tool_is_tampered(env):
    doc = env.document(PDF_V1, name="report.pdf")
    env.sign(doc)
    doc.write_bytes(PDF_V2)  # any re-encode changes the bytes -> must fail
    assert _verify(env, doc).status is Status.TAMPERED


def test_05_sig_deleted_is_unverifiable(env):
    doc = env.document(b"authoritative content")
    sig = env.sign(doc)
    sig.unlink()
    result = _verify(env, doc)
    assert result.status is Status.UNVERIFIABLE
    assert "No signature found" in result.reason


def test_06_sig_from_document_a_paired_with_document_b_is_tampered(env):
    doc_a = env.document(b"contents of A", name="a.txt")
    doc_b = env.document(b"contents of B", name="b.txt")
    sig_a = env.sign(doc_a)
    assert _verify(env, doc_b, sig_path=sig_a).status is Status.TAMPERED


def test_07_self_signed_cert_not_chaining_to_root_is_invalid(env):
    rogue_cert, rogue_key = env.self_signed()
    doc = env.document(b"forged authority")
    env.sign(doc, cert=rogue_cert, key=rogue_key)
    assert _verify(env, doc).status is Status.INVALID


def test_08_cert_from_a_different_root_ca_is_invalid(env):
    foreign_cert, foreign_key = env.foreign_ca()
    doc = env.document(b"issued elsewhere")
    env.sign(doc, cert=foreign_cert, key=foreign_key)
    assert _verify(env, doc).status is Status.INVALID


def test_09_certificate_past_its_validity_window_is_expired(env):
    old_cert, old_key = env.issue(
        not_valid_before=_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=200)
    )
    doc = env.document(b"signed long ago")
    env.sign(doc, cert=old_cert, key=old_key)
    assert _verify(env, doc).status is Status.EXPIRED


def test_10_digest_field_edited_to_match_tampered_file_is_tampered(env):
    """The digest lives inside the signed data, so editing it in the bundle to
    match a tampered file does not help the attacker."""
    from docsign import crypto

    doc = env.document(b"original content")
    sig = env.sign(doc)
    doc.write_bytes(b"attacker-substituted content")
    rewrite_bundle(sig, digest=crypto.hash_file(doc).hex())
    assert _verify(env, doc).status is Status.TAMPERED


def test_11_backdated_signed_at_still_verifies_valid(env):
    """signed_at is asserted by the signer and never trusted; changing it must
    not affect the verdict."""
    doc = env.document(b"authoritative content")
    sig = env.sign(doc)
    rewrite_bundle(sig, signed_at="2000-01-01T00:00:00Z")
    assert _verify(env, doc).status is Status.VALID


def test_12_malformed_truncated_sig_is_unverifiable_without_crashing(env):
    doc = env.document(b"authoritative content")
    sig = env.sign(doc)
    sig.write_text('{"version": 1, "algori')  # truncated JSON
    result = _verify(env, doc)  # must not raise
    assert result.status is Status.UNVERIFIABLE
