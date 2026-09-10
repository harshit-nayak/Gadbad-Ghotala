# Internal Document Signing & Verification — Build Guide

A build spec for an internal tool that answers exactly two questions about a document
received from a colleague:

1. **Authenticity** — was this actually sent by the employee who claims to have sent it?
2. **Integrity** — has it changed since they signed it?

Nothing else. Read the Scope section before writing code.

---

## 1. Scope

### In scope
- Per-employee signing keys, issued by an internal Certificate Authority
- Detached signatures over arbitrary file types
- Local verification with no network calls
- Certificate expiry to handle offboarding
- CLI for enrolment, signing, and verification

### Explicitly out of scope
Do not build these. They were considered and deliberately cut.

| Excluded | Why |
|---|---|
| Encryption | Requirement is authenticity + integrity, not confidentiality. The document stays readable. |
| Document registry / database | Verification is local. Nothing to look up. |
| Watermarking | Only useful for print/scan survivability and registry lookup. Neither is needed. |
| Canonicalisation | We sign raw bytes. Any re-encode *should* fail verification. |
| Replay / context binding | Circulation is explicitly not a concern. |
| Online revocation (CRL/OCSP) | Replaced by short-lived certificates. |
| OCR, forensics, ML anomaly detection | Cryptography answers the question. These add failure modes, not security. |
| Cross-organisation trust | Single internal root only. |

### Known limits — state these in the README, do not paper over them
- **Insider fraud is not prevented.** A valid signature by an authorised employee on a false
  document verifies correctly. The system provides accountability, not prevention.
- **Key theft = identity theft.** If a private key is stolen, the thief is that employee to
  this system.
- **Partial adoption is the practical weak point.** If unsigned documents are routinely
  accepted, an attacker simply doesn't sign. The tool reports `UNVERIFIABLE`; policy about
  what to do with that is organisational, not technical.

---

## 2. Cryptographic design

This is **signing**, not encryption. Terminology matters in the README.

| Component | Choice | Notes |
|---|---|---|
| Hash | SHA-256 | Never MD5 or SHA-1 — both are collision-broken. |
| Signature | Ed25519 | Fast, 32-byte keys, 64-byte signatures, hard to misuse. |
| Certificates | X.509 | Standard format, works with existing tooling. |
| Cert validity | 90 days | Expiry handles offboarding without a revocation list. |

### Why Ed25519

Ed25519 and ECDSA P-256 are both elliptic-curve schemes at roughly the same security level
(~128-bit). Neither is meaningfully stronger. The split is:

- **Ed25519 is the safer primitive.** It is deterministic — the per-signature nonce is
  derived from the key and message. ECDSA requires a fresh random nonce every time, and a
  reused or predictable nonce leaks the private key from two signatures. That is a real,
  repeatedly-exploited failure mode, not a theoretical one. Ed25519 also has fewer encoding
  and point-validation footguns, plus smaller keys and faster verification.
- **ECDSA P-256 is the better-supported one.** X.509, PAdES, S/MIME, smartcards, HSMs and
  every PDF reader are built around ECDSA and RSA. Ed25519 appears in these standards on
  paper but tooling support is patchy to absent.

For this system the verifier we build is the only thing that checks signatures — nothing
external needs to validate — so take the safer primitive. Keep the algorithm as a single
constant in `crypto.py` regardless, not a choice scattered across modules.

Switching to ECDSA is only worthwhile as part of the Adobe-native path in Section 12, which
is a larger change than swapping the algorithm.

**Direction of keys:** the *private* key signs, the *public* key verifies. This is the
reverse of encryption's usual direction. A frequent source of bugs — assert it in tests.

**What gets signed:** the hash, not the file.

```
digest    = SHA-256(file_bytes)
signature = Ed25519_Sign(private_key, digest)
```

Signing a 32-byte digest instead of the file is why this is O(1) in document size.

---

## 3. Trust model

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
2. Does the document signature verify against the **employee public key** from that cert?

**The root public key is the single trust anchor.** It must reach every verifier through a
trusted channel — bundled in the installer, pushed by MDM, checked into the internal repo.
Never fetched over the network at verification time. Everything rests on this one step.

---

## 4. Repository layout

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
│   └── cli.py           # argument parsing only, delegates to the above
├── tests/
│   ├── test_crypto.py
│   ├── test_verify.py
│   └── test_attacks.py  # the adversarial suite — see section 9
└── trust/
    └── root_ca.pem      # public root cert, distributed to all verifiers
```

Use Python 3.11+ with the `cryptography` library. Keep `crypto.py` pure — no file I/O, no
printing — so the attack tests can call it directly.

---

## 5. Data formats

### Signature bundle (`document.pdf.sig`)

JSON, sitting alongside the document. Detached rather than embedded: it avoids the circular
dependency of signing a file that then has the signature written into it.

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

Notes for the implementer:
- `signed_at` is **informational only**. It is asserted by the signer and not independently
  trustworthy. Do not use it in any verification decision. If trusted time is ever needed,
  that requires an RFC 3161 timestamp authority — out of scope here.
- `filename` is a convenience for the operator, also not trusted. Verification runs on bytes.
- Sign the raw digest bytes, not the hex string. Be consistent between sign and verify or
  everything fails confusingly.

### Employee certificate subject fields

```
CN = Priya Sharma
emailAddress = priya.sharma@company.internal
serialNumber = EMP10452          # employee ID — the durable identifier
O = Company Name
```

`CN` and email can change. The employee ID is what the verifier should surface to the operator.

---

## 6. Build phases

Build in this order. Each phase must pass its tests before starting the next.

### Phase 1 — Core crypto (`crypto.py`)
- `hash_file(path) -> bytes`, streaming in chunks so large files don't load into memory
- `sign_digest(private_key, digest) -> bytes`
- `verify_digest(public_key, digest, signature) -> bool`

Tests: round-trip signs and verifies; a single flipped byte in the digest fails; a signature
from a different key fails; verifying with the *private* key raises rather than silently
succeeding.

### Phase 2 — Certificate authority (`ca.py`)
- `init_root(output_dir)` — generate a self-signed root, 5-year validity, `CA:TRUE` basic
  constraint. Write the public cert to `trust/root_ca.pem`.
- `issue_employee_cert(root_key, root_cert, name, email, employee_id) -> (cert, private_key)`
  — 90-day validity, `CA:FALSE`, `digitalSignature` key usage.

Enrolment must be driven by verified identity. In a real deployment that means an HR/IAM
hook. For the prototype, an explicit admin command is fine — but say in the README that
unverified enrolment breaks the whole model, because a cert issued to the wrong person
verifies perfectly.

### Phase 3 — Key storage (`keystore.py`)
Private keys go in the OS keystore where available:
- macOS: Keychain
- Windows: DPAPI / CNG
- Linux: Secret Service, falling back to an encrypted file with a passphrase

A plaintext key file on disk is acceptable *only* behind an explicit `--insecure-keyfile`
flag, and the flag should print a warning every time it is used.

### Phase 4 — Signing (`bundle.py` + CLI)
```
docsign sign invoice_q3.pdf
→ writes invoice_q3.pdf.sig
```
Fail loudly if the signing certificate is expired. Do not offer to sign anyway.

### Phase 5 — Verification (`verify.py`)
The pipeline, in order, short-circuiting on the first failure:

1. `.sig` present and parses as valid JSON with a known `version` → else `UNVERIFIABLE`
2. Embedded certificate parses → else `INVALID`
3. Certificate chains to the root in `trust/root_ca.pem` → else `INVALID`
4. Certificate is within its validity window → else `EXPIRED`
5. Recomputed SHA-256 of the file matches `digest` → else `TAMPERED`
6. Ed25519 signature verifies over the digest → else `TAMPERED`
7. Otherwise → `VALID`

Return a structured result, never a bare boolean:

```python
@dataclass
class VerificationResult:
    status: Status          # VALID | TAMPERED | EXPIRED | INVALID | UNVERIFIABLE
    signer_name: str | None
    signer_id: str | None
    reason: str             # one plain-English line for the operator
```

### Phase 6 — CLI (`cli.py`)
```
docsign init-ca                 # admin, once
docsign enrol --name --email --id
docsign sign <file>
docsign verify <file>
```

Verification output must lead with the verdict and name the signer. An operator glancing at
this under time pressure should not have to interpret anything:

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

Exit codes: `0` valid, `1` tampered/invalid, `2` unverifiable, `3` expired. Scripts and
workflow integrations depend on these being stable.

---

## 7. Verification is offline

`verify` must make **zero network calls**. Everything needed is in the file, the `.sig`, and
the local root certificate. Add a test that fails the build if a socket is opened during
verification — this property is easy to lose accidentally once someone adds a "convenience"
lookup.

---

## 8. Offboarding

Handled by the 90-day certificate window rather than a revocation list. When someone leaves,
their certificate is simply not renewed and stops verifying within 90 days.

The tradeoff, which belongs in the README: **documents signed by a since-expired certificate
become unverifiable.** For a system where circulation is explicitly not a concern, that is
acceptable. If long-term verifiability is ever needed, it requires RFC 3161 timestamping so
"signed while the cert was valid" can be distinguished from "signed after expiry."

Treat `EXPIRED` as distinct from `TAMPERED` in the output. They mean very different things
and collapsing them will confuse operators.

---

## 9. Attack test suite (`tests/test_attacks.py`)

These are the tests that demonstrate the system actually works. Each must assert a specific
status, not merely "not valid."

| # | Attack | Expected |
|---|---|---|
| 1 | Unmodified signed document | `VALID` |
| 2 | One byte flipped in the document | `TAMPERED` |
| 3 | Trailing whitespace appended | `TAMPERED` |
| 4 | PDF re-saved through another tool | `TAMPERED` |
| 5 | `.sig` deleted (downgrade attack) | `UNVERIFIABLE` |
| 6 | `.sig` from document A paired with document B | `TAMPERED` |
| 7 | Self-signed cert not chaining to the root | `INVALID` |
| 8 | Cert from a *different* root CA | `INVALID` |
| 9 | Certificate past its validity window | `EXPIRED` |
| 10 | `digest` field edited to match a tampered file | `TAMPERED` (signature covers the digest) |
| 11 | `signed_at` backdated | `VALID` — timestamp is not trusted, and the test documents that |
| 12 | Malformed / truncated `.sig` | `UNVERIFIABLE`, no crash |

Case 10 is the important one — it proves the digest is inside the signed data rather than
being trusted as-is. Case 5 is the realistic attack: stripping a signature is far cheaper
than forging one, which is why organisational policy on `UNVERIFIABLE` matters more than any
cryptography here.

Have someone who did not write `verify.py` produce additional attack cases. Self-authored
attack suites are circular.

---

## 10. Implementation notes

- Stream file hashing in chunks; do not read whole documents into memory.
- Use constant-time comparison for any digest equality check (`hmac.compare_digest`).
- Never log private key material, not even truncated.
- Version the `.sig` format from day one (`"version": 1`) so the format can change later.
- Keep `verify.py` free of `print` — return the result, let the CLI render it.
- The root CA private key should not live in the repository. For the prototype, generate it
  into a gitignored directory and note in the README that a real deployment needs
  hardware-backed storage.

---

## 11. Stretch goal — Adobe-native PDF signatures

Optional. Do not start this until Section 10's definition of done is met.

Getting a green checkmark inside Adobe Reader is a strong demo, but it is a design fork
rather than a configuration change. Three things are required together, and all three must
hold or the demo shows a yellow warning triangle instead:

1. **ECDSA P-256 instead of Ed25519.** Adobe Reader does not validate Ed25519 signatures.
2. **Embedded signature instead of a detached `.sig`.** Adobe only reads signatures inside
   the PDF, per PAdES / ISO 32000 byte-range signing. This means signing a defined byte
   range that excludes the signature field itself, then appending the signature via PDF
   incremental update. It replaces the detached design in Section 5 — it does not sit
   alongside it.
3. **Root certificate installed in Adobe's own trust store** on every verifying machine.
   Adobe does not consult `trust/root_ca.pem`. Without this step the signature validates
   cryptographically but displays as "validity unknown."

Point 3 is the one that gets forgotten and then fails in front of an audience. If this path
is attempted, test it on a machine that has never had the root installed.

Scope consequence: this only applies to PDFs. The detached design in Section 5 works on any
file type, so keep it as the general path even if the Adobe route is added for PDFs.

---

## 12. Definition of done

- [ ] `init-ca`, `enrol`, `sign`, `verify` all work end to end
- [ ] All twelve attack tests pass with the exact expected status
- [ ] Verification makes no network calls (enforced by test)
- [ ] Private keys are in the OS keystore by default
- [ ] Exit codes are stable and documented
- [ ] README states the three known limits from Section 1 plainly
- [ ] README uses "signing" and never "encryption"
