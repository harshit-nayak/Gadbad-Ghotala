"""A small local web frontend for docsign.

Runs a Flask server bound to localhost. It wraps the existing modules and makes
**no external network calls** — the offline verification guarantee is intact.

    docsign serve

Security note: while this server is running, anyone who can reach the bind
address can sign documents as any employee enrolled in this machine's keystore.
Keep it on 127.0.0.1, and stop it when you are done. It is a prototype
convenience, not a service to leave up.
"""

from __future__ import annotations

import base64
import datetime as _dt
import tempfile
import threading
import webbrowser
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from flask import Flask, Response, jsonify, request, send_file

from . import bundle as _bundle
from . import ca as _ca
from . import config
from . import crypto
from . import keystore
from . import enrollment
from .verify import ImportRejected, Status, VerificationResult, verify_document

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


def _serial_hex(cert) -> str:
    """Colon-hex certificate serial for display — independent of the
    (optional) registry module so it works whether or not SQLAlchemy is
    installed."""
    n = cert.serial_number
    raw = n.to_bytes((n.bit_length() + 7) // 8 or 1, "big")
    return ":".join(f"{b:02X}" for b in raw)


def _signer_json(s) -> dict:
    return {
        "employee_id": s.employee_id,
        "name": s.employee_name,
        "key_id": s.key_id,
        "certificate": {
            "status": s.certificate_status,
            "serial": s.certificate_serial,
            "valid_from": s.certificate_valid_from.strftime("%Y-%m-%dT%H:%M:%SZ")
            if s.certificate_valid_from else None,
            "valid_until": s.certificate_valid_until.strftime("%Y-%m-%dT%H:%M:%SZ")
            if s.certificate_valid_until else None,
        },
        "signature": {
            "algorithm": crypto.SIGNATURE_ALGORITHM,
            "hash_algorithm": crypto.HASH_ALGORITHM,
            "verified": s.signature_verified,
        },
        "timestamp": {
            "present": s.timestamp_present,
            "trusted": s.timestamp_trusted,
        },
    }


def _result_json(result: VerificationResult) -> dict:
    return {
        "status": result.status.value,
        "signature_found": (
            None if result.status is Status.VERIFICATION_UNAVAILABLE
            else result.status is not Status.UNVERIFIABLE
        ),
        "failure_reason": result.failure_reason,
        "document_hash": result.document_digest,
        "signers": [_signer_json(s) for s in result.signers] if result.signers else (
            [_signer_json_from_flat(result)] if result.status is Status.VALID and result.signer_id else []
        ),
        "reason": result.reason,
        "signer_name": result.signer_name,
        "signer_id": result.signer_id,
        "certificate_valid_until": (
            result.certificate_valid_until.strftime("%Y-%m-%d")
            if result.certificate_valid_until else None
        ),
        "document_digest": result.document_digest,
        "document": result.filename,
    }


def _signer_json_from_flat(result: VerificationResult) -> dict:
    """The offline (.sig) path never populates result.signers (only DB mode
    retrieves multiple records) — synthesize a single-entry signers[] from
    its flat fields so /verify and /verify/offline share one response shape."""
    return {
        "employee_id": result.signer_id,
        "name": result.signer_name,
        "key_id": None,
        "certificate": {
            "status": "VALID",
            "serial": None,
            "valid_from": None,
            "valid_until": (
                result.certificate_valid_until.strftime("%Y-%m-%dT%H:%M:%SZ")
                if result.certificate_valid_until else None
            ),
        },
        "signature": {
            "algorithm": crypto.SIGNATURE_ALGORITHM,
            "hash_algorithm": crypto.HASH_ALGORITHM,
            "verified": True,
        },
        "timestamp": {"present": False, "trusted": None},
    }


def create_app(
    *,
    trust_dir: str = "trust",
    ca_dir: str = ".ca",
    state_dir: str = ".docsign",
) -> Flask:
    trust_dir = Path(trust_dir).resolve()
    ca_dir = Path(ca_dir).resolve()
    state_dir = Path(state_dir).resolve()
    root_cert_path = trust_dir / _ca.ROOT_CERT_FILENAME

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES

    # -- helpers --------------------------------------------------------------
    def _ca_info() -> dict | None:
        if not root_cert_path.exists():
            return None
        from cryptography import x509

        cert = x509.load_pem_x509_certificate(root_cert_path.read_bytes())
        return {
            "subject": cert.subject.rfc4514_string(),
            "not_before": cert.not_valid_before_utc.strftime("%Y-%m-%d"),
            "not_after": cert.not_valid_after_utc.strftime("%Y-%m-%d"),
        }

    # -- pages --------------------------------------------------------------
    @app.get("/")
    def index():
        return Response(_PAGE, mimetype="text/html")

    @app.get("/api/status")
    def status():
        return jsonify(
            {
                "ca": _ca_info(),
                "enrolled": [
                    {"id": emp_id, **meta}
                    for emp_id, meta in enrollment.list_enrolled(state_dir).items()
                ],
            }
        )

    @app.get("/api/history")
    def history():
        if not config.DATABASE_CONFIGURED:
            return jsonify({"error": "No signature registry configured."}), 400
        try:
            from . import registry as _registry

            records = _registry.list_recent(limit=100)
        except ImportError:
            return jsonify(
                {"error": "The signature registry needs SQLAlchemy "
                          "(pip install 'docsign[db]')."}
            ), 400
        except Exception as exc:  # registry.RegistryUnavailableError, etc.
            return jsonify({"error": f"Cannot read history: {exc}"}), 503

        return jsonify(
            {
                "records": [
                    {
                        "id": r.id,
                        "filename": r.filename,
                        "document_hash": r.document_hash,
                        "employee_id": r.employee_id,
                        "employee_name": r.employee_name,
                        "certificate_serial": r.certificate_serial,
                        "signed_at": r.signed_at,
                        "source": r.source,
                    }
                    for r in records
                ]
            }
        )

    @app.get("/root_ca.pem")
    def root_ca_pem():
        if not root_cert_path.exists():
            return jsonify({"error": "no root CA"}), 404
        return send_file(
            root_cert_path,
            mimetype="application/x-pem-file",
            as_attachment=True,
            download_name="root_ca.pem",
        )

    # -- admin ------------------------------------------------------------
    @app.post("/api/init-ca")
    def init_ca():
        if root_cert_path.exists():
            return jsonify({"error": "Root CA already exists."}), 409
        _ca.init_root(trust_dir=trust_dir, ca_dir=ca_dir)
        return jsonify({"ok": True, "ca": _ca_info()})

    @app.post("/api/enrol")
    def enrol():
        data = request.get_json(silent=True) or request.form
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip()
        emp_id = (data.get("id") or "").strip()
        if not (name and email and emp_id):
            return jsonify({"error": "name, email and employee ID are all required"}), 400
        try:
            root_cert, root_key = _ca.load_root(trust_dir=trust_dir, ca_dir=ca_dir)
        except FileNotFoundError:
            return jsonify({"error": "No root CA. Initialise it first."}), 400

        cert, key = _ca.issue_employee_cert(root_key, root_cert, name, email, emp_id)
        keystore.store_identity(emp_id, key, cert)
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "default_id").write_text(emp_id, encoding="utf-8")
        enrollment.register(state_dir, cert, email)
        return jsonify(
            {
                "ok": True,
                "id": emp_id,
                "name": name,
                "email": email,
                "not_after": cert.not_valid_after_utc.strftime("%Y-%m-%d"),
            }
        )

    # -- sign -----------------------------------------------------------
    @app.post("/api/sign")
    def sign():
        emp_id = (request.form.get("employee_id") or "").strip()
        upload = request.files.get("file")
        if not emp_id:
            return jsonify({"error": "pick a signer"}), 400
        if upload is None or not upload.filename:
            return jsonify({"error": "choose a document to sign"}), 400

        try:
            key, cert = keystore.load_identity(emp_id)
        except keystore.KeyNotFound as exc:
            return jsonify({"error": str(exc)}), 400

        now = _dt.datetime.now(_dt.timezone.utc)
        if not (cert.not_valid_before_utc <= now <= cert.not_valid_after_utc):
            return jsonify(
                {
                    "error": "This signing certificate is expired "
                    f"(valid until {cert.not_valid_after_utc:%Y-%m-%d}). Re-enrol."
                }
            ), 400

        with tempfile.TemporaryDirectory() as td:
            doc_path = Path(td) / Path(upload.filename).name
            upload.save(doc_path)
            digest = crypto.hash_file(doc_path)

        signature = crypto.sign_digest(key, digest)
        data = _bundle.build_bundle(
            digest=digest,
            signature=signature,
            certificate_pem=cert.public_bytes(serialization.Encoding.PEM),
            filename=Path(upload.filename).name,
        )
        name, sid = _ca.cert_identity(cert)
        import json as _json

        registered = None
        if config.DATABASE_CONFIGURED:
            try:
                from . import registry as _registry

                signature_id = _registry.store_signature(
                    document_hash=digest.hex(),
                    signature=base64.b64encode(signature).decode("ascii"),
                    certificate_pem=cert.public_bytes(serialization.Encoding.PEM).decode("ascii"),
                    employee_id=sid or "UNKNOWN",
                    employee_name=name or "Unknown",
                    key_id=_registry.compute_key_id(cert),
                    signed_at=data["signed_at"],
                    filename=Path(upload.filename).name,
                    timestamp_token=None,
                )
                registered = {"ok": True, "signature_id": signature_id}
            except ImportError as exc:
                registered = {"ok": False, "error": str(exc)}
            except Exception as exc:  # registry.RegistryUnavailableError, etc.
                registered = {"ok": False, "error": str(exc)}

        return jsonify(
            {
                "status": "SIGNED",
                "ok": True,
                "sig_filename": Path(upload.filename).name + _bundle.SIG_SUFFIX,
                "bundle_text": _json.dumps(data, indent=2) + "\n",
                "signer": f"{name} ({sid})",
                "digest": digest.hex(),
                "document_hash": digest.hex(),
                "signed_at": data["signed_at"],
                "certificate_serial": _serial_hex(cert),
                "registry": registered,
            }
        )

    # -- verify (DB mode, default) --------------------------------------
    @app.post("/api/verify")
    def verify():
        doc = request.files.get("file")
        if doc is None or not doc.filename:
            return jsonify({"error": "choose a document to verify"}), 400

        from .verify import verify_from_db

        with tempfile.TemporaryDirectory() as td:
            doc_path = Path(td) / Path(doc.filename).name
            doc.save(doc_path)
            result = verify_from_db(doc_path, root_cert_path=root_cert_path)

        return jsonify(_result_json(result))

    # -- verify (offline .sig path, explicit) ---------------------------
    @app.post("/api/verify/offline")
    def verify_offline():
        doc = request.files.get("file")
        sig = request.files.get("sig")
        if doc is None or not doc.filename:
            return jsonify({"error": "choose a document to verify"}), 400
        if sig is None or not sig.filename:
            return jsonify({"error": "choose the document's .sig file"}), 400

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            doc_path = td / Path(doc.filename).name
            doc.save(doc_path)
            sig_path = td / (Path(doc.filename).name + _bundle.SIG_SUFFIX)
            sig.save(sig_path)

            result = verify_document(
                doc_path, sig_path=sig_path, root_cert_path=root_cert_path
            )

        return jsonify(_result_json(result))

    # -- registry import (admin) -----------------------------------------
    @app.post("/api/registry/import")
    def registry_import():
        doc = request.files.get("file")
        sig = request.files.get("sig")
        if doc is None or not doc.filename:
            return jsonify({"error": "choose a document to import"}), 400
        if sig is None or not sig.filename:
            return jsonify({"error": "choose the document's .sig file"}), 400

        from .verify import import_verified_sig

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            doc_path = td / Path(doc.filename).name
            doc.save(doc_path)
            sig_path = td / (Path(doc.filename).name + _bundle.SIG_SUFFIX)
            sig.save(sig_path)

            try:
                record_id, result = import_verified_sig(
                    doc_path, sig_path, root_cert_path=root_cert_path
                )
            except ImportRejected as exc:
                body = _result_json(exc.result)
                body["error"] = (
                    f"Cannot import: {exc.result.status.value} — {exc.result.reason}"
                )
                return jsonify(body), 422
            except ImportError:
                return jsonify(
                    {"error": "The signature registry needs SQLAlchemy "
                              "(pip install 'docsign[db]')."}
                ), 400
            except Exception as exc:  # registry.RegistryUnavailableError, etc.
                return jsonify({"error": f"Cannot import: {exc}"}), 503

        body = _result_json(result)
        body["ok"] = True
        body["signature_id"] = record_id
        return jsonify(body)

    @app.errorhandler(413)
    def too_large(_):
        return jsonify({"error": "file too large (limit 200 MB)"}), 413

    return app


def run_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    trust_dir: str = "trust",
    ca_dir: str = ".ca",
    state_dir: str = ".docsign",
    open_browser: bool = True,
) -> int:
    app = create_app(trust_dir=trust_dir, ca_dir=ca_dir, state_dir=state_dir)
    url = f"http://{host}:{port}/"
    print(f"docsign web frontend  ->  {url}")
    print("  Local only. While this is running, anyone who can reach the bind")
    print("  address can sign as any enrolled employee. Stop it (Ctrl-C) when done.")
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(f"  WARNING: bound to {host}, not localhost.")
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        app.run(host=host, port=port, debug=False, use_reloader=False)
    except KeyboardInterrupt:  # pragma: no cover
        pass
    return 0


# --------------------------------------------------------------------------- #
# single-file page — no external resources, works offline
# --------------------------------------------------------------------------- #
_PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>docsign</title>
<style>
  :root {
    --bg: #f6f7f9; --panel: #ffffff; --ink: #1b1f24; --muted: #616a75;
    --line: #dfe3e8; --accent: #2f6feb;
    --ok-bg:#e7f6ec; --ok-ink:#1a7f37; --ok-line:#9bd6ac;
    --bad-bg:#fdecec; --bad-ink:#c02626; --bad-line:#f0a8a8;
    --warn-bg:#fdf3e3; --warn-ink:#9a6700; --warn-line:#e6c98a;
    --grey-bg:#eef0f2; --grey-ink:#4a525b; --grey-line:#cfd4da;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg:#14171a; --panel:#1d2125; --ink:#e7eaee; --muted:#9aa4af;
      --line:#2c3238; --accent:#4d8bff;
      --ok-bg:#12301d; --ok-ink:#5fd88a; --ok-line:#26543a;
      --bad-bg:#3a1717; --bad-ink:#ff8a8a; --bad-line:#5e2a2a;
      --warn-bg:#33280f; --warn-ink:#f0c274; --warn-line:#5c4a20;
      --grey-bg:#24282d; --grey-ink:#aab2bb; --grey-line:#3a4149;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--ink);
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  .wrap { max-width: 760px; margin: 0 auto; padding: 32px 20px 64px; }
  h1 { font-size: 22px; margin: 0 0 2px; letter-spacing: .2px; }
  .sub { color: var(--muted); margin: 0 0 20px; font-size: 13.5px; }
  .note {
    background: var(--warn-bg); color: var(--warn-ink);
    border: 1px solid var(--warn-line); border-radius: 8px;
    padding: 9px 12px; font-size: 12.5px; margin-bottom: 22px;
  }
  .tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--line); margin-bottom: 22px; }
  .tab {
    appearance: none; background: none; border: none; cursor: pointer;
    font: inherit; color: var(--muted); padding: 9px 14px; border-radius: 8px 8px 0 0;
    border-bottom: 2px solid transparent;
  }
  .tab[aria-selected="true"] { color: var(--ink); border-bottom-color: var(--accent); font-weight: 600; }
  .panel {
    background: var(--panel); border: 1px solid var(--line);
    border-radius: 12px; padding: 20px;
  }
  .panel + .panel { margin-top: 16px; }
  h2 { font-size: 15px; margin: 0 0 14px; }
  label { display: block; font-size: 13px; color: var(--muted); margin: 12px 0 5px; }
  label:first-of-type { margin-top: 0; }
  input[type=text], input[type=email], select, input[type=file] {
    width: 100%; font: inherit; color: var(--ink); background: var(--bg);
    border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px;
  }
  input[type=file] { padding: 7px; }
  button.go {
    appearance: none; margin-top: 16px; cursor: pointer; font: inherit; font-weight: 600;
    background: var(--accent); color: #fff; border: none; border-radius: 8px;
    padding: 9px 16px;
  }
  button.go:disabled { opacity: .5; cursor: default; }
  button.ghost {
    appearance: none; cursor: pointer; font: inherit; background: var(--bg);
    color: var(--ink); border: 1px solid var(--line); border-radius: 8px; padding: 7px 12px;
  }
  .verdict { border-radius: 10px; padding: 14px 16px; margin-top: 18px; border: 1px solid; }
  .verdict h3 { margin: 0 0 4px; font-size: 16px; letter-spacing: .3px; }
  .verdict p { margin: 2px 0 0; font-size: 13.5px; }
  .v-ok    { background: var(--ok-bg);   color: var(--ok-ink);   border-color: var(--ok-line); }
  .v-bad   { background: var(--bad-bg);  color: var(--bad-ink);  border-color: var(--bad-line); }
  .v-warn  { background: var(--warn-bg); color: var(--warn-ink); border-color: var(--warn-line); }
  .v-grey  { background: var(--grey-bg); color: var(--grey-ink); border-color: var(--grey-line); }
  table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font-weight: 600; }
  .pill { font-size: 11px; padding: 1px 7px; border-radius: 999px; border: 1px solid; }
  .pill.exp { background: var(--bad-bg); color: var(--bad-ink); border-color: var(--bad-line); }
  .pill.live { background: var(--ok-bg); color: var(--ok-ink); border-color: var(--ok-line); }
  .muted { color: var(--muted); font-size: 13px; }
  code { font-family: ui-monospace, "SF Mono", Consolas, monospace; font-size: 12px; word-break: break-all; }
  [hidden] { display: none !important; }
</style>
</head>
<body>
<div class="wrap">
  <h1>docsign</h1>
  <p class="sub">Internal document signing &amp; verification — authenticity + integrity. Not confidentiality; the document stays readable.</p>
  <div class="note">Local tool. While this page is open, this machine can sign documents as any enrolled employee. Close the server when you are done.</div>

  <div class="tabs" role="tablist">
    <button class="tab" role="tab" data-tab="verify" aria-selected="true">Verify</button>
    <button class="tab" role="tab" data-tab="sign" aria-selected="false">Sign</button>
    <button class="tab" role="tab" data-tab="admin" aria-selected="false">Admin</button>
  </div>

  <!-- VERIFY -->
  <section id="tab-verify" class="panel">
    <h2>Verify a document</h2>
    <p class="muted">Upload the document — its signature is looked up in the registry. No <code>.sig</code> file needed.</p>
    <label>Document</label>
    <input type="file" id="v-doc">
    <button class="go" id="v-go">Verify</button>
    <div id="v-out"></div>

    <div id="v-degraded" hidden>
      <label>Signature file (<code>.sig</code>)</label>
      <input type="file" id="v-sig-degraded">
      <button class="go" id="v-go-degraded">Verify offline</button>
    </div>

    <p class="muted" style="margin-top:16px">
      <button class="ghost" id="v-offline-toggle" type="button">Verify with a .sig file instead</button>
    </p>
    <div id="v-offline-form" hidden>
      <label>Document</label>
      <input type="file" id="v-off-doc">
      <label>Signature file (<code>.sig</code>)</label>
      <input type="file" id="v-off-sig">
      <button class="go" id="v-off-go">Verify offline</button>
      <div id="v-off-out"></div>
    </div>
  </section>

  <!-- SIGN -->
  <section id="tab-sign" class="panel" hidden>
    <h2>Sign a document</h2>
    <div id="s-nobody" class="muted" hidden>No one is enrolled yet. Use the Admin tab first.</div>
    <div id="s-form">
      <label>Sign as</label>
      <select id="s-who"></select>
      <label>Document</label>
      <input type="file" id="s-doc">
      <button class="go" id="s-go">Sign</button>
    </div>
    <div id="s-out"></div>
  </section>

  <!-- ADMIN -->
  <section id="tab-admin" hidden>
    <div class="panel">
      <h2>Root Certificate Authority</h2>
      <div id="a-ca"></div>
    </div>
    <div class="panel">
      <h2>Enrol an employee</h2>
      <p class="muted">In a real deployment this must be gated behind verified identity — a cert issued to the wrong person verifies perfectly.</p>
      <label>Full name</label>
      <input type="text" id="a-name" placeholder="Priya Sharma">
      <label>Email</label>
      <input type="email" id="a-email" placeholder="priya.sharma@company.internal">
      <label>Employee ID</label>
      <input type="text" id="a-id" placeholder="EMP10452">
      <button class="go" id="a-go">Enrol</button>
      <div id="a-out"></div>
    </div>
    <div class="panel">
      <h2>Enrolled on this machine</h2>
      <div id="a-list"></div>
    </div>
  </section>
</div>

<script>
const $ = s => document.querySelector(s);
const el = (t, props={}, kids=[]) => {
  const n = document.createElement(t);
  Object.assign(n, props);
  for (const k of [].concat(kids)) n.append(k);
  return n;
};

// tabs
document.querySelectorAll('.tab').forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll('.tab').forEach(b => b.setAttribute('aria-selected', b === btn));
    for (const name of ['verify', 'sign', 'admin']) {
      $('#tab-' + name).hidden = (name !== btn.dataset.tab);
    }
    if (btn.dataset.tab !== 'verify') refresh();
  };
});

const VERDICT = {
  VALID:                    { cls: 'v-ok',   glyph: '✓', head: 'VALID' },
  TAMPERED:                 { cls: 'v-bad',  glyph: '✗', head: 'TAMPERED' },
  INVALID:                  { cls: 'v-bad',  glyph: '✗', head: 'INVALID' },
  EXPIRED:                  { cls: 'v-warn', glyph: '!', head: 'EXPIRED' },
  UNVERIFIABLE:             { cls: 'v-grey', glyph: '?', head: 'UNVERIFIABLE' },
  VERIFICATION_UNAVAILABLE: { cls: 'v-warn', glyph: '⚠', head: 'VERIFICATION UNAVAILABLE' },
};

function showVerdict(target, r) {
  const v = VERDICT[r.status] || VERDICT.UNVERIFIABLE;
  const box = el('div', { className: 'verdict ' + v.cls });
  box.append(el('h3', { textContent: v.glyph + '  ' + v.head }));
  const signers = (r.signers && r.signers.length) ? r.signers : null;
  if (signers) {
    for (const s of signers) {
      const who = (s.name || 'unknown') + (s.employee_id ? ' (' + s.employee_id + ')' : '');
      box.append(el('p', { textContent: 'Signed by ' + who }));
    }
  } else if (r.signer_name || r.signer_id) {
    const who = (r.signer_name || 'unknown') + (r.signer_id ? ' (' + r.signer_id + ')' : '');
    box.append(el('p', { textContent: 'Signed by ' + who }));
  }
  if (r.certificate_valid_until) {
    box.append(el('p', { textContent: 'Certificate valid until ' + r.certificate_valid_until }));
  }
  box.append(el('p', { textContent: r.reason }));
  if (r.document_hash || r.document_digest) {
    box.append(el('p', {}, el('code', { textContent: 'SHA-256 ' + (r.document_hash || r.document_digest) })));
  }
  target.replaceChildren(box);
  return v;
}

function err(target, msg) {
  target.replaceChildren(el('div', { className: 'verdict v-bad' }, el('p', { textContent: msg })));
}

// verify — DB mode, document only (default UX)
$('#v-go').onclick = async () => {
  const out = $('#v-out');
  const doc = $('#v-doc').files[0];
  if (!doc) return err(out, 'Choose a document.');
  const fd = new FormData();
  fd.append('file', doc);
  out.textContent = 'Verifying…';
  $('#v-degraded').hidden = true;
  try {
    const res = await fetch('/api/verify', { method: 'POST', body: fd });
    const j = await res.json();
    if (!res.ok) return err(out, j.error || 'verification failed');
    showVerdict(out, j);
    if (j.status === 'VERIFICATION_UNAVAILABLE') {
      // Degrade gracefully: reveal the .sig upload right here rather than
      // making the operator hunt for the secondary offline form.
      $('#v-degraded').hidden = false;
    }
  } catch (e) { err(out, String(e)); }
};

// verify — degraded path, revealed only after VERIFICATION_UNAVAILABLE
$('#v-go-degraded').onclick = async () => {
  const out = $('#v-out');
  const doc = $('#v-doc').files[0];
  const sig = $('#v-sig-degraded').files[0];
  if (!doc) return err(out, 'Choose a document.');
  if (!sig) return err(out, 'Choose the .sig file.');
  const fd = new FormData();
  fd.append('file', doc);
  fd.append('sig', sig);
  out.textContent = 'Verifying offline…';
  try {
    const res = await fetch('/api/verify/offline', { method: 'POST', body: fd });
    const j = await res.json();
    if (!res.ok) return err(out, j.error || 'verification failed');
    showVerdict(out, j);
  } catch (e) { err(out, String(e)); }
};

// verify — secondary "I have a .sig file" form, always available
$('#v-offline-toggle').onclick = () => {
  $('#v-offline-form').hidden = !$('#v-offline-form').hidden;
};
$('#v-off-go').onclick = async () => {
  const out = $('#v-off-out');
  const doc = $('#v-off-doc').files[0];
  const sig = $('#v-off-sig').files[0];
  if (!doc) return err(out, 'Choose a document.');
  if (!sig) return err(out, 'Choose the .sig file.');
  const fd = new FormData();
  fd.append('file', doc);
  fd.append('sig', sig);
  out.textContent = 'Verifying offline…';
  try {
    const res = await fetch('/api/verify/offline', { method: 'POST', body: fd });
    const j = await res.json();
    if (!res.ok) return err(out, j.error || 'verification failed');
    showVerdict(out, j);
  } catch (e) { err(out, String(e)); }
};

// sign
$('#s-go').onclick = async () => {
  const out = $('#s-out');
  const doc = $('#s-doc').files[0];
  const who = $('#s-who').value;
  if (!who) return err(out, 'Pick a signer.');
  if (!doc) return err(out, 'Choose a document.');
  const fd = new FormData();
  fd.append('file', doc);
  fd.append('employee_id', who);
  out.textContent = 'Signing…';
  try {
    const res = await fetch('/api/sign', { method: 'POST', body: fd });
    const j = await res.json();
    if (!res.ok) return err(out, j.error || 'signing failed');
    const blob = new Blob([j.bundle_text], { type: 'application/json' });
    const a = el('a', {
      href: URL.createObjectURL(blob),
      download: j.sig_filename,
      textContent: 'Download ' + j.sig_filename,
      className: 'ghost',
    });
    a.style.display = 'inline-block';
    a.style.marginTop = '10px';
    const box = el('div', { className: 'verdict v-ok' });
    box.append(el('h3', { textContent: '✓  Signed' }));
    box.append(el('p', { textContent: 'By ' + j.signer } ));
    box.append(el('p', {}, el('code', { textContent: 'SHA-256 ' + j.digest })));
    if (j.registry) {
      box.append(el('p', {
        className: j.registry.ok ? 'muted' : '',
        style: j.registry.ok ? '' : 'color:var(--bad-ink)',
        textContent: j.registry.ok
          ? 'Registered in signature registry (record id ' + j.registry.signature_id + ') — DB-mode verify will find it.'
          : 'Not registered in the signature registry: ' + j.registry.error + ' — the .sig file below is unaffected; DB-mode verify will show UNVERIFIABLE for this document unless you import it later.',
      }));
    } else {
      box.append(el('p', { className: 'muted', textContent: 'No signature registry configured — .sig file only. DB-mode verify (document only, no upload) will not find this signature.' }));
    }
    box.append(a);
    out.replaceChildren(box);
  } catch (e) { err(out, String(e)); }
};

// admin: enrol
$('#a-go').onclick = async () => {
  const out = $('#a-out');
  const body = {
    name: $('#a-name').value.trim(),
    email: $('#a-email').value.trim(),
    id: $('#a-id').value.trim(),
  };
  if (!body.name || !body.email || !body.id) return err(out, 'All three fields are required.');
  out.textContent = 'Enrolling…';
  try {
    const res = await fetch('/api/enrol', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const j = await res.json();
    if (!res.ok) return err(out, j.error || 'enrolment failed');
    out.replaceChildren(el('div', { className: 'verdict v-ok' },
      el('p', { textContent: 'Enrolled ' + j.name + ' (' + j.id + ') — certificate valid until ' + j.not_after })));
    $('#a-name').value = $('#a-email').value = $('#a-id').value = '';
    refresh();
  } catch (e) { err(out, String(e)); }
};

async function initCA() {
  const res = await fetch('/api/init-ca', { method: 'POST' });
  const j = await res.json();
  if (!res.ok) alert(j.error || 'init failed');
  refresh();
}

function renderCA(ca) {
  const box = $('#a-ca');
  if (!ca) {
    box.replaceChildren(
      el('p', { className: 'muted', textContent: 'No root CA on this machine yet.' }),
      el('button', { className: 'go', textContent: 'Initialise Root CA', onclick: initCA }),
    );
    return;
  }
  const dl = el('a', { href: '/root_ca.pem', className: 'ghost', textContent: 'Download root_ca.pem' });
  dl.style.display = 'inline-block'; dl.style.marginTop = '10px';
  box.replaceChildren(
    el('p', {}, el('code', { textContent: ca.subject })),
    el('p', { className: 'muted', textContent: 'Valid ' + ca.not_before + ' → ' + ca.not_after }),
    el('p', { className: 'muted', textContent: 'Distribute this file to every verifier through a trusted channel.' }),
    dl,
  );
}

function renderEnrolled(list) {
  // sign tab dropdown
  const sel = $('#s-who');
  sel.replaceChildren(...list.map(e => el('option', { value: e.id, textContent: e.name + ' (' + e.id + ')' + (e.expired ? ' — expired' : '') })));
  $('#s-nobody').hidden = list.length > 0;
  $('#s-form').hidden = list.length === 0;

  // admin table
  const box = $('#a-list');
  if (!list.length) { box.replaceChildren(el('p', { className: 'muted', textContent: 'Nobody enrolled yet.' })); return; }
  const rows = list.map(e => el('tr', {}, [
    el('td', {}, el('code', { textContent: e.id })),
    el('td', { textContent: e.name || '' }),
    el('td', { textContent: e.email || '' }),
    el('td', { textContent: (e.not_after || '').slice(0, 10) }),
    el('td', {}, el('span', { className: 'pill ' + (e.expired ? 'exp' : 'live'), textContent: e.expired ? 'expired' : 'valid' })),
  ]));
  const table = el('table', {}, [
    el('thead', {}, el('tr', {}, ['ID', 'Name', 'Email', 'Expires', ''].map(h => el('th', { textContent: h })))),
    el('tbody', {}, rows),
  ]);
  box.replaceChildren(table);
}

async function refresh() {
  try {
    const j = await (await fetch('/api/status')).json();
    renderCA(j.ca);
    renderEnrolled(j.enrolled || []);
  } catch (e) { /* offline-ish; ignore */ }
}
refresh();
</script>
</body>
</html>
"""
