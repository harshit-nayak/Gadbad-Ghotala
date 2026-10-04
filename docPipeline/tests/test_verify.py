"""Phase 5 tests — the verification pipeline and its offline guarantee."""

from __future__ import annotations

import socket

import pytest

from docsign.verify import Status, verify_document


def _verify(env, document, **kw):
    return verify_document(document, root_cert_path=env.root_cert_path, **kw)


def test_valid_document_reports_signer_identity(env):
    doc = env.document(b"quarterly numbers")
    env.sign(doc)
    result = _verify(env, doc)
    assert result.status is Status.VALID
    assert result.signer_name == "Priya Sharma"
    assert result.signer_id == "EMP10452"
    assert "unchanged" in result.reason.lower()


def test_result_is_structured_not_a_bool(env):
    doc = env.document(b"data")
    env.sign(doc)
    result = _verify(env, doc)
    assert hasattr(result, "status")
    assert hasattr(result, "reason")
    assert not isinstance(result, bool)


def test_missing_signature_is_unverifiable(env):
    doc = env.document(b"unsigned")
    result = _verify(env, doc)
    assert result.status is Status.UNVERIFIABLE
    assert result.signer_id is None


def test_expired_is_distinct_from_tampered(env):
    import datetime as dt

    old_cert, old_key = env.issue(
        not_valid_before=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=200)
    )
    doc = env.document(b"still the original bytes")
    env.sign(doc, cert=old_cert, key=old_key)
    result = _verify(env, doc)
    assert result.status is Status.EXPIRED
    # identity still surfaced, and the reason must not say "tampered"
    assert result.signer_id == "EMP10452"
    assert "tamper" not in result.reason.lower()


def test_verification_makes_no_network_calls(env, monkeypatch):
    """Section 7: fail the build if a socket is opened during verification."""
    doc = env.document(b"offline please")
    env.sign(doc)

    def _boom(*a, **k):  # pragma: no cover - only runs on regression
        raise AssertionError("verification attempted a network operation")

    monkeypatch.setattr(socket, "socket", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(socket, "getaddrinfo", _boom)

    result = _verify(env, doc)
    assert result.status is Status.VALID


def test_unknown_sig_version_is_unverifiable(env):
    from conftest import rewrite_bundle

    doc = env.document(b"payload")
    sig = env.sign(doc)
    rewrite_bundle(sig, version=999)
    result = _verify(env, doc)
    assert result.status is Status.UNVERIFIABLE


# --------------------------------------------------------------------------- #
# verify_from_sig is verify_document under its new spec name
# --------------------------------------------------------------------------- #
def test_verify_from_sig_is_verify_document():
    from docsign.verify import verify_from_sig

    assert verify_from_sig is verify_document


# --------------------------------------------------------------------------- #
# verify_from_db — DB mode (needs the 'db' extra)
# --------------------------------------------------------------------------- #
pytest.importorskip("sqlalchemy", reason="DB mode tests need the 'db' extra")

from docsign.verify import verify_from_db  # noqa: E402


def _verify_db(env, document, **kw):
    return verify_from_db(
        document, root_cert_path=env.root_cert_path, database_url=env.db_url, **kw
    )


def test_verify_from_db_valid_document(db_env):
    doc = db_env.document(b"quarterly numbers")
    db_env.db_sign(doc)
    result = _verify_db(db_env, doc)
    assert result.status is Status.VALID
    assert result.signer_name == "Priya Sharma"
    assert result.signer_id == "EMP10452"
    assert len(result.signers) == 1


def test_verify_from_db_modified_document_is_unverifiable_not_tampered(db_env):
    """A hash miss can't be told apart from 'never signed' in DB mode — see
    the registry guide's Tamper Detection in DB Mode section."""
    doc = db_env.document(b"original content")
    db_env.db_sign(doc)
    doc.write_bytes(b"modified content")
    result = _verify_db(db_env, doc)
    assert result.status is Status.UNVERIFIABLE
    assert result.failure_reason == "NO_REGISTERED_SIGNATURE"


def test_verify_from_db_no_record_is_unverifiable(db_env):
    doc = db_env.document(b"never signed")
    result = _verify_db(db_env, doc)
    assert result.status is Status.UNVERIFIABLE
    assert result.failure_reason == "NO_REGISTERED_SIGNATURE"
    assert result.signers == []


def test_verify_from_db_expired_certificate(db_env):
    import datetime as dt

    old_cert, old_key = db_env.issue(
        not_valid_before=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=200)
    )
    doc = db_env.document(b"signed long ago")
    db_env.db_sign(doc, cert=old_cert, key=old_key)
    result = _verify_db(db_env, doc)
    assert result.status is Status.EXPIRED
    assert result.signer_id == "EMP10452"


def test_verify_from_db_invalid_cert_chain(db_env):
    rogue_cert, rogue_key = db_env.self_signed()
    doc = db_env.document(b"forged authority")
    db_env.db_sign(doc, cert=rogue_cert, key=rogue_key)
    result = _verify_db(db_env, doc)
    assert result.status is Status.INVALID


def test_verify_from_db_revoked_record_excluded_unverifiable_if_no_others(db_env):
    from docsign import registry as _registry

    doc = db_env.document(b"soon to be revoked")
    record_id = db_env.db_sign(doc)
    _registry.revoke_signature(record_id, "compromised", database_url=db_env.db_url)

    result = _verify_db(db_env, doc)
    assert result.status is Status.UNVERIFIABLE
    assert result.failure_reason == "NO_REGISTERED_SIGNATURE"


def test_verify_from_db_multiple_signers_all_valid_all_returned(db_env):
    other_cert, other_key = db_env.issue(employee_id="EMP99999", name="Alex Chen")
    doc = db_env.document(b"co-signed contract")
    db_env.db_sign(doc)
    db_env.db_sign(doc, cert=other_cert, key=other_key)

    result = _verify_db(db_env, doc)
    assert result.status is Status.VALID
    assert len(result.signers) == 2
    assert {s.employee_id for s in result.signers} == {"EMP10452", "EMP99999"}


def test_verify_from_db_multiple_signers_one_valid_result_is_valid(db_env):
    rogue_cert, rogue_key = db_env.self_signed()
    doc = db_env.document(b"one good signer, one bad")
    db_env.db_sign(doc)  # legitimate
    db_env.db_sign(doc, cert=rogue_cert, key=rogue_key)  # untrusted chain

    result = _verify_db(db_env, doc)
    assert result.status is Status.VALID
    assert [s.employee_id for s in result.signers] == ["EMP10452"]


def test_verify_from_db_unavailable_returns_verification_unavailable(db_env):
    import time

    doc = db_env.document(b"db is down")
    start = time.monotonic()
    result = verify_from_db(
        doc,
        root_cert_path=db_env.root_cert_path,
        database_url="sqlite:////no/such/directory/at/all/db.sqlite",
    )
    elapsed = time.monotonic() - start
    assert result.status is Status.VERIFICATION_UNAVAILABLE
    assert elapsed < 3.0


def test_verify_from_db_unavailable_is_not_invalid(db_env):
    """Database unavailability is operational, never a verdict about the
    document — must never collapse into INVALID or TAMPERED."""
    doc = db_env.document(b"db is down again")
    result = verify_from_db(
        doc,
        root_cert_path=db_env.root_cert_path,
        database_url="sqlite:////no/such/directory/at/all/db.sqlite",
    )
    assert result.status not in (Status.INVALID, Status.TAMPERED)
    assert result.failure_reason == "REGISTRY_UNREACHABLE"


def test_both_modes_agree_for_the_same_signature_material(env, db_env):
    """.sig and DB paths verify the same cryptographic material the same
    way — same document, same signing key, same verdict."""
    doc = env.document(b"identical material")
    env.sign(doc)
    db_env.db_sign(doc)

    from_sig = verify_document(doc, root_cert_path=env.root_cert_path)
    from_db = _verify_db(db_env, doc)

    assert from_sig.status is from_db.status is Status.VALID
    assert from_sig.signer_id == from_db.signer_id == "EMP10452"
