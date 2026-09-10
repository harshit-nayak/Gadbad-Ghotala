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


def _upload(name, data):
    return {name: (io.BytesIO(data), name)}


def test_full_flow_sign_then_verify(client):
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
        "/api/verify",
        data={
            **_upload("file", doc),
            "sig": (io.BytesIO(sig_text.encode()), "report.sig"),
        },
        content_type="multipart/form-data",
    )
    assert r.get_json()["status"] == "VALID"

    # tampered doc -> TAMPERED
    r = client.post(
        "/api/verify",
        data={
            **_upload("file", doc + b"!"),
            "sig": (io.BytesIO(sig_text.encode()), "report.sig"),
        },
        content_type="multipart/form-data",
    )
    assert r.get_json()["status"] == "TAMPERED"

    # no sig -> UNVERIFIABLE
    r = client.post(
        "/api/verify",
        data=_upload("file", doc),
        content_type="multipart/form-data",
    )
    assert r.get_json()["status"] == "UNVERIFIABLE"


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
