# docsign — internal document signing & verification

A small internal tool that answers exactly two questions about a document you
received from a colleague:

1. **Authenticity** — was this actually sent by the employee who claims to have sent it?
2. **Integrity** — has it changed since they signed it?

Nothing else.

This is a **signing** tool. It does not provide confidentiality — the document
stays fully readable, and is never scrambled or locked. What it adds is a
detached signature that a recipient can check offline.

---

## What it is not

Deliberately cut, and not built:

| Not included | Why |
|---|---|
| Confidentiality / document locking | The requirement is authenticity + integrity. The document is meant to stay readable. |
| Watermarking | Only helps print/scan survivability and registry lookup. Neither is needed. |
| Canonicalisation | We sign raw bytes. Any re-encode *should* fail verification. |
| Online revocation (CRL/OCSP) | Replaced by short-lived (90-day) certificates. |
| OCR / forensics / ML anomaly detection | The cryptography answers the question; these only add failure modes. |
| Cross-organisation trust | Single internal root only. |

An optional **signature registry** (a database) does exist — see
[Signature registry](#signature-registry) below — but it changes the UX, not
the trust model:

> **The database is a signature registry, not a trust authority.** A row in
> it proves nothing by itself; every verification still runs the full
> cryptographic pipeline (chain, expiry, Ed25519 signature) against
> whatever it retrieves. It only removes the need to hand over a `.sig`
> file by hand — offline `.sig` verification still works exactly as before,
> unchanged, whether or not a registry is configured.

---

## Known limits — read these

These are real and are not worked around:

- **Insider fraud is not prevented.** A valid signature by an authorised
  employee on a false document verifies correctly. The system provides
  *accountability*, not *prevention*.
- **Key theft = identity theft.** If an employee's private key is stolen, the
  thief *is* that employee as far as this system is concerned.
- **Partial adoption is the practical weak point.** If unsigned documents are
  routinely accepted, an attacker simply doesn't sign — the tool then reports
  `UNVERIFIABLE`, and what to do about that is an organisational policy
  decision, not a technical one. Stripping a signature is far cheaper than
  forging one, which is why that policy matters more than any of the
  cryptography here.

Related operational note: **enrolment must be driven by verified identity.** A
certificate issued to the wrong person verifies perfectly. In this prototype
`docsign enrol` is a bare admin command with no identity check; a real
deployment must gate it behind an HR/IAM hook.

---

## Cryptographic design

| Component | Choice | Notes |
|---|---|---|
| Hash | SHA-256 | Never MD5 or SHA-1 — both are collision-broken. |
| Signature | Ed25519 | 32-byte keys, 64-byte signatures, deterministic, hard to misuse. |
| Certificates | X.509 | Standard format. |
| Employee cert validity | 90 days | Expiry handles offboarding without a revocation list. |
| Root cert validity | 5 years | Self-signed, `CA:TRUE`. |

**What gets signed is the hash, not the file:**

```
digest    = SHA-256(file_bytes)
signature = Ed25519_Sign(private_key, digest)
```

Signing the 32-byte digest is why verification cost is O(1) in document size.

**Direction of keys:** the *private* key signs, the *public* key verifies.
`crypto.verify_digest()` raises if handed a private key rather than silently
succeeding.

### Why Ed25519

Ed25519 and ECDSA P-256 sit at roughly the same security level (~128-bit).
Neither is meaningfully stronger. The reason to pick Ed25519 here:

- It is the safer primitive. It is deterministic — the per-signature nonce is
  derived from the key and message, so there is no random-nonce reuse failure
  mode (which has repeatedly leaked ECDSA private keys in the wild). It also
  has fewer encoding and point-validation footguns, smaller keys, and faster
  verification.
- The cost is tooling support: X.509 / PAdES / S/MIME / smartcards / PDF
  readers are all built around ECDSA and RSA. Ed25519 is on paper in those
  standards but patchily implemented.

For this system, the verifier we ship is the only thing that checks
signatures — nothing external needs to validate — so we take the safer
primitive. The algorithm lives as a single constant in `crypto.py`.

Switching to ECDSA only becomes worthwhile as part of the Adobe-native PDF path
(not built here), which is a larger design fork than swapping the algorithm.

---

## Trust model

```
Company Root CA  (self-signed, offline key)
        │  signs
        ▼
Employee Certificate  (name, email, employee_id, public key, 90-day validity)
        │  its private key signs
        ▼
Document Signature  (.sig file next to the document)
```

Verification is two signature checks:

1. Does the employee certificate verify against the **root public key**?
2. Does the document signature verify against the **employee public key** from
   that certificate?

**The root public key (`trust/root_ca.pem`) is the single trust anchor.** It
must reach every verifier through a trusted channel — bundled in the installer,
pushed by MDM, or checked into the internal repo. It is never fetched over the
network at verification time. Everything rests on this one step.

---

## Verification is offline

`docsign verify` makes **zero network calls**. Everything it needs is in the
document, the `.sig` bundle, and the local root certificate. There is a test
(`tests/test_verify.py::test_verification_makes_no_network_calls`) that fails
the build if a socket is opened during verification.

---

## Offboarding

Handled by the 90-day certificate window, not a revocation list. When someone
leaves, their certificate is simply not renewed and stops verifying within
90 days.

The tradeoff: **documents signed by a since-expired certificate become
unverifiable.** For a system where document circulation is explicitly not a
concern, that is acceptable. Distinguishing "signed while valid" from "signed
after expiry" would require RFC 3161 trusted timestamping, which is out of
scope.

`EXPIRED` is reported as a distinct status from `TAMPERED` — they mean very
different things.

---

## Install

```
python -m pip install -e .
```

Python 3.11+ and the `cryptography` and `keyring` libraries. Optional extras:
`.[web]` for the local UI (Flask), `.[db]` for the signature registry
(SQLAlchemy + Alembic) — see [Signature registry](#signature-registry).

---

## Usage

```
docsign init-ca                              # admin, once — creates the root CA
docsign enrol --name "Priya Sharma" \        # issue an employee certificate
              --email priya.sharma@company.internal \
              --id EMP10452
docsign sign invoice_q3.pdf                  # writes invoice_q3.pdf.sig
docsign verify invoice_q3.pdf                # DB mode if configured, else .sig
docsign verify invoice_q3.pdf --offline      # force the .sig path
docsign import-sig invoice_q3.pdf invoice_q3.pdf.sig   # add an existing .sig to the registry
```

`docsign verify` only uses the registry if `DOCSIGN_DATABASE_URL` is set —
see [Signature registry](#signature-registry). Without it, nothing changes
from a `.sig`-only deployment.

Verification output leads with the verdict and names the signer:

```
✓ VALID
  Signed by Priya Sharma (EMP10452)
  Document unchanged since signing.
```

```
✗ TAMPERED
  Signed by Priya Sharma (EMP10452)
  Document has been modified after signing. Do not act on it.
```

```
? UNVERIFIABLE
  No signature found.
  This document cannot be verified. Ask the sender to sign and resend.
```

```
⚠ VERIFICATION UNAVAILABLE
  The signature registry could not be reached (timeout after 3s).
  Cryptographic verification was not performed.

  If you have the .sig file, run:
    docsign verify invoice_q3.pdf --offline
```

### Exit codes

Stable — scripts and workflow integrations depend on them. `TAMPERED` and
`INVALID` are separate codes because they mean different things operationally:
`TAMPERED` implies a known signer whose document was changed after signing;
`INVALID` implies the certificate itself isn't trustworthy.
`VERIFICATION_UNAVAILABLE` is a fifth, distinct code because a database
being unreachable is an operational failure, not a verdict about the
document — it must never be confused with `INVALID` or `TAMPERED`.

| Code | Meaning |
|---|---|
| `0` | `VALID` |
| `1` | `TAMPERED` |
| `2` | `UNVERIFIABLE` |
| `3` | `EXPIRED` |
| `4` | `INVALID` |
| `5` | `VERIFICATION_UNAVAILABLE` |

---

## Web frontend

A small local web UI wraps the same modules — verify, sign, and admin
(init-CA + enrol) in one page.

```
python -m pip install -e '.[web]'     # adds Flask
docsign serve                         # opens http://127.0.0.1:8765/
```

- **Local only.** The server binds to `127.0.0.1`. Verification stays offline —
  no external calls (the registry, if configured, is on the same machine or a
  private network — see [Signature registry](#signature-registry)). While it
  is running, this machine can sign as any employee enrolled in its keystore,
  so stop it (`Ctrl-C`) when you are done.
- The page loads no external resources; it works with no internet.
- Signing picks the identity from a dropdown of keystore-enrolled employees.
  The `.sig` comes back as a download; if a registry is configured, signing
  also registers the signature there.
- **Verifying needs only the document** — no `.sig` upload — when a registry
  is configured; it looks the signature up by hash. If the registry can't be
  reached, the page shows `VERIFICATION UNAVAILABLE` and reveals a `.sig`
  upload right there so you can still verify offline. A "Verify with a .sig
  file instead" link is always available regardless of registry state.
- Every verdict — `VALID / TAMPERED / EXPIRED / INVALID / UNVERIFIABLE /
  VERIFICATION UNAVAILABLE` — renders the same way whichever path produced it.

`docsign serve --host`, `--port`, and `--no-browser` are available. The enrolled
list is a local convenience index (`.docsign/enrolled.json`, public metadata
only — no keys).

---

## Key storage

Private keys go in the OS keystore by default, via `keyring`:

- macOS: Keychain
- Windows: Credential Locker (DPAPI/CNG backed)
- Linux: Secret Service, or a passphrase-protected `keyrings.alt` keyfile

A plaintext key file on disk is allowed **only** behind an explicit
`--insecure-keyfile PATH` flag, which prints a warning on every use. That file
holds the employee certificate followed by the private key.

The **root CA private key** is written to a gitignored `.ca/` directory for the
prototype. A real deployment needs hardware-backed storage (HSM / smartcard)
and the root key kept offline.

---

## The `.sig` bundle

JSON, sitting next to the document (`invoice_q3.pdf` → `invoice_q3.pdf.sig`).
Detached rather than embedded to avoid the circular dependency of writing a
signature into the file it signs. Format is versioned (`"version": 1`) from day
one.

```json
{
  "version": 1,
  "algorithm": "Ed25519",
  "hash": "SHA-256",
  "digest": "<hex of SHA-256(document bytes)>",
  "signature": "<base64 Ed25519 signature over the raw digest bytes>",
  "certificate": "<PEM employee certificate>",
  "signed_at": "2026-09-10T14:03:22Z",
  "filename": "invoice_q3.pdf"
}
```

- `signed_at` is **informational only** — asserted by the signer, never used in
  a verification decision. Trusted time would need an RFC 3161 timestamp
  authority.
- `filename` is a convenience for the operator, also not trusted. Verification
  runs on bytes.
- The raw digest bytes are signed, not the hex string.

---

## Verification pipeline

Two paths, both cryptographic, both returning the same `VerificationResult`
shape (never a bare boolean) — see `verify.py`.

### Offline — `.sig` file (`verify_from_sig`, alias of `verify_document`)

In order, short-circuiting on the first failure:

1. `.sig` present and parses as JSON with a known `version` → else `UNVERIFIABLE`
2. Embedded certificate parses → else `INVALID`
3. Certificate chains to the root in `trust/root_ca.pem` → else `INVALID`
4. Certificate is within its validity window → else `EXPIRED`
5. Ed25519 signature verifies over the `digest` claimed in the bundle → else `TAMPERED`
6. Recomputed SHA-256 of the file matches that (now-trustworthy) digest → else `TAMPERED`
7. Otherwise → `VALID`

Step 5 must run before step 6: the Ed25519 signature is what makes the bundle's
`digest` field trustworthy in the first place. Comparing digests before
verifying the signature would let an attacker who controls the `.sig` file
substitute any digest they like — see `tests/test_attacks.py` case 10.

### Registry — signature lookup (`verify_from_db`)

```
1. SHA-256(document bytes) → document_hash
2. registry.lookup_signatures(document_hash)
       empty            → UNVERIFIABLE (failure_reason=NO_REGISTERED_SIGNATURE)
       unreachable/slow  → VERIFICATION_UNAVAILABLE (failure_reason=REGISTRY_UNREACHABLE)
       one or more rows → verify each: parse cert → chain → expiry →
                           Ed25519 signature over document_hash
3. any record VALID       → VALID, with every valid signer listed
   else any record's own signature fails to verify → TAMPERED
       (the *registry row* is inconsistent — this is not the same claim as
       ".sig proves the document was modified", see Signature registry below)
   else all records EXPIRED → EXPIRED
   else                      → INVALID
```

A hash miss can't be told apart from "never signed" — that's why it's
`UNVERIFIABLE`, never `TAMPERED`. See [Signature registry](#signature-registry).

---

## Tests

```
python -m pytest
```

- `tests/test_crypto.py` — core primitives (round-trip, flipped byte, wrong
  key, wrong key direction).
- `tests/test_verify.py` — pipeline behaviour (both paths) and the offline
  path's no-network guarantee.
- `tests/test_attacks.py` — the thirteen offline adversarial cases from the
  build guide plus six DB-mode registry attacks, each asserting a specific
  status.
- `tests/test_registry.py` — registry storage/lookup/revoke unit tests, no
  cryptography.
- `tests/test_web.py` — the web UI's `/api/*` routes, both verify paths and
  the registry import endpoint.

The build guide asks that the attack cases be written by someone who did not
write `verify.py`; that separation was not available for this prototype and a
real deployment must not treat the suite as sufficient on its own.

Registry (DB) tests need the optional `db` extra — they skip cleanly without it.

---

## Signature registry

The registry is an optional UX layer: instead of handing a recipient a `.sig`
file, `docsign sign` (and the web UI) can also register the signature in a
database, keyed by document hash, so `docsign verify` can look it up with
just the document. **It does not change what "verified" means** — read the
guiding rule again:

> The database is a signature registry, not a trust authority. A row in it
> proves nothing by itself; every verification still runs the full
> cryptographic pipeline against whatever it retrieves.

### Configuration

```
export DOCSIGN_DATABASE_URL="sqlite:///docsign.db"   # or a postgresql+psycopg:// URL
```

Unset (the default), `docsign verify` behaves exactly as a `.sig`-only
deployment always has — no registry is attempted. SQLite is the prototype
choice (zero infrastructure, file-based); SQLAlchemy is the ORM specifically
so switching to PostgreSQL is a connection-string change, not a code change.
`DOCSIGN_QUERY_TIMEOUT` (default `3` seconds) bounds every registry call —
a hung connection must not block verification indefinitely.

### Initialise the database

```
python -m pip install -e '.[db]'   # adds SQLAlchemy + Alembic
alembic upgrade head               # creates document_signatures
```

The schema lives in `alembic/versions/0001_initial_registry.py`. Notably
**there is no `valid` or `status` column** — status is always computed by
`verify.py`, never stored, so a compromised database admin cannot flip a bit
to make a bad signature look good. `document_hash` has no unique constraint:
multiple legitimate signers on one document is expected, not an error.

### Importing existing `.sig` files

Nothing is imported without first passing full verification:

```
docsign import-sig invoice_q3.pdf invoice_q3.pdf.sig
```

Only `VALID` (or `EXPIRED` backed by a trusted timestamp) is stored — a
rejected import explains why and nothing is written. For a whole directory:

```
python scripts/bulk_import.py path/to/documents/
```

Walks the directory for `<file>` + `<file>.sig` pairs, imports what
qualifies, and skips anything already registered (same document hash *and*
certificate serial) so it's safe to re-run.

### When the registry is unreachable

`docsign verify` does **not** silently fall back to `.sig` mode — the
operator needs to know cryptographic verification didn't happen at all:

```
⚠ VERIFICATION UNAVAILABLE
  The signature registry could not be reached (timeout after 3s).
  Cryptographic verification was not performed.

  If you have the .sig file, run:
    docsign verify invoice_q3.pdf --offline
```

`docsign verify --offline` (or the web UI's degraded-mode `.sig` upload,
or its always-available "Verify with a .sig file instead" link) is the
fallback the operator drives explicitly.

### Audit logging coverage — including a real gap

Signing and verification events have a documented shape (see `docsign.md`),
but **no audit-log writer is implemented in this prototype** — `config.py`
has an `AUDIT_LOG_ENABLED` toggle for a real deployment to wire up, and
that's as far as it goes here. Concretely:

- **CLI signing (`docsign sign`) is not audited.** It creates the `.sig`
  file and, if a registry is configured, best-effort registers the
  signature there (a `registry: could not register…` notice is printed if
  that fails — the `.sig` file itself is never affected either way) — but no
  audit event fires for the *signing action* in either case. If a registry
  is **not** configured, there is nothing to register either.
- **Do not treat the registry's `created_at` column as an audit trail.** It
  records when a row was inserted, not who verified what and when.
- A real deployment needing audited CLI signing must add that logging
  itself; this prototype only defines the event shapes.

### Key rotation with the registry

No change to rotation itself (see [Offboarding](#offboarding)): a document's
registry row keeps the certificate that was live when it was *signed*, not
whatever is current. Rotating an employee's key does not touch old rows, and
old documents keep verifying against their original embedded certificate —
exactly as the `.sig` path already does.

### Backup

**`docsign.db` (or your configured database) is sensitive: it holds every
signature and every employee certificate ever issued.** It holds no private
keys (those stay in the OS keystore / HSM), but losing it loses the
registry-lookup convenience for every previously signed document — they
remain verifiable only via their original `.sig` files. Back it up like any
other production database.

---

## Repository layout

```
docsign/
├── README.md
├── pyproject.toml
├── alembic.ini
├── alembic/
│   ├── env.py             # reads the DB URL from docsign.config, not this file
│   └── versions/
│       └── 0001_initial_registry.py
├── scripts/
│   └── bulk_import.py     # walk a directory, import every <file>+<file>.sig pair
├── src/docsign/
│   ├── crypto.py          # hashing, signing, verifying — no I/O, no CLI
│   ├── ca.py               # root CA init, employee cert issuance
│   ├── keystore.py         # private key storage and retrieval
│   ├── bundle.py           # .sig file format read/write
│   ├── enrollment.py       # local index of enrolled employees (CLI/web convenience)
│   ├── config.py           # DB URL, query timeout, audit toggle — env-driven
│   ├── registry.py         # signature registry: storage/lookup only, no crypto
│   ├── verify.py           # verify_from_sig + verify_from_db → VerificationResult
│   ├── cli.py              # argument parsing, delegates to the above
│   └── web.py              # local Flask UI + /api/* routes (needs the web extra)
├── tests/
│   ├── test_crypto.py
│   ├── test_verify.py
│   ├── test_attacks.py
│   ├── test_registry.py
│   └── test_web.py
└── trust/
    └── root_ca.pem      # created by `docsign init-ca`; distribute to verifiers
```
