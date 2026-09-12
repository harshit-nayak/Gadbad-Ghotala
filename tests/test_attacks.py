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


def test_13_chain_check_runs_before_signature_check_is_invalid(env):
    """A self-signed (untrusted) cert whose bundled signature is *also*
    broken must still come back INVALID, not TAMPERED. That only holds if
    the chain check (step 3) runs and fails before the signature check
    (step 5) gets a chance to — verifying a valid self-signed key would
    otherwise let it reach step 6 and misreport the failure."""
    from docsign import crypto

    rogue_cert, rogue_key = env.self_signed()
    doc = env.document(b"forged authority, and the signature is broken too")
    mismatched_digest = crypto.hash_bytes(b"an entirely different payload")
    env.sign(doc, cert=rogue_cert, key=rogue_key, sign_over_digest=mismatched_digest)
    assert _verify(env, doc).status is Status.INVALID


# --------------------------------------------------------------------------- #
# Signature registry attacks (registry guide, DB mode — needs the 'db' extra)
# --------------------------------------------------------------------------- #
pytest.importorskip("sqlalchemy", reason="DB mode attack tests need the 'db' extra")

from docsign.verify import verify_from_db, import_verified_sig, ImportRejected  # noqa: E402


def _verify_db(env, document, **kw):
    return verify_from_db(
        document, root_cert_path=env.root_cert_path, database_url=env.db_url, **kw
    )


def test_14_db_record_tampered_signature_bytes_is_tampered(db_env):
    """The stored signature bytes don't verify against the recorded hash —
    a corrupted registry row, not document tampering (the hash still
    matches the actual file). See docsign.md Assumption 5."""
    doc = db_env.document(b"registry row will be corrupted")
    record_id = db_env.db_sign(doc)
    db_env.corrupt_record(record_id, signature="Y29ycnVwdGVkIQ==")  # base64 garbage
    assert _verify_db(db_env, doc).status is Status.TAMPERED


def test_15_db_record_cert_does_not_chain_is_invalid(db_env):
    rogue_cert, rogue_key = db_env.self_signed()
    doc = db_env.document(b"forged authority via the registry")
    db_env.db_sign(doc, cert=rogue_cert, key=rogue_key)
    assert _verify_db(db_env, doc).status is Status.INVALID


def test_16_importing_a_tampered_sig_is_rejected_not_stored(db_env):
    from docsign import crypto, registry as _registry

    doc = db_env.document(b"original content")
    sig = db_env.sign(doc)
    doc.write_bytes(b"attacker-substituted content")  # tamper after signing

    with pytest.raises(ImportRejected) as exc_info:
        import_verified_sig(doc, sig, root_cert_path=db_env.root_cert_path,
                             database_url=db_env.db_url)
    assert exc_info.value.result.status is Status.TAMPERED

    doc_hash = crypto.hash_file(doc).hex()
    assert _registry.lookup_signatures(doc_hash, database_url=db_env.db_url) == []


def test_17_importing_a_sig_from_a_different_root_is_rejected_not_stored(db_env):
    from docsign import crypto, registry as _registry

    foreign_cert, foreign_key = db_env.foreign_ca()
    doc = db_env.document(b"issued by a different company entirely")
    sig = db_env.sign(doc, cert=foreign_cert, key=foreign_key)

    with pytest.raises(ImportRejected) as exc_info:
        import_verified_sig(doc, sig, root_cert_path=db_env.root_cert_path,
                             database_url=db_env.db_url)
    assert exc_info.value.result.status is Status.INVALID

    doc_hash = crypto.hash_file(doc).hex()
    assert _registry.lookup_signatures(doc_hash, database_url=db_env.db_url) == []


def test_18_db_record_empty_certificate_pem_is_invalid_no_crash(db_env):
    doc = db_env.document(b"corrupted certificate column")
    record_id = db_env.db_sign(doc)
    db_env.corrupt_record(record_id, certificate_pem="")

    result = _verify_db(db_env, doc)  # must not raise
    assert result.status is Status.INVALID


def test_19_one_valid_one_invalid_signer_reports_the_valid_one(db_env):
    """An attacker adds a second, untrustworthy row for the same document
    hash hoping to confuse the verdict. The legitimate signer must still be
    the one reported, and the overall result must still be VALID."""
    rogue_cert, rogue_key = db_env.self_signed()
    doc = db_env.document(b"legit signer plus an attacker-added row")
    db_env.db_sign(doc)  # legitimate: EMP10452
    db_env.db_sign(doc, cert=rogue_cert, key=rogue_key)  # attacker's own cert

    result = _verify_db(db_env, doc)
    assert result.status is Status.VALID
    assert [s.employee_id for s in result.signers] == ["EMP10452"]
