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
| Document registry / database | Verification is local. There is nothing to look up. |
| Watermarking | Only helps print/scan survivability and registry lookup. Neither is needed. |
| Canonicalisation | We sign raw bytes. Any re-encode *should* fail verification. |
| Online revocation (CRL/OCSP) | Replaced by short-lived (90-day) certificates. |
| OCR / forensics / ML anomaly detection | The cryptography answers the question; these only add failure modes. |
| Cross-organisation trust | Single internal root only. |

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

Python 3.11+ and the `cryptography` and `keyring` libraries.

---

## Usage

```
docsign init-ca                              # admin, once — creates the root CA
docsign enrol --name "Priya Sharma" \        # issue an employee certificate
              --email priya.sharma@company.internal \
              --id EMP10452
docsign sign invoice_q3.pdf                  # writes invoice_q3.pdf.sig
docsign verify invoice_q3.pdf                # checks it
```

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

### Exit codes

Stable — scripts and workflow integrations depend on them:

| Code | Meaning |
|---|---|
| `0` | `VALID` |
| `1` | `TAMPERED` or `INVALID` |
| `2` | `UNVERIFIABLE` |
| `3` | `EXPIRED` |

---

## Web frontend

A small local web UI wraps the same modules — verify, sign, and admin
(init-CA + enrol) in one page.

```
python -m pip install -e '.[web]'     # adds Flask
docsign serve                         # opens http://127.0.0.1:8765/
```

- **Local only.** The server binds to `127.0.0.1`. Verification stays offline —
  no external calls. While it is running, this machine can sign as any employee
  enrolled in its keystore, so stop it (`Ctrl-C`) when you are done.
- The page loads no external resources; it works with no internet.
- Signing picks the identity from a dropdown of keystore-enrolled employees.
  The `.sig` comes back as a download.
- Verifying takes the document and its `.sig` and shows the same
  `VALID / TAMPERED / EXPIRED / INVALID / UNVERIFIABLE` verdict the CLI prints.

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

In order, short-circuiting on the first failure:

1. `.sig` present and parses as JSON with a known `version` → else `UNVERIFIABLE`
2. Embedded certificate parses → else `INVALID`
3. Certificate chains to the root in `trust/root_ca.pem` → else `INVALID`
4. Certificate is within its validity window → else `EXPIRED`
5. Recomputed SHA-256 of the file matches `digest` → else `TAMPERED`
6. Ed25519 signature verifies over the digest → else `TAMPERED`
7. Otherwise → `VALID`

`verify.py` returns a structured `VerificationResult`, never a bare boolean.

---

## Tests

```
python -m pytest
```

- `tests/test_crypto.py` — core primitives (round-trip, flipped byte, wrong
  key, wrong key direction).
- `tests/test_verify.py` — pipeline behaviour and the no-network guarantee.
- `tests/test_attacks.py` — the twelve adversarial cases from the build guide,
  each asserting a specific status.

The build guide asks that the attack cases be written by someone who did not
write `verify.py`; that separation was not available for this prototype and a
real deployment must not treat the suite as sufficient on its own.

---

## Repository layout

```
docsign/
├── README.md
├── pyproject.toml
├── src/docsign/
│   ├── crypto.py        # hashing, signing, verifying — no I/O, no CLI
│   ├── ca.py            # root CA init, employee cert issuance
│   ├── keystore.py      # private key storage and retrieval
│   ├── bundle.py        # .sig file format read/write
│   ├── verify.py        # verification pipeline → VerificationResult
│   └── cli.py           # argument parsing, delegates to the above
├── tests/
│   ├── test_crypto.py
│   ├── test_verify.py
│   └── test_attacks.py
└── trust/
    └── root_ca.pem      # created by `docsign init-ca`; distribute to verifiers
```
