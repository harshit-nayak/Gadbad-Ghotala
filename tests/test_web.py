"""Smoke tests for the local web frontend.

The keyring is stubbed with an in-memory dict so tests never touch the real OS
keystore.
"""

from __future__ import annotations

import io
import json

import pytest

pytest.importorskip("flask")

from docsign import keystore, web


class _MemKeyring:
    def __init__(self):
        self.store = {}

    def set_password(self, service, user, secret):
        self.store[(service, user)] = secret

    def get_password(self, service, user):
        return self.store.get((service, user))

    def delete_password(self, service, user):
        self.store.pop((service, user), None)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(keystore, "keyring", _MemKeyring())
    app = web.create_app(
        trust_dir=tmp_path / "trust",
        ca_dir=tmp_path / "ca",
        state_dir=tmp_path / "state",
    )
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture
def db_client(tmp_path, monkeypatch):
    """A client with the signature registry configured and initialised —
    /api/verify (DB mode) and /api/registry/import need this; the plain
    ``client`` fixture deliberately leaves DATABASE_CONFIGURED off so
    /api/verify falls back to VERIFICATION_UNAVAILABLE instead of silently
    working, matching the CLI's "don't silently fall back" rule."""
    pytest.importorskip("sqlalchemy", reason="DB-mode web tests need the 'db' extra")
    from docsign import config, registry

    db_url = "sqlite:///" + (tmp_path / "docsign.db").as_posix()
    registry.init_db(db_url)
    monkeypatch.setattr(config, "DATABASE_CONFIGURED", True)
    monkeypatch.setattr(config, "DATABASE_URL", db_url)

    monkeypatch.setattr(keystore, "keyring", _MemKeyring())
    app = web.create_app(
        trust_dir=tmp_path / "trust",
        ca_dir=tmp_path / "ca",
        state_dir=tmp_path / "state",
    )
    app.config.update(TESTING=True)
    return app.test_client()


def _upload(name, data):
    return {name: (io.BytesIO(data), name)}


def test_full_flow_sign_then_verify_offline(client):
    """/api/verify/offline — the explicit .sig path, DB not involved."""
    assert client.post("/api/init-ca").status_code == 200

    r = client.post(
        "/api/enrol",
        json={"name": "Priya Sharma", "email": "priya@company.internal", "id": "EMP10452"},
    )
    assert r.status_code == 200

    st = client.get("/api/status").get_json()
    assert st["ca"] is not None
    assert st["enrolled"][0]["id"] == "EMP10452"

    doc = b"quarterly report bytes"
    r = client.post(
        "/api/sign",
        data={"employee_id": "EMP10452", **_upload("file", doc)},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    sig_text = r.get_json()["bundle_text"]

    # matching doc + sig -> VALID
    r = client.post(
        "/api/verify/offline",
        data={
            **_upload("file", doc),
            "sig": (io.BytesIO(sig_text.encode()), "report.sig"),
        },
        content_type="multipart/form-data",
    )
    assert r.get_json()["status"] == "VALID"

    # tampered doc -> TAMPERED
    r = client.post(
        "/api/verify/offline",
        data={
            **_upload("file", doc + b"!"),
            "sig": (io.BytesIO(sig_text.encode()), "report.sig"),
        },
        content_type="multipart/form-data",
    )
    assert r.get_json()["status"] == "TAMPERED"

    # no sig -> a 400 (offline mode requires one), not a verdict
    r = client.post(
        "/api/verify/offline",
        data=_upload("file", doc),
        content_type="multipart/form-data",
    )
    assert r.status_code == 400


def test_verify_without_db_configured_is_verification_unavailable(client):
    """The plain client has no registry configured. /verify must not
    silently fall back to .sig — it should say the registry is unavailable."""
    r = client.post(
        "/api/verify",
        data=_upload("file", b"whatever"),
        content_type="multipart/form-data",
    )
    assert r.get_json()["status"] == "VERIFICATION_UNAVAILABLE"


def test_full_flow_sign_then_verify_db_mode(db_client):
    """/api/verify (default, DB mode) — no .sig upload at all."""
    assert db_client.post("/api/init-ca").status_code == 200
    assert db_client.post(
        "/api/enrol",
        json={"name": "Priya Sharma", "email": "priya@company.internal", "id": "EMP10452"},
    ).status_code == 200

    doc = b"quarterly report bytes, registry edition"
    r = db_client.post(
        "/api/sign",
        data={"employee_id": "EMP10452", **_upload("file", doc)},
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    sign_body = r.get_json()
    assert sign_body["registry"]["ok"] is True

    # document only, no sig -> found via the registry, VALID
    r = db_client.post(
        "/api/verify", data=_upload("file", doc), content_type="multipart/form-data"
    )
    body = r.get_json()
    assert body["status"] == "VALID"
    assert body["signers"][0]["employee_id"] == "EMP10452"

    # never-signed document -> UNVERIFIABLE with the DB-mode failure reason
    r = db_client.post(
        "/api/verify",
        data=_upload("file", b"never signed at all"),
        content_type="multipart/form-data",
    )
    body = r.get_json()
    assert body["status"] == "UNVERIFIABLE"
    assert body["failure_reason"] == "NO_REGISTERED_SIGNATURE"


def test_registry_import_accepts_valid_sig(db_client):
    assert db_client.post("/api/init-ca").status_code == 200
    assert db_client.post(
        "/api/enrol",
        json={"name": "Priya Sharma", "email": "priya@company.internal", "id": "EMP10452"},
    ).status_code == 200

    doc = b"signed offline, imported later"
    r = db_client.post(
        "/api/sign",
        data={"employee_id": "EMP10452", **_upload("file", doc)},
        content_type="multipart/form-data",
    )
    sig_text = r.get_json()["bundle_text"]

    # Not yet visible to DB-mode verify (sign() already registered it via the
    # DB, so re-importing the same bundle is still expected to succeed and
    # simply add a second, source='imported' record).
    r = db_client.post(
        "/api/registry/import",
        data={
            **_upload("file", doc),
            "sig": (io.BytesIO(sig_text.encode()), "report.sig"),
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_registry_import_rejects_tampered_sig(db_client):
    assert db_client.post("/api/init-ca").status_code == 200
    assert db_client.post(
        "/api/enrol",
        json={"name": "Priya Sharma", "email": "priya@company.internal", "id": "EMP10452"},
    ).status_code == 200

    doc = b"original bytes"
    r = db_client.post(
        "/api/sign",
        data={"employee_id": "EMP10452", **_upload("file", doc)},
        content_type="multipart/form-data",
    )
    sig_text = r.get_json()["bundle_text"]

    r = db_client.post(
        "/api/registry/import",
        data={
            **_upload("file", doc + b" tampered after signing"),
            "sig": (io.BytesIO(sig_text.encode()), "report.sig"),
        },
        content_type="multipart/form-data",
    )
    assert r.status_code == 422
    assert r.get_json()["status"] == "TAMPERED"


def test_double_init_ca_is_conflict(client):
    assert client.post("/api/init-ca").status_code == 200
    assert client.post("/api/init-ca").status_code == 409


def test_enrol_without_ca_fails(client):
    r = client.post(
        "/api/enrol",
        json={"name": "X", "email": "x@y.z", "id": "EMP1"},
    )
    assert r.status_code == 400


def test_index_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"<title>docsign</title>" in r.data
