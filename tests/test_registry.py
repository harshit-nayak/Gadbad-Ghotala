"""Registry unit tests — storage and retrieval only, no cryptographic
verification here (that's test_verify.py / test_attacks.py). See
registry.py's module docstring: the database is a signature registry, not a
trust authority, so these tests only check that it stores and returns bytes
faithfully, never that it judges anything valid.
"""

from __future__ import annotations

import base64
import datetime as _dt

import pytest
from cryptography.hazmat.primitives import serialization

pytest.importorskip("sqlalchemy", reason="registry (DB) tests need the 'db' extra")

from docsign import registry as _registry
from docsign import crypto


def _cert_pem(env) -> str:
    return env.emp_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")


def _store(env, doc_hash: str, **overrides) -> int:
    kwargs = dict(
        document_hash=doc_hash,
        signature=base64.b64encode(b"not a real signature").decode("ascii"),
        certificate_pem=_cert_pem(env),
        employee_id="EMP10452",
        employee_name="Priya Sharma",
        key_id="AA:BB:CC",
        signed_at="2026-09-12T10:00:00Z",
        filename="doc.pdf",
        timestamp_token=None,
        database_url=env.db_url,
    )
    kwargs.update(overrides)
    return _registry.store_signature(**kwargs)


def test_store_signature_happy_path(db_env):
    doc_hash = crypto.hash_bytes(b"payload").hex()
    record_id = _store(db_env, doc_hash)
    assert isinstance(record_id, int)

    records = _registry.lookup_signatures(doc_hash, database_url=db_env.db_url)
    assert len(records) == 1
    r = records[0]
    assert r.id == record_id
    assert r.document_hash == doc_hash
    assert r.employee_id == "EMP10452"
    assert r.source == "signed"
    assert r.revoked_at is None
    # certificate_serial / not_before / not_after are derived from the PEM,
    # not trusted from the caller — confirm they were actually populated.
    assert r.certificate_serial
    assert r.certificate_not_before
    assert r.certificate_not_after


def test_store_signature_same_hash_twice_creates_two_rows(db_env):
    """No unique constraint on document_hash — multiple legitimate signers."""
    doc_hash = crypto.hash_bytes(b"multi-signer payload").hex()
    id1 = _store(db_env, doc_hash, employee_id="EMP10452")
    id2 = _store(db_env, doc_hash, employee_id="EMP99999")
    assert id1 != id2

    records = _registry.lookup_signatures(doc_hash, database_url=db_env.db_url)
    assert len(records) == 2
    assert {r.employee_id for r in records} == {"EMP10452", "EMP99999"}


def test_lookup_signatures_empty_for_unknown_hash(db_env):
    assert _registry.lookup_signatures("00" * 32, database_url=db_env.db_url) == []


def test_lookup_signatures_excludes_revoked_rows(db_env):
    doc_hash = crypto.hash_bytes(b"revocation test").hex()
    record_id = _store(db_env, doc_hash)
    assert len(_registry.lookup_signatures(doc_hash, database_url=db_env.db_url)) == 1

    _registry.revoke_signature(record_id, "key compromised", database_url=db_env.db_url)
    assert _registry.lookup_signatures(doc_hash, database_url=db_env.db_url) == []


def test_revoke_signature_sets_revoked_at_row_not_deleted(db_env):
    doc_hash = crypto.hash_bytes(b"soft delete test").hex()
    record_id = _store(db_env, doc_hash)
    _registry.revoke_signature(record_id, "offboarded", database_url=db_env.db_url)

    # The row must still exist (append-only) even though lookup hides it.
    import sqlite3

    path = db_env.db_url.removeprefix("sqlite:///")
    conn = sqlite3.connect(path)
    try:
        row = conn.execute(
            "SELECT revoked_at FROM document_signatures WHERE id = ?", (record_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] is not None


def test_revoke_signature_excluded_from_future_lookups(db_env):
    doc_hash = crypto.hash_bytes(b"future lookup test").hex()
    id1 = _store(db_env, doc_hash, employee_id="EMP10452")
    id2 = _store(db_env, doc_hash, employee_id="EMP99999")
    _registry.revoke_signature(id1, "compromised", database_url=db_env.db_url)

    records = _registry.lookup_signatures(doc_hash, database_url=db_env.db_url)
    assert [r.id for r in records] == [id2]


def test_import_from_sig_bundle_stores_with_imported_source(db_env, env):
    doc = env.document(b"import me")
    sig_path = env.sign(doc)
    import json

    bundle = json.loads(sig_path.read_text())

    record_id = _registry.import_from_sig_bundle(
        bundle, verified_at="2026-09-12T11:00:00Z", database_url=env.db_url
    )
    records = _registry.lookup_signatures(bundle["digest"], database_url=env.db_url)
    assert len(records) == 1
    r = records[0]
    assert r.id == record_id
    assert r.source == "imported"
    assert r.import_verified_at == "2026-09-12T11:00:00Z"


def test_db_unavailable_raises_registry_unavailable_error(db_env):
    bogus_url = "sqlite:////no/such/directory/at/all/db.sqlite"
    with pytest.raises(_registry.RegistryUnavailableError):
        _registry.lookup_signatures("00" * 32, database_url=bogus_url)


def test_db_unavailable_within_configured_timeout(db_env):
    """A locked database must raise RegistryUnavailableError within the
    configured timeout, not hang indefinitely."""
    import sqlite3
    import time

    path = db_env.db_url.removeprefix("sqlite:///")
    blocker = sqlite3.connect(path, timeout=0)
    blocker.execute("BEGIN EXCLUSIVE")

    start = time.monotonic()
    try:
        with pytest.raises(_registry.RegistryUnavailableError):
            # Small timeout so the test doesn't need to wait the full
            # production default (3s) to prove the mechanism works.
            _registry.store_signature(
                document_hash=crypto.hash_bytes(b"locked").hex(),
                signature=base64.b64encode(b"sig").decode("ascii"),
                certificate_pem=_cert_pem(db_env),
                employee_id="EMP10452",
                employee_name="Priya Sharma",
                key_id="AA:BB",
                signed_at="2026-09-12T10:00:00Z",
                filename="locked.pdf",
                timestamp_token=None,
                database_url=db_env.db_url,
                timeout=0.5,
            )
        elapsed = time.monotonic() - start
        assert elapsed < 3.0
    finally:
        blocker.rollback()
        blocker.close()


def test_corrupt_record_certificate_pem_does_not_crash_verify_from_db(db_env):
    """Registry-level smoke check that a garbage certificate_pem is stored
    faithfully (no validation on write) — verify_from_db's handling of this
    is covered in test_verify.py / test_attacks.py."""
    doc_hash = crypto.hash_bytes(b"garbage cert").hex()
    record_id = _store(db_env, doc_hash)
    db_env.corrupt_record(record_id, certificate_pem="not a certificate")

    records = _registry.lookup_signatures(doc_hash, database_url=db_env.db_url)
    assert records[0].certificate_pem == "not a certificate"


def test_missing_signature_field_stored_and_returned_as_is(db_env):
    doc_hash = crypto.hash_bytes(b"missing sig").hex()
    record_id = _store(db_env, doc_hash)
    db_env.corrupt_record(record_id, signature="")

    records = _registry.lookup_signatures(doc_hash, database_url=db_env.db_url)
    assert records[0].signature == ""
