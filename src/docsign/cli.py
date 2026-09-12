"""Command-line interface. Argument parsing only — the real work lives in the
other modules.

    docsign init-ca                 # admin, once
    docsign enrol --name --email --id
    docsign sign <file>
    docsign verify <file>           # DB mode if configured, else .sig
    docsign verify <file> --offline # force the offline .sig path
    docsign import-sig <file> <file>.sig

Exit codes (stable — scripts depend on them):
    0  valid
    1  tampered
    2  unverifiable
    3  expired
    4  invalid
    5  verification unavailable (registry unreachable/timed out — not a
       verdict about the document; see docsign verify --offline)
"""

from __future__ import annotations

import argparse
import base64
import datetime as _dt
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization

from . import ca as _ca
from . import bundle as _bundle
from . import config
from . import crypto
from . import keystore
from . import enrollment
from .verify import ImportRejected, Status, VerificationResult, verify_document, verify_from_db

DEFAULT_TRUST_DIR = Path("trust")
DEFAULT_CA_DIR = Path(".ca")
DEFAULT_STATE_DIR = Path(".docsign")

EXIT_OK = 0
EXIT_TAMPERED = 1
EXIT_UNVERIFIABLE = 2
EXIT_EXPIRED = 3
EXIT_INVALID = 4
EXIT_VERIFICATION_UNAVAILABLE = 5
EXIT_BAD = 1  # generic command failure (e.g. bad args, missing CA) — not a verdict code

_STATUS_EXIT = {
    Status.VALID: EXIT_OK,
    Status.TAMPERED: EXIT_TAMPERED,
    Status.UNVERIFIABLE: EXIT_UNVERIFIABLE,
    Status.EXPIRED: EXIT_EXPIRED,
    Status.INVALID: EXIT_INVALID,
    Status.VERIFICATION_UNAVAILABLE: EXIT_VERIFICATION_UNAVAILABLE,
}


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_init_ca(args: argparse.Namespace) -> int:
    trust_dir = Path(args.trust_dir)
    ca_dir = Path(args.ca_dir)
    root_cert = trust_dir / _ca.ROOT_CERT_FILENAME
    if root_cert.exists() and not args.force:
        print(
            f"Root CA already exists at {root_cert}. Refusing to overwrite "
            "(use --force to replace it and invalidate every issued cert).",
            file=sys.stderr,
        )
        return EXIT_BAD
    cert, _ = _ca.init_root(trust_dir=trust_dir, ca_dir=ca_dir)
    print(f"Initialised root CA: {root_cert}")
    print(f"  subject : {cert.subject.rfc4514_string()}")
    print(f"  valid   : {cert.not_valid_before_utc:%Y-%m-%d} .. "
          f"{cert.not_valid_after_utc:%Y-%m-%d}")
    print(f"  private key: {ca_dir / _ca.ROOT_KEY_FILENAME} (keep offline / gitignored)")
    print(f"\nDistribute {root_cert} to every verifier through a trusted channel.")
    return EXIT_OK


def cmd_enrol(args: argparse.Namespace) -> int:
    try:
        root_cert, root_key = _ca.load_root(
            trust_dir=args.trust_dir, ca_dir=args.ca_dir
        )
    except FileNotFoundError:
        print("No root CA found. Run 'docsign init-ca' first.", file=sys.stderr)
        return EXIT_BAD

    cert, key = _ca.issue_employee_cert(
        root_key, root_cert, args.name, args.email, args.id
    )
    keystore.store_identity(
        args.id, key, cert, insecure_keyfile=args.insecure_keyfile
    )

    if not args.insecure_keyfile:
        state = Path(args.state_dir)
        state.mkdir(parents=True, exist_ok=True)
        (state / "default_id").write_text(args.id, encoding="utf-8")
        enrollment.register(state, cert, args.email)

    where = args.insecure_keyfile or "OS keystore"
    print(f"Enrolled {args.name} ({args.id})")
    print(f"  email     : {args.email}")
    print(f"  cert valid: {cert.not_valid_before_utc:%Y-%m-%d} .. "
          f"{cert.not_valid_after_utc:%Y-%m-%d}  (90 days)")
    print(f"  key stored: {where}")
    return EXIT_OK


def _resolve_signer_id(args: argparse.Namespace) -> str | None:
    if args.id:
        return args.id
    default = Path(args.state_dir) / "default_id"
    if default.exists():
        return default.read_text(encoding="utf-8").strip()
    return None


def cmd_sign(args: argparse.Namespace) -> int:
    document = Path(args.file)
    if not document.is_file():
        print(f"No such file: {document}", file=sys.stderr)
        return EXIT_BAD

    signer_id = _resolve_signer_id(args)
    try:
        key, cert = keystore.load_identity(
            signer_id, insecure_keyfile=args.insecure_keyfile
        )
    except keystore.KeyNotFound as exc:
        print(f"Cannot sign: {exc}", file=sys.stderr)
        return EXIT_BAD

    now = _dt.datetime.now(_dt.timezone.utc)
    if not (cert.not_valid_before_utc <= now <= cert.not_valid_after_utc):
        print(
            "Cannot sign: your signing certificate is expired "
            f"(valid until {cert.not_valid_after_utc:%Y-%m-%d}). "
            "Re-enrol to get a fresh certificate.",
            file=sys.stderr,
        )
        return EXIT_EXPIRED

    digest = crypto.hash_file(document)
    signature = crypto.sign_digest(key, digest)
    data = _bundle.build_bundle(
        digest=digest,
        signature=signature,
        certificate_pem=cert.public_bytes(serialization.Encoding.PEM),
        filename=document.name,
    )
    out = _bundle.sig_path_for(document)
    _bundle.write_bundle(out, data)

    name, emp_id = _ca.cert_identity(cert)
    print(f"Signed {document.name} as {name} ({emp_id})")
    print(f"  -> {out}")

    # Best-effort registry registration. The .sig file above is the durable,
    # offline-verifiable artefact regardless of what happens here — DB
    # storage is a convenience, never a requirement for a sign to succeed.
    # If DATABASE_URL isn't configured at all, this is silently skipped: no
    # DB was asked for, so there is nothing to report (see the README's
    # "CLI signing audit gap" note — no audit event fires for this signing
    # action in that case).
    if config.DATABASE_CONFIGURED:
        try:
            from . import registry as _registry

            record_id = _registry.store_signature(
                document_hash=digest.hex(),
                signature=base64.b64encode(signature).decode("ascii"),
                certificate_pem=cert.public_bytes(serialization.Encoding.PEM).decode("ascii"),
                employee_id=emp_id or "UNKNOWN",
                employee_name=name or "Unknown",
                key_id=_registry.compute_key_id(cert),
                signed_at=data["signed_at"],
                filename=document.name,
                timestamp_token=None,
            )
        except ImportError:
            print(
                "  registry: DATABASE_URL is set but SQLAlchemy is not installed "
                "(pip install 'docsign[db]') — .sig only, not registered.",
                file=sys.stderr,
            )
        except Exception as exc:  # registry.RegistryUnavailableError, etc.
            print(
                f"  registry: could not register this signature ({exc}) — "
                ".sig file above is unaffected.",
                file=sys.stderr,
            )
        else:
            print(f"  registered in signature registry (record id {record_id})")

    return EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    # Explicit --offline, or an explicit --sig path, both mean "I have a
    # .sig file, use it" — the offline path is fully deterministic then.
    # Otherwise: DB mode is the default only if a registry has actually been
    # configured — either DOCSIGN_DATABASE_URL is set, or this invocation
    # explicitly passed --database-url. An unconfigured deployment falls
    # back to .sig transparently, matching pre-registry behaviour.
    db_configured = config.DATABASE_CONFIGURED or bool(args.database_url)
    use_offline = args.offline or bool(args.sig) or not db_configured

    if use_offline:
        result = verify_document(args.file, sig_path=args.sig, root_cert_path=args.root)
    else:
        result = verify_from_db(
            args.file, root_cert_path=args.root, database_url=args.database_url
        )

    _render(result)
    return _STATUS_EXIT[result.status]


def cmd_import_sig(args: argparse.Namespace) -> int:
    from .verify import import_verified_sig

    try:
        record_id, result = import_verified_sig(
            args.file,
            args.sig,
            root_cert_path=args.root,
            database_url=args.database_url,
        )
    except ImportRejected as exc:
        print(
            f"Cannot import: {exc.result.status.value} — {exc.result.reason}",
            file=sys.stderr,
        )
        return _STATUS_EXIT.get(exc.result.status, EXIT_BAD)
    except ImportError:
        print(
            "The signature registry needs SQLAlchemy. Install it with:\n"
            "    python -m pip install 'docsign[db]'",
            file=sys.stderr,
        )
        return EXIT_BAD
    except Exception as exc:  # registry.RegistryUnavailableError, etc.
        print(f"Cannot import: {exc}", file=sys.stderr)
        return EXIT_VERIFICATION_UNAVAILABLE

    print(f"Imported {Path(args.file).name} into the registry (record id {record_id}).")
    print(f"  status at import: {result.status.value}")
    return EXIT_OK


# --------------------------------------------------------------------------- #
# rendering — verdict first, signer named, no interpretation required
# --------------------------------------------------------------------------- #
_GLYPH_UNICODE = {
    Status.VALID: "✓ VALID",
    Status.TAMPERED: "✗ TAMPERED",
    Status.EXPIRED: "! EXPIRED",
    Status.INVALID: "✗ INVALID",
    Status.UNVERIFIABLE: "? UNVERIFIABLE",
    Status.VERIFICATION_UNAVAILABLE: "⚠ VERIFICATION UNAVAILABLE",
}
_GLYPH_ASCII = {
    Status.VALID: "[ OK ] VALID",
    Status.TAMPERED: "[FAIL] TAMPERED",
    Status.EXPIRED: "[WARN] EXPIRED",
    Status.INVALID: "[FAIL] INVALID",
    Status.UNVERIFIABLE: "[ ?? ] UNVERIFIABLE",
    Status.VERIFICATION_UNAVAILABLE: "[WARN] VERIFICATION UNAVAILABLE",
}

_ACTION = {
    Status.VALID: None,
    Status.TAMPERED: "DO NOT ACCEPT THIS DOCUMENT.",
    Status.EXPIRED: "Historical validity requires trusted timestamp evidence if "
    "available.\n  Ask the sender to re-enrol and re-sign.",
    Status.INVALID: "DO NOT ACCEPT THIS DOCUMENT.",
    Status.UNVERIFIABLE: "DO NOT ACCEPT AS AUTHENTICATED.\n  Ask the sender to sign "
    "and resend.",
    # VERIFICATION_UNAVAILABLE's action is built in _render (it names the file).
}


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover - stream may not support it
            pass


def _glyphs() -> dict:
    enc = (getattr(sys.stdout, "encoding", "") or "").lower()
    return _GLYPH_UNICODE if "utf" in enc else _GLYPH_ASCII


def _render(result: VerificationResult) -> None:
    r = result
    print(_glyphs()[r.status])
    print()

    if len(r.signers) > 1:
        print("Signers")
        for s in r.signers:
            line = s.employee_name or "unknown"
            if s.employee_id:
                line += f" ({s.employee_id})"
            print(f"  {line}")
        print()
    elif r.signer_name or r.signer_id:
        print("Signer")
        print(f"  {r.signer_name or 'unknown'}")
        if r.signer_id:
            print(f"  Employee ID: {r.signer_id}")
        print()

    if r.certificate_valid_until is not None:
        print("Certificate")
        cert_status = "EXPIRED" if r.status is Status.EXPIRED else "VALID"
        print(f"  Status: {cert_status}")
        if r.status is Status.EXPIRED:
            print(f"  Expired: {r.certificate_valid_until:%Y-%m-%d}")
        else:
            print(f"  Valid until: {r.certificate_valid_until:%Y-%m-%d}")
        print()

    if r.filename:
        print("Document")
        print(f"  Filename: {r.filename}")
        if r.status is Status.TAMPERED:
            print("  Digest status: MISMATCH")
        elif r.document_digest:
            print(f"  SHA-256: {r.document_digest}")
        print()

    if r.status in (Status.VALID, Status.TAMPERED):
        print("Signature")
        print(f"  Algorithm: {crypto.SIGNATURE_ALGORITHM}")
        print(f"  Status: {'VERIFIED' if r.status is Status.VALID else 'INVALID'}")
        print()

    if r.status is Status.VALID:
        print("Integrity")
        print(f"  {r.reason}")
    else:
        print(f"  {r.reason}")

    action = _ACTION.get(r.status)
    if r.status is Status.VERIFICATION_UNAVAILABLE and r.filename:
        action = (
            "If you have the .sig file, run:\n"
            f"    docsign verify {r.filename} --offline"
        )
    if action:
        print()
        print("Action")
        print(f"  {action}")


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="docsign",
        description="Internal document signing & verification "
        "(authenticity + integrity; not encryption).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    ic = sub.add_parser("init-ca", help="initialise the internal root CA (admin, once)")
    ic.add_argument("--trust-dir", default=str(DEFAULT_TRUST_DIR))
    ic.add_argument("--ca-dir", default=str(DEFAULT_CA_DIR))
    ic.add_argument("--force", action="store_true", help="overwrite an existing root CA")
    ic.set_defaults(func=cmd_init_ca)

    en = sub.add_parser("enrol", help="issue an employee signing certificate")
    en.add_argument("--name", required=True)
    en.add_argument("--email", required=True)
    en.add_argument("--id", required=True, help="employee ID (the durable identifier)")
    en.add_argument("--trust-dir", default=str(DEFAULT_TRUST_DIR))
    en.add_argument("--ca-dir", default=str(DEFAULT_CA_DIR))
    en.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    en.add_argument(
        "--insecure-keyfile",
        metavar="PATH",
        help="store the private key as a plaintext file instead of the OS keystore",
    )
    en.set_defaults(func=cmd_enrol)

    sg = sub.add_parser("sign", help="sign a document, writing <file>.sig")
    sg.add_argument("file")
    sg.add_argument("--id", help="employee ID to sign as (defaults to last enrolled)")
    sg.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    sg.add_argument(
        "--insecure-keyfile",
        metavar="PATH",
        help="load the private key from a plaintext file",
    )
    sg.set_defaults(func=cmd_sign)

    vf = sub.add_parser(
        "verify",
        help="verify a document — signature registry by default if configured, "
        "else its <file>.sig",
    )
    vf.add_argument("file")
    vf.add_argument("--sig", help="path to the .sig bundle (implies --offline)")
    vf.add_argument(
        "--offline", action="store_true",
        help="force the offline .sig path even if a registry is configured",
    )
    vf.add_argument(
        "--database-url", default=None,
        help="override the signature registry connection string "
        "(default: DOCSIGN_DATABASE_URL / sqlite:///docsign.db)",
    )
    vf.add_argument(
        "--root",
        default=str(DEFAULT_TRUST_DIR / _ca.ROOT_CERT_FILENAME),
        help="path to the trusted root certificate",
    )
    vf.set_defaults(func=cmd_verify)

    im = sub.add_parser(
        "import-sig",
        help="verify a .sig bundle and, if it qualifies, store it in the registry",
    )
    im.add_argument("file")
    im.add_argument("sig")
    im.add_argument(
        "--root",
        default=str(DEFAULT_TRUST_DIR / _ca.ROOT_CERT_FILENAME),
        help="path to the trusted root certificate",
    )
    im.add_argument(
        "--database-url", default=None,
        help="override the signature registry connection string",
    )
    im.set_defaults(func=cmd_import_sig)

    sv = sub.add_parser("serve", help="run the local web frontend (sign / verify / admin)")
    sv.add_argument("--host", default="127.0.0.1", help="bind address (default: localhost)")
    sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--trust-dir", default=str(DEFAULT_TRUST_DIR))
    sv.add_argument("--ca-dir", default=str(DEFAULT_CA_DIR))
    sv.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    sv.add_argument("--no-browser", action="store_true", help="do not open a browser")
    sv.set_defaults(func=cmd_serve)

    return p


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        from .web import run_server
    except ImportError:
        print(
            "The web frontend needs Flask. Install it with:\n"
            "    python -m pip install 'docsign[web]'   (or: pip install flask)",
            file=sys.stderr,
        )
        return EXIT_BAD
    return run_server(
        host=args.host,
        port=args.port,
        trust_dir=args.trust_dir,
        ca_dir=args.ca_dir,
        state_dir=args.state_dir,
        open_browser=not args.no_browser,
    )


def main(argv: list[str] | None = None) -> int:
    _configure_output()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
