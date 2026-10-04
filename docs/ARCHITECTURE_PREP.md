# Architecture Q&A Prep — Live Call Deepfake Detection + Document Pipeline

Internal prep notes for presentation Q&A. Not user-facing documentation —
written so you can defend design choices under questioning, not to explain
the project to a stranger from scratch.

**Official framing** (from the SIH pitch deck): Problem Statement SIH26104,
"AI-Powered Real-Time Detection and Prevention of Voice Cloning Impersonation
Attacks," Theme: Blockchain & Cybersecurity, Team **Gadbad Ghotala**, product
name **Pehchaan AI**.

---

## 0. Deck vs. actual build — read this section first

The pitch deck describes a broader product than what's currently implemented
in this repo. This is the section most likely to trip you up if a judge has
read the deck closely and then asks to see something specific run. Know
exactly which claims are real, which are partial, and which are slideware —
and have an honest one-line answer ready for each.

| Deck claims | Actually built (this repo) | Honest answer if asked |
|---|---|---|
| "Speaker & speaking fingerprint" — voice + speaking-pattern embeddings matched against a database of employee/caller embeddings via cosine similarity (Pinecone/pgvector/Qdrant) | **Not implemented.** No embedding extraction, no vector DB, no cosine-similarity matching anywhere in `call-monitor/`. The system only classifies real-vs-synthetic per window; it does not identify *who* is speaking. | "Speaker identity verification is on the roadmap / architecture diagram; the current build focuses on the spoof/bona-fide classification layer, which is the harder and more time-critical piece." |
| Audio ingestion via **Twilio** (phone-call piping, on-device hashing before reaching servers) | **Not implemented.** Actual ingestion is WASAPI loopback + mic capture from **WhatsApp Desktop** via a Windows client, streamed over a plain WebSocket. No Twilio integration, no telephony piping. | "The demo path is WhatsApp Desktop calls via WASAPI loopback, which is what we could build and test end-to-end in the time available. Twilio/SIP ingestion is a swap-in at the transport layer — the VAD → model → risk pipeline downstream is transport-agnostic." |
| Non-ML techniques: **watermark detection, codec-artifact analysis, prosody analysis, pause analysis, breathing-pattern analysis** | **Not implemented.** The only non-ML component actually in the pipeline is VAD (Silero, a small ML model itself) plus a placeholder RMS/spectral-flatness heuristic used only when no real detector loads. No watermarking, no prosody/breathing feature extraction. | "These are the planned pre-filter layer to cut compute before the heavy model runs — not yet built. Today the acoustic/spectral layer (XLSR-Mamba) is the whole detection story." |
| **Edge inference** / on-device computing, "data only processed over RAM" | **Partially true in spirit, not in the deck's literal sense.** Inference runs on **CPU** (not a phone/edge device — a laptop backend), which does keep it off a GPU/cloud accelerator, but it's a server-style FastAPI backend, not on-device inference inside a phone app. Audio *is* written to disk by default (recordings), which directly contradicts "zero data retention" / "processed only over RAM" — see the privacy section below. | "CPU inference on commodity hardware, yes — genuinely edge-deployable without a GPU. 'Zero retention' is the target for production; the current build records everything to disk by default for debugging/demo traceability, which we'd turn off (`RECORD_LOCALLY=false` etc.) for a real deployment." |
| **22+ Indian languages** supported | The fine-tuned head was trained on **three** languages: Hindi, Bengali, Tamil (IndicVoices-R + IndicSynth). "22+ languages" is the scale of the underlying multilingual datasets/XLS-R pretraining in principle, not what the fine-tune actually specialized on. | "The backbone (XLS-R) is pretrained multilingually, but our fine-tuning — the part that actually detects deepfakes well — targeted three languages first: Hindi, Bengali, Tamil. Scaling the fine-tune to more Indic languages is the direct next step, same recipe, more data." |
| Weighted/EMA risk score, three-tier verdict, alerts, dashboard | **Matches.** Session risk EMA + 3-band (`likely_real`/`uncertain`/`likely_synthetic`) verdict, `/ws/monitor` dashboard fan-out — this part of the deck accurately describes the build. | No gap — can demo this directly. |
| Document signing: SHA-256 hash → Ed25519 signature, cert chain check (root CA, validity window, integrity, key match) on verify | **Matches closely.** `docPipeline` (docsign) implements exactly this: SHA-256 digest, Ed25519 signature, X.509 chain to a root CA, expiry check, tamper check, `VALID`/`TAMPERED`/`EXPIRED`/`INVALID`/`UNVERIFIABLE` verdicts. The deck's "two-tier X.509 certificate chain" = root CA → employee cert, which is exactly the implemented trust model. | No gap — can demo this directly, including the CLI or web UI. |
| Latency claim: "<30 minutes" (feasibility slide) vs. "in seconds" (impact slide) vs. measured reality | Measured on real calls: **~0.8s/window model inference, ~2.2s/window end-to-end** including VAD and windowing overhead — i.e. verdicts genuinely arrive in seconds during a live call, consistent with the impact slide, not the (much looser) 30-minute figure on the feasibility slide, which reads like it was written for a batch/non-real-time framing. | If asked to reconcile: "per-window latency is ~2 seconds in practice; the call itself can obviously run much longer, which is likely what the 30-minute figure on that slide refers to — the risk score itself updates continuously throughout, not at the end." |

**Bottom line if pressed**: the deck describes the target *product* (Pehchaan
AI); what's built and demoable today is the **core detection pipeline**
(VAD → per-utterance windowing → XLSR-Mamba → 3-band risk) plus a fully
separate, fully working **document integrity pipeline** (docsign). Speaker
identity, telephony ingestion, and the non-ML forensic layers are designed
but not yet implemented — be upfront about that distinction rather than
implying they're all live.

---

## 1. The end-to-end pipeline, in one picture

```
WhatsApp Desktop call
      │ plays far-party audio to your output device
      ▼
WASAPI loopback (far) ──┐         Microphone (near) ──┐
      │ 16k mono, anti-aliased    │ 16k mono, anti-aliased
      ▼                           ▼
   chunker (4s default)        chunker (4s default)
      │                           │
      └──────────► WebSocket ◄────┘
                       │
              FastAPI backend (call-monitor/backend)
                       │
        ┌──────────────┴───────────────────────┐
        │  event loop: ack + record to disk     │
        │              │                        │
        │              ▼ (worker thread)        │
        │   Silero VAD ──► speech accumulator   │
        │              │  (per-utterance)       │
        │              ▼ every 64,600 samples   │
        │   XLSR-Mamba (Indic head) ──► score   │
        │              │                        │
        │              ▼                        │
        │   3-band label + session risk EMA     │
        └───────────────┬───────────────────────┘
                         ▼
             live verdict stream (/ws/audio ack,
             /ws/monitor fan-out to dashboards)
```

Separately, **docPipeline** (docsign) is a document authenticity/integrity
signer+verifier — cryptographic, not ML — that the frontend exposes alongside
the call monitor as the "sign/verify a document" arm of the same fraud-
prevention suite. It shares no runtime code with the audio side; the
connection is only at the product/UX layer (one dashboard, two kinds of
verification).

---

## 2. Why VAD (Silero) sits in front of the model at all

**Q: Why not just feed the model 4-second audio chunks directly?**

- The model (XLSR-Mamba) is a *speech* anti-spoofing classifier. A fixed
  4s wall-clock slice of the "far" track is very often mostly silence — the
  other party is listening while you talk. Scoring silence produces a
  confident-looking number that means nothing.
- So the unit of analysis must be *speech*, not *clock time*. Something has
  to decide which samples are actually speech before the model ever sees
  them. That's the VAD's whole job.

**Q: Why Silero specifically, not just energy/RMS thresholding?**

- Two backends exist: `silero` (preferred) and `energy` (dependency-free
  fallback). Energy-based VAD is weak in noisy rooms — a noisy caller's
  background can look like speech by RMS alone.
- Silero VAD is a small (~2.2 MB) ONNX model, run on the same onnxruntime
  the detector already needs, so it adds no new runtime dependency, only a
  new graph. It's robust to background noise because it's a real learned
  model, not a threshold.
- Design principle: **never fail silently**. If the Silero model file is
  missing or fails to load, the code falls back to `energy` and logs a loud
  warning — a silent downgrade would quietly change what every verdict in
  the session means without anyone noticing.

**Q: How does Silero actually work under the hood in this integration?**

- It's recurrent — carries hidden state frame-to-frame — so frames must be
  fed strictly in order, one 32 ms frame (512 samples @ 16kHz) at a time.
- Input names/state tensors are discovered by introspecting the ONNX graph
  rather than hardcoded, because Silero v4 exports use separate `h`/`c`
  tensors while v5 uses one packed `state` tensor. This makes the code
  version-agnostic.
- **Gotcha that mattered in practice:** v5 does *not* accept a bare 512-sample
  frame — it expects the previous 64 samples prepended as context (576
  total). The graph's declared input shape is `[None, None]`, so feeding a
  bare 512 doesn't error, it just silently returns near-zero probabilities
  for everything, *including obvious speech*. This was verified empirically:
  real speech scored 261/272 frames correctly with context prepended vs.
  0/272 without it. This is exactly the kind of bug that would have made the
  whole pipeline look "broken" (no verdicts ever appear) with no error
  anywhere — worth mentioning if asked about debugging war stories.

**Q: What's the hysteresis (SpeechGate) for — why not just threshold each frame?**

- Raw per-frame probabilities are noisy. Without smoothing:
  - A single loud cough or a line click would open a "speech" segment.
  - A short pause mid-sentence would split one utterance into two, which
    then breaks the "one utterance = one window" invariant the windowing
    stage depends on.
- It's a classic Schmitt trigger: opening threshold (`VAD_THRESHOLD`, default
  0.5) is higher than the closing threshold (`threshold - 0.15`). Speech must
  sustain `VAD_MIN_SPEECH_MS` (250ms default) before a segment opens; silence
  must sustain `VAD_MIN_SILENCE_MS` (400ms default) before it closes. A small
  pad (`VAD_SPEECH_PAD_MS`, 120ms) is kept on both sides so onsets/offsets
  aren't clipped.
- Frames are buffered until their fate is decidable (a frame might retroactively
  become the head-pad of a segment that hasn't opened yet), so there's a small
  bounded-size buffer (`min_speech + pad` frames) rather than deciding frame-by-frame.

---

## 3. Why windows are cut per-utterance, not from a pooled buffer

**Q: Why does the model score "utterances" instead of just every N seconds of speech?**

- An earlier version pooled *all* kept speech into one running buffer and cut
  fixed windows out of that buffer. On real calls this meant a single 4s
  window could join sentences spoken **up to 50 seconds apart** — completely
  decontextualized, and empirically these spliced windows scored measurably
  worse than windows drawn from one continuous stretch of speech.
- Current design: the VAD's segment boundaries (with hysteresis) define
  **utterances** — one continuous stretch of the far party talking, where
  short pauses under `VAD_MIN_SILENCE_MS` stay inside the same utterance. A
  window never spans two utterances.
- Three cases, by utterance length vs. the model's fixed input (64,600
  samples = 4.0375s):
  1. **Utterance ≥ one window**: slide full windows through it at
     `WINDOW_HOP_SAMPLES` (default = window length, i.e. no overlap) *while
     it's still being spoken* — so a long sentence gets scored mid-sentence,
     not only after it ends. When the utterance ends, an end-aligned final
     window covers the remainder if that remainder alone is long enough
     (≥ floor).
  2. **`UTTERANCE_MIN_SECONDS` (default 3s) ≤ utterance < one window**: a
     single window, tile-padded (repeated) up to 64,600 samples — exactly
     what the model card specifies for short clips — flagged `padded: true`.
  3. **Utterance < floor**: recorded to `speech.wav` but never scored.

**Q: What's the cost/benefit of this design?**

- Benefit: per-utterance windows are real, continuous stretches of the call
  — no cross-sentence splicing — and cut inference load roughly threefold
  vs. the old pooled approach, which matters because CPU inference averaged
  2.2s/window on a real call (slower than pooled windows would arrive).
- Cost: coverage. In quick back-and-forth conversation, a lot of speech comes
  in bursts under the 3s floor. Measured on real test calls: a 3s floor
  scores 68–86% of speech, a 2s floor scores 80–92%. Every session's
  `summary.json` reports its own `scored_speech_ratio` so this isn't hidden.
- `UTTERANCE_MIN_SECONDS` is the knob: lower it for more coverage at the cost
  of more heavily-padded (less reliable) windows.

---

## 4. XLSR-Mamba model — the core "why this model" story

**Q: What is XLSR-Mamba, architecturally?**

`waveform → XLS-R wav2vec 2.0 (frozen backbone) → Linear(1024→144) →
BatchNorm2d → SELU → dual-column bidirectional Mamba (6 layers each
direction, attention pooling) → 2 logits [spoof, bona fide]`

- Base paper: Xiao & Das, arXiv:2411.10027.
- The backbone is a standard wav2vec 2.0 architecture but loaded via a
  hand-written port (`app/wav2vec2_port.py`) directly into `transformers`
  tensors, so the pipeline needs **no fairseq dependency** (fairseq is
  effectively unmaintained and painful to install alongside modern PyTorch —
  worth mentioning if asked "why not just use the original repo's loader").
- The Mamba head is a **pure-PyTorch reimplementation** (no `mamba_ssm` CUDA
  kernels), vendored from the fine-tuning branch, which means it runs on
  **CPU** — important because this whole pipeline runs on a laptop during a
  live call, no GPU assumed.
- Bidirectional: separate forward and backward Mamba stacks, each attention-
  pooled, concatenated and passed through a final linear layer before the
  2-way classifier. This lets the head use context from both ends of the
  4.18s clip.

**Q: What does "Indic fine-tuned head" mean exactly — what was actually retrained?**

- Base checkpoint: `AustinXiao/XLSR-Mamba-LA` (MIT-licensed, ASVspoof-trained,
  565 tensors total: frozen XLS-R backbone + `LL`/`first_bn` front-end +
  Mamba head).
- The fine-tune (private branch `XLSR_MAMBA_FINETUNED`, from the team's own
  repo) retrains **only the 129 `conformer.*` head tensors** — the backbone
  and front-end are byte-identical between base and fine-tuned versions.
- Training data: real speech from **SPRINGLab/IndicVoices-R** (Hindi, Bengali,
  Tamil) and synthetic/deepfake speech from **vdivyasharma/IndicSynth**, with
  **half of the training data passed through WhatsApp-style Opus compression**
  — deliberately matching the deployment condition (WhatsApp calls are always
  Opus-compressed and lossy).
- The loader in `xlsr_mamba.py` reconstructs the fine-tuned model exactly the
  way the branch's own `load_model.py` does: load the base checkpoint, then
  overwrite just the `conformer.*` tensors with the head file. There's a
  strict integrity check — the head file's tensor keys/shapes must match the
  base model's head one-for-one, or loading fails loudly rather than
  producing a silently-wrong model.
- `VARIANT="base"` (no head file) gives you the original ASVspoof-trained
  model on the exact same code path — useful for A/B comparison.

**Q: What's the actual reported/measured performance, and what's the catch?**

- Reported by the fine-tuning branch: **0.31% EER, 99.69% accuracy** on
  held-out Indic audio, clean and WhatsApp-compressed alike.
- **The catch — catastrophic forgetting.** Because only the head was
  retrained (backbone frozen), the model got very good at Indic speech but
  measurably worse at everything else it used to know: **ASVspoof5 EER rose
  from 2.77% to 21.28%** after fine-tuning. On a 40-clip ASVspoof5 sample run
  through this pipeline, it was right 75% of the time — missing 5 of 20
  spoofs. Translation: **an English-language voice clone is meaningfully more
  likely to get past this detector than a Hindi/Bengali/Tamil one.** This is
  a direct, known tradeoff of the fine-tuning approach, not a bug — worth
  stating plainly if asked "does it work for all languages."
- Field-test numbers on real recorded calls (not benchmark data): real
  callers correctly identified as real in **25 of 28** windows, the tester's
  own voice correctly identified as real in **22 of 23**, and it caught one
  known deepfake played through the pipeline. For comparison: the earlier
  AntiDeepfake (MMS-300M) model got 26/28 on callers but only 10/23 on the
  tester's own voice; the original XLSR-SLS model called *every* real caller
  fake (i.e. it was unusable — 0% specificity on real speech in this
  deployment's actual acoustic conditions, likely because it was overfit to
  ASVspoof-style studio audio and WhatsApp compression looked "fake" to it).
- **Not yet tested:** deepfakes played through an actual live WhatsApp call
  (only tested on files so far, per project memory) — flag this as a known
  gap if asked about validation status.

**Q: Why is it robust to WhatsApp's audio compression specifically?**

- Because half the fine-tuning data was deliberately passed through Opus
  compression before training — the model learned what synthetic vs. real
  speech looks like *after* the exact lossy pipeline it'll see in production,
  rather than assuming clean studio audio. This is the single most important
  design decision behind why this model was chosen over the two alternatives.

**Q: Preprocessing — what actually goes into the model?**

- Raw waveform in `[-1, 1]` float range, **explicitly no normalization**
  (matches the fine-tuning branch's own `evaluate_model.py` exactly — this
  was verified, not assumed).
- Repeat-tiled (if short) or cropped (if long) to exactly **66,800 samples
  (4.175s)** — the fixed length both the base model and fine-tune were
  trained on. Short utterances get looped, not zero-padded, because the
  model card specifies tiling for short clips.
- Loading is strict: **all 565 tensors must land**, or the model refuses to
  start rather than silently running with partially-loaded weights.
- Numerical parity was explicitly verified against the original branch's own
  GPU run: base model matches to 2.6e-3 on the raw logit, fine-tuned model
  matches within 0.02 on P(real) with 0 of 30 verdicts different. This
  matters because it proves the "ported" code path (no fairseq, CPU-only
  Mamba) produces the *same* model, not a reimplementation that merely looks
  similar.

**Q: Why not just run this per audio chunk in real time continuously? What's the latency?**

- ~0.8s per window on CPU for inference alone; ~2.2s/window measured
  end-to-end on a real call (includes VAD + windowing overhead). This is why
  per-utterance windowing (not pooled/overlapping) matters — it's the
  difference between keeping up with a live call and falling behind.

---

## 5. Multi-detector architecture (comparison / fallback design)

**Q: Is XLSR-Mamba the only model in the system?**

No — the architecture supports **multiple loaded detectors simultaneously**:

- `DETECTORS` env var lists them in priority order (default: `xlsr-mamba`
  alone). The **first one that loads successfully becomes primary** — its
  score is what drives the verdict and the risk EMA.
- Any other detectors in the list are also scored on the *same window* and
  reported under `secondary` in every verdict — this lets you compare models
  side-by-side on identical live audio without changing what the system
  actually acts on.
- Two others are wired in but off by default: **AntiDeepfake (MMS-300M)**
  and the original **XLSR-SLS**. Both were tried as primary and replaced —
  see the comparison numbers above.
- **Fail-soft, not fail-hard**: if a listed detector can't load (missing
  weights, missing torch, etc.), it's skipped and the next one in the list is
  tried. If *no* detector loads at all, a placeholder heuristic (RMS +
  spectral flatness) runs instead — explicitly **not** a real classifier,
  exists only so the pipeline still demonstrates end-to-end and doesn't hard-
  crash a demo. `/health` always reports which detector is actually live so
  a degraded state is never silently mistaken for a working one.

---

## 6. Risk scoring / decision logic

**Q: Why three bands (real/uncertain/synthetic) instead of a binary yes/no?**

- Explicit design constraint: **a false accusation is the expensive error.**
  Telling a genuine customer/caller they sound synthetic destroys exactly the
  trust the system exists to protect. So a window that isn't clearly real
  and isn't clearly synthetic returns `uncertain`, which recommends
  *verification* (call back on a known number, ask for a second factor)
  rather than asserting fraud outright.
- Thresholds: `P(real) ≥ THRESHOLD_REAL` (0.75 default) → `likely_real`;
  `P(real) ≤ THRESHOLD_SYNTHETIC` (0.30 default) → `likely_synthetic`;
  otherwise `uncertain`. **These thresholds are explicitly uncalibrated
  placeholders** — the honest answer if asked "how did you pick 0.75/0.30"
  is: not from an ROC curve on this exact deployment yet, they were chosen
  to produce sensible-looking demo behavior, and the intended calibration
  path is to derive them from EER measured via `deepfake/eval_balanced.py`.

**Q: How does the "session risk" meter work?**

- It's an **exponential moving average (EMA)** of `P(spoof)` across windows,
  not a per-window flag: `risk = α·p_spoof + (1-α)·risk_prev`, with
  `RISK_EMA_ALPHA` default 0.4. The first window seeds the EMA directly
  (rather than starting at 0 and easing up), so an obviously-fake opening
  window is reported as risky immediately, not smoothed away.
- The `high` risk band requires **either** the EMA to cross a high cutoff
  **or** `RISK_SUSTAIN_WINDOWS` (default 3) consecutive `likely_synthetic`
  windows in a row. This is deliberate: a single bad window (codec glitch,
  noise burst) shouldn't spike the session to "high risk" — the suspicion
  has to *persist*.
- Band cutoffs on session risk are derived from the *same* per-window
  thresholds (`1 - THRESHOLD_SYNTHETIC` and `1 - THRESHOLD_REAL`), so the
  per-window label and the session-level band can never disagree in
  direction — that consistency was a deliberate invariant, not a coincidence.

---

## 7. Call-monitor plumbing (lighter detail — background only)

**Q: How does audio actually get from WhatsApp into the model?**

- **Far track (the other party)**: WASAPI loopback — a **digital tap** inside
  Windows' audio engine, reading the exact bits WhatsApp decoded, before they
  hit a speaker. Not a microphone recording of a speaker — so no room noise,
  no re-recording loss, works even with headphones on or volume muted.
- **Near track (you)**: unavoidably a real microphone capture — there's no
  equivalent digital tap for your own outgoing audio without hooking into
  WhatsApp internals, so it does pick up your room.
- Both are resampled (anti-aliased) to 16kHz mono and chunked (4s default)
  before being sent over a WebSocket (`/ws/audio`) to the FastAPI backend.
- **Why desktop, not mobile**: Android explicitly blocks capturing another
  app's call audio (`AudioPlaybackCapture` excludes `USAGE_VOICE_COMMUNICATION`;
  raw voice-call capture needs a privileged permission apps can't get).
  Desktop OSes don't restrict loopback capture this way. This was a
  deliberate, informed platform choice, not an oversight — and it's argued
  as still high-value because executive/family-impersonation fraud calls
  increasingly happen over desktop conferencing apps (WhatsApp Desktop,
  Zoom, Teams) anyway.

**Q: What's `/ws/monitor` for, separate from `/ws/audio`?**

- `/ws/audio` is a **1:1 channel** — it only acks the specific client that's
  streaming the call (the desktop capture app), so a separate dashboard/UI
  has no way to see verdicts through it.
- `/ws/monitor` is a **fan-out hub** for any number of read-only watchers
  (e.g. the frontend dashboard): it broadcasts `session_start`, `verdict`,
  and `session_summary` events to everyone connected. A watcher joining
  mid-call gets replayed the active session's verdicts-so-far in a `hello`
  message (capped at the last 500), so a page refresh doesn't reset the risk
  meter to zero. Slow/dead watchers are dropped rather than blocking the
  broadcast to everyone else (2s send timeout per watcher).

**Q: Everything is recorded — isn't that a privacy problem?**

- Yes, explicitly flagged as a known limitation, not hidden: raw call audio
  for both parties is written to disk indefinitely by default (`RECORD_LOCALLY`
  etc. all default `true`), which is the opposite of what a real deployment
  should do — voice is biometric data under India's **DPDP Act 2023**. The
  stated design target for a real deployment is feature-only logging with
  minimal raw retention, and there are env flags to turn every recording
  layer off independently. Good honest answer if pressed: "this is a
  demo/hackathon default for traceability/debugging, and we know it's wrong
  for production."

---

## 8. Document pipeline (docsign / docPipeline) — the other arm

**Q: How does this relate to the voice deepfake detection?**

- It doesn't share code or models — it's a **separate trust problem**
  (document authenticity/integrity) bundled into the same fraud-prevention
  product story, presented in the same frontend. If asked "why is a document
  signer in a deepfake-detection project," the honest framing is: both are
  about **verifying a claimed identity/origin is real** — one for a live
  voice, one for a static document — and a fraud-prevention suite plausibly
  needs both.
- It is **cryptographic, not ML**. No anomaly detection, no OCR, no
  probabilistic scoring — deliberately, because "the cryptography answers
  the question; ML only adds failure modes" (an explicit design rule in its
  own README).

**Q: What does it actually verify?**

Exactly two questions, nothing else:
1. **Authenticity** — was this sent by the employee who claims to have sent it?
2. **Integrity** — has it changed since they signed it?

It does **not** provide confidentiality (document stays fully readable — this
is a signing tool, not encryption), watermarking, canonicalization, or
online revocation.

**Q: What's the crypto design, and why those choices?**

- **SHA-256** hash of the raw file bytes, **Ed25519** signature over the
  32-byte digest (not the file itself) — this is why verification is O(1) in
  document size, not O(file size).
- Why Ed25519 over ECDSA P-256 (roughly equivalent security level, ~128-bit):
  Ed25519 is **deterministic** — no per-signature random nonce — so there's
  no random-nonce-reuse failure mode, which has repeatedly leaked ECDSA
  private keys in real-world incidents. Tradeoff: weaker tooling support
  (X.509/PAdES/PDF readers are built around RSA/ECDSA) — acceptable here
  because this system's own verifier is the only thing that ever checks the
  signature; nothing external needs to validate it.
- **X.509 certificates**, chained to a single **self-signed root CA**
  (5-year validity). Employee certs are **90-day validity** — this is the
  offboarding mechanism: no revocation list needed, a departed employee's
  cert simply stops verifying within 90 days. Tradeoff explicitly accepted:
  documents signed by a since-expired cert become unverifiable later
  (deemed fine since document circulation isn't a concern here).

**Q: Walk me through the verification steps.**

Order is **security-critical** — each step short-circuits on failure:
1. Parse `.sig` bundle (JSON, known version) → else `UNVERIFIABLE`
2. Parse embedded X.509 certificate → else `INVALID`
3. Certificate chains to the trusted root → else `INVALID`
4. Certificate within its validity window → else `EXPIRED`
5. **Ed25519 signature verifies over the digest claimed in the bundle** →
   else `TAMPERED`
6. Recomputed SHA-256 of the actual file matches that now-trusted digest →
   else `TAMPERED`
7. Otherwise → `VALID`

**Q: Why must step 5 (signature check) run before step 6 (digest comparison)?
This is the one they're most likely to probe on.**

- If you compared digests *first*: an attacker who controls the `.sig` file
  could simply write in whatever digest matches their tampered document,
  and that comparison would pass — **before** the signature check ever
  catches that the digest itself was forged. The signature is what makes the
  bundle's `digest` field trustworthy in the first place; comparing it
  before verifying it is comparing against a number the attacker chose.
  This exact ordering is enforced by a named adversarial test case
  (`test_attacks.py` case 10) specifically so it can't regress silently.
- Similarly, chain check (step 3) must precede signature check (step 5):
  verifying a signature against an untrusted certificate's public key proves
  nothing about who actually signed it.

**Q: There's also a "registry" (database) mode — how does that change the trust model?**

- It doesn't. "**The database is a signature registry, not a trust
  authority.**" A row in it proves nothing by itself — every verification
  still runs the *entire* cryptographic pipeline (chain, expiry, Ed25519)
  against whatever the registry hands back. It only saves the recipient from
  needing the `.sig` file by hand — offline `.sig` verification keeps
  working unchanged whether or not a registry is configured.
- If the registry is unreachable, it fails **loudly** as
  `VERIFICATION_UNAVAILABLE` (a 5th, distinct status code) rather than
  silently falling back to "no verification happened" being mistaken for
  a real verdict — the operator is told to explicitly re-run with `--offline`
  if they have a `.sig` file.
- A hash miss in the registry (nothing found) is `UNVERIFIABLE`, never
  `TAMPERED` — you cannot distinguish "never signed" from "signed then
  stripped," and conflating those would be a false accusation.

**Q: What are the honestly-acknowledged limitations?**

- **Insider fraud isn't prevented** — a valid signature by an authorized
  employee on a *false* document still verifies correctly. This provides
  accountability, not prevention.
- **Key theft = identity theft** for this system's purposes.
- **Partial adoption is the real weak point** — if unsigned documents are
  routinely accepted anyway, an attacker just doesn't sign, and the system
  reports `UNVERIFIABLE` rather than blocking anything; enforcing "always
  require a signature" is an organizational policy decision, not something
  the crypto can force.
- Enrollment (issuing a cert to an employee) is a bare admin command in this
  prototype with no identity check — a real deployment needs an HR/IAM hook
  gating it.

---

## 9. Research backing (from the deck's references slide — cite these if asked "why this architecture")

- **XLS-R + Mamba paper**: Xiao & Das, arXiv:2411.10027 — combines a
  self-supervised multilingual wav2vec 2.0 backbone (XLSR) with Mamba
  (state-space sequence modeling) to capture both fine-grained acoustic
  representations and long-range temporal anomalies. This is the base
  architecture this project's detector implements (see section 4).
- **ASVspoof5 benchmark table (from the deck)** — XLS-R+Mamba against other
  published baselines on 2021LA / 2021DF:

  | System | 2021LA EER% | 2021LA min t-DCF | 2021DF EER% |
  |---|---|---|---|
  | RawNet2 (2021) | 5.31 | 0.310 | 22.38 |
  | SE-Rawformer (2023) | 4.98 | 0.318 | — |
  | RawBMamba (2024) | 3.21 | 0.271 | 15.85 |
  | XLSR+AASIST* (2022) | 1.00 | 0.212 | 3.69 |
  | XLSR+Conformer (2023) | 0.97 | 0.212 | 2.58 |
  | XLSR+AASIST2 (2024) | 1.61 | — | 2.77 |
  | WavLM-Large+MFA (2024) | 5.08 | — | 2.56 |
  | XLSR+Conformer+TCM (2024) | 1.18 | 0.217 | 2.25 |
  | **XLSR-Mamba (proposed / base)** | **0.93** | **0.208** | **1.88** |

  This is the **base** (ASVspoof-trained) XLSR-Mamba model beating every
  other published baseline on both metrics — the reason it was chosen as the
  starting point before Indic fine-tuning. Useful line if asked "why not just
  use AASIST or a Conformer": the base architecture already outperformed them
  on the standard benchmark before any Indic-specific work was done.
- **Datasets**: real speech from **AI4Bharat IndicVoices**
  (huggingface.co/datasets/ai4bharat/IndicVoices) and synthetic/deepfake
  speech from **IndicSynth** (huggingface.co/datasets/vdivyasharma/IndicSynth,
  CC BY-NC 4.0 — noted in code as a licensing consideration for commercial
  use). Note: the actually-loaded fine-tune used **IndicVoices-R** (the
  read-speech subset of IndicVoices), not the full corpus — worth being
  precise about if asked exactly what data trained the head.
- **Survey/context papers** cited in the deck (background reading, not
  directly implemented): arXiv:2308.14970 (shift from LFCC/MFCC spectral
  features toward self-supervised representations — motivates using XLS-R
  over hand-crafted features), arXiv:2608.15411 (survey of spoofing
  attacks — TTS/VC — and countermeasures), arXiv:2403.11778 (low-latency
  spoofing detection for live telephony/streaming — the closest prior art to
  this project's actual real-time windowing problem, worth mentioning if
  asked about related work on the streaming/latency angle specifically).

---

## 10. Anticipated "gotcha" questions and honest answers

| Question | Honest answer |
|---|---|
| "Have you tested this against real deepfake audio played through an actual call?" | Not yet — tested against deepfake files and real callers separately, but not deepfakes played live through WhatsApp end-to-end. Documented as a known gap. |
| "Does it work for English speech / non-Indic languages?" | Noticeably worse — ASVspoof5 (mostly English) EER rose from 2.77% to 21.28% after the Indic fine-tune, because only the classification head was retrained and the backbone forgot some of what it knew (catastrophic forgetting). |
| "What happens if the model is wrong?" | Three-band design means most wrong calls land in `uncertain`, which recommends verification rather than asserting fraud — deliberately biased against false accusations. Verdicts are advisory only; nothing auto-blocks or terminates a call. |
| "Are the risk thresholds scientifically derived?" | No — explicitly stated as uncalibrated placeholders chosen for sensible demo behavior, pending calibration from EER on `deepfake/eval_balanced.py`. |
| "Isn't recording both parties without clear consent a legal problem?" | Yes, flagged as a known limitation — voice is biometric data under DPDP Act 2023; recording is a demo default for traceability, not the production design, and can be fully disabled via env flags. |
| "Why is document signing in this project at all?" | Different trust problem (document vs. live voice), same product story (verifying claimed identity), no shared runtime — bundled for a unified fraud-prevention pitch, not because they share technology. |
| "Could the document signer be attacked by feeding it a forged digest?" | No — signature verification (Ed25519) always runs before the digest is trusted for comparison, specifically to close that exact attack, and there's a named regression test for it. |
| "What stops someone just not signing a document to dodge detection?" | Nothing cryptographic — reported as `UNVERIFIABLE`, and enforcing "signature required" is a deployment policy decision, explicitly out of the crypto's scope. |
| "Your deck says speaker identity verification / voice fingerprinting — show me that." | Not built yet — be direct about this rather than trying to demo around it (see section 0). The current system answers "is this voice synthetic," not "is this the specific person it claims to be." Those are complementary but separate problems; the second needs an enrolled-voice embedding database, which doesn't exist in this build. |
| "Where's the Twilio integration / how would this work on a real phone call, not WhatsApp Desktop?" | Not built — current ingestion is WASAPI loopback from WhatsApp Desktop specifically, chosen because desktop OSes allow loopback capture and Android blocks it (section 7). Telephony ingestion (Twilio/SIP) would replace only the capture layer; VAD/windowing/model/risk logic downstream doesn't care where the audio came from. |
| "Is this actually real-time / edge / on-device as the deck claims?" | CPU inference, yes (no GPU needed, ~0.8s/window) — but it's a backend server process, not inference running inside a mobile app, and the deck's "zero data retention" claim is contradicted by the build's default of recording everything to disk. Be ready to state the gap plainly (section 0) rather than let a demo of the recordings folder undercut the privacy claim unprompted. |
| "Why should I believe XLS-R+Mamba over [some other architecture]?" | Point to the ASVspoof5 benchmark table (section 9): the base architecture already beats AASIST/Conformer/RawBMamba variants on published EER before any Indic fine-tuning was even applied — the architecture choice is evidence-based, not arbitrary. |
