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
