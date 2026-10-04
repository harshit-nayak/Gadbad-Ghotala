# docsign — Technical Pipeline Overview

---

## High-Level Pipeline

A bird's-eye view of the entire system — what flows where, and who trusts whom.

```mermaid
flowchart TB
    subgraph SETUP["🔧 One-Time Setup"]
        A["Admin runs<br/><code>docsign init-ca</code>"] --> B["Root CA<br/>(self-signed, 5-year, Ed25519)"]
        B --> C["<code>trust/root_ca.pem</code><br/>(public cert → all verifiers)"]
        B --> D["<code>.ca/root_ca_key.pem</code><br/>(private key → offline/HSM)"]
    end

    subgraph ENROL["👤 Employee Enrolment"]
        E["Admin runs<br/><code>docsign enrol</code>"] --> F["Employee X.509 Cert<br/>(90-day, CA:FALSE)"]
        F --> G["Private Key → OS Keystore<br/>(Keychain / DPAPI / SecretService)"]
        F --> H["Public Cert + metadata →<br/><code>.docsign/enrolled.json</code>"]
    end

    subgraph SIGN["✍️ Signing"]
        I["Employee picks a document"] --> J["SHA-256 hash the file"]
        J --> K["Ed25519 sign the 32-byte digest"]
        K --> L["Write <code>.sig</code> bundle<br/>(JSON: digest, signature, cert, metadata)"]
        L -.->|"optional"| M["Register in Signature DB"]
    end

    subgraph VERIFY["🔍 Verification"]
        N["Recipient has the document"]
        N --> O{".sig file<br/>available?"}
        O -->|"Yes / --offline"| P["Offline Path<br/><code>verify_from_sig</code>"]
        O -->|"No, DB configured"| Q["Registry Path<br/><code>verify_from_db</code>"]
        P --> R["Verdict:<br/>VALID · TAMPERED · EXPIRED<br/>INVALID · UNVERIFIABLE"]
        Q --> R
    end

    B -.->|"signs"| F
    D -.->|"used by"| E
    G -.->|"used by"| K
    C -.->|"trust anchor for"| P
    C -.->|"trust anchor for"| Q

    style SETUP fill:#1a1a2e,stroke:#e94560,color:#eee
    style ENROL fill:#1a1a2e,stroke:#0f3460,color:#eee
    style SIGN fill:#1a1a2e,stroke:#16213e,color:#eee
    style VERIFY fill:#1a1a2e,stroke:#533483,color:#eee
```

### Summary

| Stage | Input | Output | Key Trust Property |
|---|---|---|---|
| **Init CA** | Admin command | Root keypair + public cert | Single trust anchor for entire org |
| **Enrol** | Name, email, employee ID | 90-day X.509 cert + private key in keystore | Identity bound to key by admin |
| **Sign** | Document file + employee key | Detached `.sig` JSON bundle | Digest signed, not file — O(1) in doc size |
| **Verify** | Document + `.sig` (or DB lookup) | Structured `VerificationResult` | Zero network calls on offline path |

---

## Low-Level Technical Pipeline

### Signing Pipeline (Detail)

```mermaid
flowchart LR
    subgraph crypto_py["crypto.py"]
        A1["<code>hash_file(path)</code><br/>Stream file in chunks"] --> A2["SHA-256 digest<br/>(32 bytes)"]
        A2 --> A3["<code>sign_digest(privkey, digest)</code><br/>Ed25519 deterministic signature"]
        A3 --> A4["Signature<br/>(64 bytes, base64-encoded)"]
    end

    subgraph keystore_py["keystore.py"]
        B1["Retrieve private key<br/>from OS keystore<br/>(or --insecure-keyfile)"]
    end

    subgraph bundle_py["bundle.py"]
        C1["Assemble .sig JSON bundle"]
    end

    B1 --> A3
    A2 -->|"hex-encoded"| C1
    A4 --> C1
    C1 --> D1["<code>document.pdf.sig</code>"]

    style crypto_py fill:#0d1117,stroke:#58a6ff,color:#c9d1d9
    style keystore_py fill:#0d1117,stroke:#f78166,color:#c9d1d9
    style bundle_py fill:#0d1117,stroke:#3fb950,color:#c9d1d9
```

#### `.sig` Bundle Structure
```json
{
  "version": 1,
  "algorithm": "Ed25519",
  "hash": "SHA-256",
  "digest": "<hex SHA-256(document bytes)>",
  "signature": "<base64 Ed25519(private_key, raw_digest_bytes)>",
  "certificate": "<PEM employee X.509 cert>",
  "signed_at": "2026-09-10T14:03:22Z",
  "filename": "invoice_q3.pdf"
}
```

> [!IMPORTANT]
> `signed_at` and `filename` are **informational only** — never trusted in verification decisions. The signature covers the raw digest bytes, not the hex string.

---

### Offline Verification Pipeline (`verify_from_sig`)

Each step short-circuits on failure. The step ordering is security-critical.

```mermaid
flowchart TD
    START["Receive document + .sig path"] --> S1

    S1["<b>Step 1:</b> Parse .sig bundle<br/><code>bundle.read_bundle()</code><br/>JSON + known version + required fields"]
    S1 -->|"fail"| R_UNVERIFIABLE["🔴 UNVERIFIABLE"]
    S1 -->|"ok"| S2

    S2["<b>Step 2:</b> Parse embedded certificate<br/><code>x509.load_pem_x509_certificate()</code>"]
    S2 -->|"fail"| R_INVALID1["🔴 INVALID"]
    S2 -->|"ok"| S3

    S3["<b>Step 3:</b> Chain check<br/><code>cert.verify_directly_issued_by(root_cert)</code><br/>Was this cert issued by our Root CA?"]
    S3 -->|"fail"| R_INVALID2["🔴 INVALID"]
    S3 -->|"ok"| S4

    S4["<b>Step 4:</b> Validity window<br/><code>not_valid_before ≤ now ≤ not_valid_after</code>"]
    S4 -->|"fail"| R_EXPIRED["🟡 EXPIRED"]
    S4 -->|"ok"| S5

    S5["<b>Step 5:</b> Signature check ⚡<br/><code>crypto.verify_digest(pub, claimed_digest, sig)</code><br/>Ed25519 over the digest from the bundle"]
    S5 -->|"fail"| R_TAMPERED1["🔴 TAMPERED<br/>(bundle inconsistent)"]
    S5 -->|"ok"| S6

    S6["<b>Step 6:</b> Digest comparison<br/><code>crypto.hash_file(doc) == claimed_digest</code><br/>Recompute SHA-256, constant-time compare"]
    S6 -->|"mismatch"| R_TAMPERED2["🔴 TAMPERED<br/>(document modified)"]
    S6 -->|"match"| R_VALID["🟢 VALID"]

    style S5 fill:#2d1b00,stroke:#f0883e,color:#ffd700
    style S6 fill:#2d1b00,stroke:#f0883e,color:#ffd700
    style R_VALID fill:#0d3117,stroke:#3fb950,color:#3fb950
    style R_TAMPERED1 fill:#3d0d0d,stroke:#f85149,color:#f85149
    style R_TAMPERED2 fill:#3d0d0d,stroke:#f85149,color:#f85149
    style R_INVALID1 fill:#3d0d0d,stroke:#da3633,color:#da3633
    style R_INVALID2 fill:#3d0d0d,stroke:#da3633,color:#da3633
    style R_EXPIRED fill:#3d2b00,stroke:#d29922,color:#d29922
    style R_UNVERIFIABLE fill:#3d0d0d,stroke:#f85149,color:#f85149
```

> [!CAUTION]
> **Step 5 MUST run before Step 6.** The Ed25519 signature is what makes the bundle's `digest` field trustworthy. If you compare digests first, an attacker who controls the `.sig` can substitute any digest they like — the comparison would pass before the signature check catches the forgery. This ordering is enforced by [test_attacks.py case 10](file:///c:/Users/Uday Raj Malik/Desktop/docPipeline/Gadbad-Ghotala/tests/test_attacks.py).

---

### Registry Verification Pipeline (`verify_from_db`)

Used when `DOCSIGN_DATABASE_URL` is set and no `--offline` flag is given.

```mermaid
flowchart TD
    START["Receive document path"] --> H1

    H1["<b>Step 1:</b> Hash the document<br/><code>SHA-256(file_bytes) → document_hash</code>"]
    H1 --> H2

    H2["<b>Step 2:</b> Lookup in registry<br/><code>registry.lookup_signatures(document_hash)</code><br/>Timeout: DOCSIGN_QUERY_TIMEOUT (default 3s)"]
    H2 -->|"unreachable / timeout"| R_UNAVAIL["⚠️ VERIFICATION_UNAVAILABLE<br/><i>failure_reason=REGISTRY_UNREACHABLE</i>"]
    H2 -->|"empty result"| R_UNVERIF["🔴 UNVERIFIABLE<br/><i>failure_reason=NO_REGISTERED_SIGNATURE</i>"]
    H2 -->|"1+ records"| H3

    H3["<b>Step 3:</b> For each record, run:<br/>parse cert → chain → expiry → Ed25519 sig"]
    H3 --> H4

    H4{"Any record<br/>VALID?"}
    H4 -->|"yes"| R_VALID["🟢 VALID<br/>Lists all valid signers"]
    H4 -->|"no"| H5

    H5{"Any record<br/>TAMPERED?"}
    H5 -->|"yes"| R_TAMPERED["🔴 TAMPERED<br/>Registry row inconsistent"]
    H5 -->|"no"| H6

    H6{"All records<br/>EXPIRED?"}
    H6 -->|"yes"| R_EXPIRED["🟡 EXPIRED"]
    H6 -->|"no"| R_INVALID["🔴 INVALID"]

    style R_VALID fill:#0d3117,stroke:#3fb950,color:#3fb950
    style R_UNAVAIL fill:#3d2b00,stroke:#d29922,color:#d29922
    style R_UNVERIF fill:#3d0d0d,stroke:#f85149,color:#f85149
    style R_TAMPERED fill:#3d0d0d,stroke:#f85149,color:#f85149
    style R_EXPIRED fill:#3d2b00,stroke:#d29922,color:#d29922
    style R_INVALID fill:#3d0d0d,stroke:#da3633,color:#da3633
```

> [!NOTE]
> A hash miss in the registry **cannot** be distinguished from "never signed" — it's always `UNVERIFIABLE`, never `TAMPERED`. `TAMPERED` in DB mode means a stored signature failed its own cryptographic check (a corrupted registry row), which is a different claim than "the document was modified after signing."

---

### Module Dependency Graph

How the source modules call each other at runtime.

```mermaid
flowchart BT
    crypto["<b>crypto.py</b><br/>hash_file · sign_digest · verify_digest<br/><i>Pure functions, no I/O</i>"]
    ca["<b>ca.py</b><br/>init_root · issue_employee_cert<br/>cert_identity"]
    keystore["<b>keystore.py</b><br/>OS keystore read/write"]
    bundle["<b>bundle.py</b><br/>.sig file format"]
    config["<b>config.py</b><br/>env-driven settings"]
    enrollment["<b>enrollment.py</b><br/>enrolled.json index"]
    registry["<b>registry.py</b><br/>DB storage/lookup<br/><i>(optional, SQLAlchemy)</i>"]
    verify["<b>verify.py</b><br/>verify_from_sig · verify_from_db"]
    cli["<b>cli.py</b><br/>argparse + rendering"]
    web["<b>web.py</b><br/>Flask UI + /api/*"]

    verify --> crypto
    verify --> ca
    verify --> bundle
    verify -.->|"lazy import"| registry
    cli --> verify
    cli --> crypto
    cli --> ca
    cli --> keystore
    cli --> bundle
    cli --> enrollment
    cli --> config
    cli -.-> registry
    web --> verify
    web --> crypto
    web --> ca
    web --> keystore
    web --> bundle
    web --> enrollment
    web --> config
    web -.-> registry
    registry --> config

    style crypto fill:#0d1117,stroke:#58a6ff,color:#c9d1d9
    style verify fill:#0d1117,stroke:#a371f7,color:#c9d1d9
    style registry fill:#0d1117,stroke:#f0883e,color:#c9d1d9
```

---

### Exit Code Map

Stable contract — scripts and CI integrations depend on these.

| Exit Code | Status | Meaning |
|:---------:|--------|---------|
| `0` | `VALID` | Signature checks out, document unchanged |
| `1` | `TAMPERED` | Known signer, document modified post-signing |
| `2` | `UNVERIFIABLE` | No signature found at all |
| `3` | `EXPIRED` | Certificate outside validity window |
| `4` | `INVALID` | Certificate doesn't chain to trusted root |
| `5` | `VERIFICATION_UNAVAILABLE` | Registry unreachable (operational, not cryptographic) |

---

### Key Security Invariants

| Invariant | Enforced By |
|---|---|
| Verification makes **zero network calls** | [test_verify.py::test_verification_makes_no_network_calls](file:///c:/Users/Uday Raj Malik/Desktop/docPipeline/Gadbad-Ghotala/tests/test_verify.py) |
| Signature check (step 5) before digest comparison (step 6) | [test_attacks.py case 10](file:///c:/Users/Uday Raj Malik/Desktop/docPipeline/Gadbad-Ghotala/tests/test_attacks.py) |
| Chain check (step 3) before signature check (step 5) | [test_attacks.py case 13](file:///c:/Users/Uday Raj Malik/Desktop/docPipeline/Gadbad-Ghotala/tests/test_attacks.py) |
| Digest comparison uses constant-time `hmac.compare_digest` | [crypto.py::digests_equal](file:///c:/Users/Uday Raj Malik/Desktop/docPipeline/Gadbad-Ghotala/src/docsign/crypto.py) |
| Private keys never logged or serialized | Convention in keystore.py / crypto.py |
| `verify_digest()` rejects private keys | [test_crypto.py](file:///c:/Users/Uday Raj Malik/Desktop/docPipeline/Gadbad-Ghotala/tests/test_crypto.py) |
