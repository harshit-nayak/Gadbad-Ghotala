# Context

## What this project is

An **AI-powered system that detects cloned / synthetic voices during a live phone call** and warns the person on the other end *before* they act on what they're being told.

The threat: generative speech models can clone a voice convincingly from a few seconds of audio. Attackers use this to impersonate CXOs, government officials, bank staff, or family members over VoIP, mobile networks, and collaboration tools — usually paired with leaked personal details to make the story credible. The payoff is a fraudulent fund transfer, an approval, or a disclosure of confidential information.

Existing defenses (caller ID, call-back, "I know their voice") fail because the voice *is* the credential and the attacker now controls it. Nothing in the current telephony stack tells you, mid-call, that the audio you're hearing was generated.

## The one-sentence goal

Analyze a live audio stream in near real time, output a continuously updating **impersonation risk score**, and trigger an actionable alert before a sensitive action is taken.

## Who it's for

| User | What they need from it |
|---|---|
| Bank / NBFC frontline staff, relationship managers | A live warning on the call before authorizing a transaction |
| Enterprise finance & exec assistants | Detection of "CEO fraud" calls requesting urgent payments |
| Contact centers | Automated screening at scale, queued for review |
| Telecom operators | A network-level layer they can offer as a service |
| Individuals | An in-app warning on a suspicious call |

## Scope

### In scope
- Real-time / near-real-time inference on streaming audio (target: verdict within the first few seconds, updated continuously).
- **Multi-layer analysis** — three independent signals, fused:
  1. **Acoustic & spectral** — synthesis artifacts, phase inconsistencies, vocoder fingerprints, unnatural spectral distribution.
  2. **Prosody & behavioral** — rhythm, pitch contours, pause structure, breath, micro-variations that neural TTS still under-models.
  3. **Cross-session consistency** — compare against enrolled/historical genuine samples of the claimed speaker, where available.
- **Risk scoring engine** — configurable thresholds per scenario (high-value transaction vs. routine call), enriched with metadata: call origin, whether the number is a known contact, transaction context, prior fraud indicators.
- **Alerting layer** — UI prompt, SMS/email, in-app notification; pre-transaction warning recommending a second factor (call-back, MFA, supervisor escalation); configurable automated responses per organization.
- **Privacy module** — minimal retention of raw audio, on-device/edge inference where possible, feature-only or anonymized logging.
- **Integration surface** — REST/gRPC APIs + SDKs for core banking, contact center platforms, enterprise comms, telecom infrastructure.
- **Multilingual** — Indian languages and regional accents; language-agnostic feature extraction plus language-specific acoustic models where needed.

### Explicitly out of scope
- Speaker *identification* as a standalone product (identity verification is a supporting signal, not the deliverable).
- Blocking or terminating calls automatically — the system advises; the organization's policy decides.
- Detecting deepfake *video*.
- Content-level analysis of what the caller says (that's a different fraud-detection problem).

## Hard constraints that shape every design decision

1. **Latency.** A risk score that arrives after the call ends is worthless. Streaming inference on short windows, not batch analysis of a full recording. This rules out heavy offline architectures.
2. **Audio quality.** Real input is 8 kHz narrowband, codec-compressed (G.711/Opus/AMR), packet-lossy, noisy. A model trained on clean 16 kHz studio datasets will collapse in production. Codec-aware augmentation is not optional.
3. **False positives are expensive.** Accusing a genuine customer of being a deepfake destroys trust. The operating point should favor precision on the "synthetic" verdict, with an ambiguous middle band that recommends verification rather than asserting fraud.
4. **Generalization to unseen synthesizers.** The model must flag voices from TTS systems it was never trained on — attackers use whatever is new. Evaluate on held-out generators, not just held-out samples.
5. **Privacy / compliance.** Voice is biometric data under DPDP Act 2023 and comparable regimes. Default to not storing raw audio; store derived features. Consent and retention policy have to be part of the design, not bolted on.
6. **Accent and language coverage.** A system that works on American English and fails on Indian-accented Hindi-English code-switching does not solve the stated problem.

## Success criteria

- **Detection quality:** high AUC / low EER on a held-out set that includes *unseen* synthesis methods; report performance separately per language and per codec condition.
- **Latency:** first score in ≤ 2–3 s of speech; continuous updates thereafter.
- **False positive rate:** low enough that frontline staff don't learn to ignore the alert.
- **Robustness:** measured degradation under noise, compression, and packet loss — reported, not hidden.
- **Integrability:** a working SDK/API demo against at least one realistic call flow.

## Anticipated hard problems

- **Data.** Need paired genuine + cloned speech in Indian languages. Public deepfake-audio corpora (ASVspoof family, In-the-Wild, etc.) skew English and clean. Generating your own spoofed set with open TTS/voice-conversion models is likely necessary — and creates its own bias (you'll be good at detecting the systems you generated with).
- **Adversarial pressure.** Anti-forensic post-processing (adding noise, re-recording, re-encoding) can erase artifacts the model relies on. Prosody-level signals degrade more gracefully than spectral artifact detection.
- **The arms race.** Each generation of TTS closes artifacts the previous one left. Design for retrainability and model versioning from day one.
- **Enrollment gap.** Cross-session consistency only works if you have genuine reference audio for the claimed speaker. For most inbound calls you don't. Treat it as a bonus signal, not a dependency.
- **Explainability.** "Risk 0.87" is not actionable. The alert needs a human-readable reason ("unnatural pause structure, vocoder artifacts detected") for staff to trust and act on it.

## Deliverable shape (working assumption)

1. A **detection model / ensemble** with a documented evaluation.
2. A **streaming inference service** that ingests audio chunks and emits scores.
3. A **demo client** — a call UI showing a live risk meter and pre-transaction warning.
4. An **integration layer** — API spec + minimal SDK.
5. **Documentation** covering privacy posture, threat model, and known limitations.

## Open decisions

These aren't settled yet and should be resolved before building:

- Target deployment: cloud service, on-prem enterprise, edge/on-device, or telecom-network layer? (Affects everything about latency and privacy design.)
- Which pipeline stage is the priority for a first working version — detection accuracy, or end-to-end demo?
- Model approach: end-to-end raw-waveform model, spectrogram-based CNN/transformer, self-supervised speech representation + classifier, or an ensemble?
- Which languages/accents to cover in v1 vs. later.
- Whether speaker enrollment is available in the target deployment.
- Team size, timeline, and whether this is a prototype or a production path.
