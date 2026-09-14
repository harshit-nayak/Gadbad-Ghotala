#!/usr/bin/env python
"""Bulk-import existing ``.sig`` files into the signature registry.

    python scripts/bulk_import.py <directory> [--database-url URL] [--root PATH]

Walks <directory> for ``<file>`` + ``<file>.sig`` pairs, runs the full
verification pipeline against each (same as ``docsign import-sig``), and
stores everything that qualifies (``VALID``, or ``EXPIRED`` backed by a
trusted timestamp) in the registry. Nothing is imported without first
passing verification.

Already-registered signatures — same document hash *and* certificate serial
already present in the registry — are skipped rather than re-inserted, so
this script is safe to re-run over the same directory.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docsign import bundle as _bundle  # noqa: E402
from docsign import ca as _ca  # noqa: E402
from docsign import config  # noqa: E402
from docsign import crypto  # noqa: E402
from docsign.verify import ImportRejected, import_verified_sig  # noqa: E402


def find_pairs(root: Path):
    """Yield ``(document_path, sig_path)`` for every file under *root* that
    has a matching ``<file>.sig`` sibling."""
    for sig_path in sorted(root.rglob("*" + _bundle.SIG_SUFFIX)):
        doc_path = sig_path.with_name(sig_path.name[: -len(_bundle.SIG_SUFFIX)])
        if doc_path.is_file():
            yield doc_path, sig_path


def _certificate_serial(certificate_pem: str) -> str:
    from cryptography import x509

    from docsign import registry

    cert = x509.load_pem_x509_certificate(certificate_pem.encode("ascii"))
    return registry.compute_certificate_serial(cert)


def already_registered(document_path: Path, sig_path: Path, database_url: str) -> bool:
    """Look up by the *actual* recomputed document hash, never the bundle's
    own claimed ``digest`` field — that field is exactly what an attacker
    (or, here, a simple copy/paste mistake pairing the wrong .sig with a
    document) can make say anything. Trusting it for a "already imported,
    skip" decision would silently skip verifying a mismatched pair instead
    of correctly rejecting it."""
    from docsign import registry

    try:
        data = _bundle.read_bundle(sig_path)
        serial = _certificate_serial(data["certificate"])
    except (_bundle.BundleError, ValueError, KeyError):
        return False
    actual_hash = crypto.hash_file(document_path).hex()
    try:
        existing = registry.lookup_signatures(actual_hash, database_url=database_url)
    except registry.RegistryUnavailableError:
        return False
    return any(r.certificate_serial == serial for r in existing)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument(
        "--root", default=str(Path("trust") / _ca.ROOT_CERT_FILENAME),
        help="path to the trusted root certificate",
    )
    p.add_argument(
        "--database-url", default=None,
        help="override the signature registry connection string "
        "(default: DOCSIGN_DATABASE_URL / sqlite:///docsign.db)",
    )
    args = p.parse_args(argv)

    if not args.directory.is_dir():
        print(f"Not a directory: {args.directory}", file=sys.stderr)
        return 2

    database_url = args.database_url or config.DATABASE_URL

    pairs = list(find_pairs(args.directory))
    if not pairs:
        print(f"No <file> + <file>.sig pairs found under {args.directory}")
        return 0

    imported = skipped = rejected = 0
    for doc_path, sig_path in pairs:
        if already_registered(doc_path, sig_path, database_url):
            print(f"SKIP     {doc_path} (already in the registry)")
            skipped += 1
            continue
        try:
            record_id, result = import_verified_sig(
                doc_path, sig_path, root_cert_path=args.root, database_url=database_url,
            )
        except ImportRejected as exc:
            print(f"REJECTED {doc_path}: {exc.result.status.value} — {exc.result.reason}")
            rejected += 1
        except Exception as exc:  # ImportError (no sqlalchemy) / RegistryUnavailableError
            print(f"ERROR    {doc_path}: {exc}")
            rejected += 1
        else:
            print(f"IMPORTED {doc_path} (record id {record_id}, status {result.status.value})")
            imported += 1

    print()
    print(f"{imported} imported, {skipped} skipped (already registered), {rejected} rejected")
    return 1 if rejected else 0


if __name__ == "__main__":
    sys.exit(main())
