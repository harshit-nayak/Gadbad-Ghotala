# Call Deepfake Screening — Desktop Capture (WhatsApp Desktop)

Captures both sides of a **WhatsApp Desktop** call as two separate real-time
PCM streams — **far** (the other party) and **near** (you) — isolates the
stretches where the far party is actually speaking, and scores them with the
**XLSR-Mamba** anti-spoofing model, fine-tuned on Hindi, Bengali and Tamil
deepfakes including WhatsApp-compressed audio, returning a continuously updating
impersonation risk score while the call is still happening.

Every stage is recorded: the raw call, the speech the VAD kept, the exact
samples handed to the model, and what it returned — so any verdict can be
traced back to the audio that produced it.

This only works for calls taken in the **WhatsApp Desktop app** (or Zoom /
Teams / Meet / any app that plays audio through Windows) — see
["Why desktop, not mobile"](#10-why-desktop-not-mobile).

**Every session is saved locally by default**, including raw audio of both
parties — see [section 6](#6-recordings-and-logs-what-gets-written) for the
full layout and [section 13](#13-known-limitations) for why you should turn
that off before using this for real.

---

## 1. What you need

- Windows 10/11
- Python 3.10+ on PATH (`python --version`)
- WhatsApp Desktop installed (the native app, not the browser — see
  ["Why desktop, not mobile"](#10-why-desktop-not-mobile) for why browser
  WhatsApp doesn't apply here)
- A working speaker/headphone output and a microphone

No admin rights, no root, no WhatsApp modification — everything below uses
public Windows audio APIs.

---

## 2. Install

From the folder containing `backend\`, `client\` and `scripts\`:

```powershell
cd "C:\Users\nayak\Desktop\sih deepfake\call-monitor"
.\scripts\run_backend.ps1
```
```powershell
.\scripts\run_client.ps1
```

Run each once and let it finish — both scripts create a `.venv` and install
dependencies automatically the first time, then start the program.

(To install without running yet: `python -m venv .venv` then
`.\.venv\Scripts\pip install -r requirements.txt` inside `backend/` and
`client/` respectively.)

### Model files

All under `backend\models\`:

| File | Size | Role | How to get it |
|---|---|---|---|
| `xlsr-mamba\model_base.safetensors` | 1.28 GB | XLSR-Mamba base checkpoint (public, MIT) | fetched automatically by `run_backend.ps1` (or `scripts\fetch_xlsr_mamba.py`) |
| `xlsr-mamba\conformer_head_only.safetensors` | 7.2 MB | the Indic fine-tuned head, merged onto that base — together, **the detector** | from the private repo `harshit-nayak/Gadbad-Ghotala`, branch `XLSR_MAMBA_FINETUNED`; see `SOURCE.txt` in that folder |
| `silero_vad.onnx` | 2.2 MB | isolating the other party's speech | fetched automatically (or `scripts\fetch_silero.py`) |
| `mms-300m-anti-deepfake\` and `../deepfake/xlsr-sls.onnx` | 1.27 / 1.36 GB | optional comparison detectors, off by default | `scripts\fetch_antideepfake.py`; already in `../deepfake/` |

The backend still starts with any of these missing — but it degrades, loudly,
and tells you so. Without the head it cannot run the fine-tuned model; with no
detector at all it falls back to a placeholder heuristic whose numbers mean
nothing; without the VAD it falls back to energy-based speech detection, which
is weaker when the other party is in a noisy room.
`http://localhost:8000/health` always reports what is actually live:

```json
{"status":"ok","detector":"xlsr-mamba","model_state":"ready","vad_backend":"silero",
 "detectors":[{"name":"xlsr-mamba","state":"ready"}]}
```

The detector needs PyTorch (`requirements-antideepfake.txt`), which
`run_backend.ps1` installs. The base model and code are MIT; the Indic head was
trained partly on IndicSynth, which is **CC BY-NC 4.0** — fine for research and
a hackathon, but get a legal read before any commercial use.

---

## 3. Run it

Two commands, in two terminals. That's the whole thing.

**Both terminals must start in this folder** — the one containing `backend\`,
`client\` and `scripts\`, *not* the `sih deepfake` root above it:

```powershell
cd "C:\Users\nayak\Desktop\sih deepfake\call-monitor"
```

(If you see `The module 'scripts' could not be loaded`, you are one directory
too high. That is PowerShell's unhelpful way of saying the path doesn't exist.)

**Terminal 1 — start the backend** (leave this running):
```powershell
.\scripts\run_backend.ps1
```
It fetches the VAD and XLSR-Mamba models if missing (the latter is 1.28 GB,
one time), then loads the detector — a few seconds warm, up to ~40 s cold.
Wait for `Application startup complete`. Check the fine-tuned model came up:

```powershell
curl http://localhost:8000/health
# {"status":"ok","detector":"xlsr-mamba",...,"detectors":[{"name":"xlsr-mamba","state":"ready"}]}
```

**Terminal 2 — start the capture client** (same folder):
```powershell
cd "C:\Users\nayak\Desktop\sih deepfake\call-monitor"
.\scripts\run_client.ps1
```
A window titled **"Call Deepfake Screening — Desktop Capture"** opens.

> To test without placing a call, replace terminal 2 with
> `backend\.venv\Scripts\python backend\scripts\simulate_call.py <audio file>`
> — see [section 14](#14-verifying-the-pipeline).

### First-time walkthrough

1. **Server** — leave the WebSocket URL as `ws://localhost:8000/ws/audio`
   unless the backend is running elsewhere. Auth token is optional (see
   [Configuration](#5-configuration-reference)).
2. **Audio sources**:
   - **Far (call audio via loopback)** — pick the device that plays
     WhatsApp's call audio. The one labeled *"(current default output)"* is
     auto-selected and is correct for most setups.
   - **Near (your microphone)** — your mic; the one labeled
     *"(default microphone)"* is auto-selected.
   - Click **Refresh devices** if you plug in headphones/a different mic
     after opening the app.
3. **Options**:
   - **Chunk length (seconds)** — how much audio accumulates before each
     piece is sent and analyzed. Default 4s. Shorter = faster alerts, more
     network chatter; longer = slower alerts, more context per chunk.
   - **Auto-detect WhatsApp calls...** — see [section 4](#4-auto-detect-recommended).
4. Click **Start**, then start or answer the WhatsApp Desktop call.
5. Watch the **verdicts / events** log at the bottom. Click **Stop** when
   you're done (or just close the window — it stops cleanly on exit).

### What you should see

- Status changes: `Disconnected` → `Connecting...` → `Connected` →
  `Connected & streaming`.
- The **Stats** row counts climbing roughly every 4 seconds for both `far`
  and `near` as chunks are sent and acknowledged.
- The **impersonation risk** meter stays at "awaiting speech" until the other
  party has actually spoken for about 4 seconds — that is by design, not a
  hang (see [section 7](#7-how-detection-actually-works)).
- Then lines like:
  ```
  [14:02:07] far window  3  likely_real  P(real)=0.995 [xlsr-mamba]  speech=17.3s  840ms
      xlsr-mamba P(real)=0.995 on 4.04s of speech, tile-padded to 4.17s
  ```
  colour-coded green (`likely_real`), amber (`uncertain`), red
  (`likely_synthetic`), with the risk meter and its recommendation updating
  each time.
- Recordings and logs building up on disk in real time — see
  [section 6](#6-recordings-and-logs-what-gets-written).

---

## 4. Auto-detect (recommended)

Instead of clicking Start/Stop for every call, check **"Auto-detect
WhatsApp calls and record automatically"** once. From then on:

- Recording **starts by itself** when WhatsApp begins an actual call
  (detected via Windows' own per-process audio session state — the same
  data the system Volume Mixer uses; no hooking, no admin rights).
- Recording **stops by itself** a few seconds after the call ends.
- A session you start manually with the **Start** button is never
  auto-stopped by the detector — manual control always wins.
- Detection requires both a microphone session *and* a speaker session
  active from WhatsApp at once, which is specifically what filters out the
  false positive of recording a voice note (mic only, no call audio).
- Watching a different app instead? Change the **Process name** field
  (e.g. `Teams.exe`, `zoom.exe`, `Discord.exe`) before checking the box.

Leave the app running in the background with auto-detect on and it screens
— and records — every WhatsApp call without further interaction.

---

## 5. Configuration reference

**Client GUI**

| Setting | Default | Purpose |
|---|---|---|
| Server URL | `ws://localhost:8000/ws/audio` | backend to stream to |
| Auth token | none (disabled) | shared secret, if the backend requires one |
| Chunk length | 4s | how often audio is *sent*. Not how often it is scored — see [section 7](#7-how-detection-actually-works) |
| Process name | `WhatsApp.exe, WhatsApp.Root.exe` | which app's calls to auto-detect |

**Backend env vars** — everything the backend uses, with defaults. The full
effective set is served at `http://localhost:8000/config` and snapshotted into
every session's `session.json`.

| Variable | Default | Purpose |
|---|---|---|
| `DETECTORS` | `xlsr-mamba` | detectors to run, in priority order; the first that loads produces the verdict, any others are logged alongside (e.g. `xlsr-mamba,antideepfake,xlsr-sls`) |
| `XLSR_MAMBA_PATH` | `backend/models/xlsr-mamba` | base checkpoint + Indic head |
| `ANTIDEEPFAKE_PATH` | `backend/models/mms-300m-anti-deepfake` | the AntiDeepfake weights folder (optional) |
| `MODEL_PATH` | `../../deepfake/xlsr-sls.onnx` | the XLSR-SLS model |
| `MODEL_CODE_DIR` | `../../deepfake` | folder holding `xlsr_sls_infer.py` + `preprocess.py` |
| `MODEL_PROVIDER` | `cpu` | `cpu`, `openvino`, `dml`, `cuda` |
| `MODEL_ENABLED` | `true` | set `false` to force the placeholder heuristic |
| `THRESHOLD_REAL` | `0.75` | P(real) at or above this → `likely_real` |
| `THRESHOLD_SYNTHETIC` | `0.30` | P(real) at or below this → `likely_synthetic` |
| `RISK_EMA_ALPHA` | `0.4` | how reactive the session risk meter is |
| `RISK_SUSTAIN_WINDOWS` | `3` | consecutive suspicious windows before risk is called `high` |
| `UTTERANCE_MIN_SECONDS` | `3.0` | shortest utterance that gets scored; shorter ones are recorded, not scored |
| `WINDOW_HOP_SAMPLES` | `64600` | within a long utterance, how far each window advances (default: no overlap; `32300` = 50%) |
| `VAD_BACKEND` | `silero` | `silero`, `energy`, or `off` |
| `SILERO_VAD_PATH` | `backend/models/silero_vad.onnx` | the VAD model |
| `VAD_THRESHOLD` | `0.5` | speech probability needed to open a segment |
| `VAD_MIN_SPEECH_MS` | `250` | speech must sustain this long to count |
| `VAD_MIN_SILENCE_MS` | `400` | silence must sustain this long to end a segment |
| `VAD_SPEECH_PAD_MS` | `120` | audio kept either side of a segment |
| `DETECT_TRACKS` | `far` | which track(s) to score; add `,near` to also score yourself |
| `RECORD_LOCALLY` | `true` | continuous `far.wav` / `near.wav` |
| `RECORD_CHUNKS` | `true` | one WAV per arriving chunk |
| `RECORD_SPEECH` | `true` | `speech.wav` — VAD-kept audio only |
| `RECORD_WINDOWS` | `true` | one WAV per scored window |
| `WRITE_ARTIFACTS` | `true` | the JSONL logs |
| `RECORDINGS_DIR` | `recordings` | where all of the above is written |
| `AUTH_TOKEN` | none | require a shared secret to connect |
| `PORT` / `HOST` | `8000` / `0.0.0.0` | bind address |

> **The two thresholds are not calibrated.** They are placeholders that produce
> sensible behaviour, not values derived from evaluation. Run
> `deepfake/eval_balanced.py`, read the EER out of `deepfake/results/summary.json`,
> and set them from your own data before treating any verdict as meaningful.

Set env vars before `scripts\run_backend.ps1`, e.g.:
```powershell
$env:AUTH_TOKEN = "some-shared-secret"
scripts\run_backend.ps1
```

---

## 6. Recordings and logs: what gets written

Everything is written **locally by the backend** as the call happens. Nothing
is stored by the client; the backend (running on your own machine when you
follow this README) is where files land. The goal is that any verdict can be
traced back afterwards to the exact audio that produced it:

```
backend/recordings/<session_id>/
  session.json                    config snapshot, model fingerprint, start time
  events.jsonl                    every event in order: chunks, VAD segments,
                                  windows, verdicts, drops, errors
  verdicts.jsonl                  one line per verdict
  summary.json                    written at session end: totals and final risk
  far.wav                         the other party, whole call
  near.wav                        you, whole call
  far/chunk_0000.wav ...          one file per arriving chunk, in real time
  far/speech.wav                  ONLY what the VAD judged to be speech
  far/segments.jsonl              each speech segment: start_ms, end_ms, rms
  far/windows/window_0000.wav     the exact 64,600 samples the model scored
  far/windows/window_0000.json    provenance + what the model returned
```

`<session_id>` is the UUID shown in the client's log when a session starts.
WAVs are 16 kHz mono 16-bit PCM, playable in anything (Media Player, VLC,
Audacity) — and finalized correctly even if the app is closed or the
connection drops mid-call, not just on a clean Stop.

A window's `.json` is the interesting one. `source_ranges_ms` says which
stretch of the call its samples came from, so a verdict you disagree with can
be opened and listened to. This is window 0 of a real test call — a 3.2 s
utterance, repeat-tiled up to the detector's 4.18 s input:

```json
{
  "window": { "index": 0, "utterance_index": 0, "source_ranges_ms": [[0, 3232]],
              "real_duration_s": 3.232, "padded": true },
  "result": { "p_bonafide": 1.0, "label": "likely_real", "detector": "xlsr-mamba" },
  "risk":   { "session_risk": 0.000, "risk_band": "low" },
  "wav": "far/windows/window_0000.wav"
}
```

That caller was a real person, and the detector gets it right.

Each level can be turned off independently — `RECORD_LOCALLY`, `RECORD_CHUNKS`,
`RECORD_SPEECH`, `RECORD_WINDOWS`, `WRITE_ARTIFACTS` — and `RECORDINGS_DIR`
moves all of it:

```powershell
$env:RECORDINGS_DIR = "D:\call-recordings"
scripts\run_backend.ps1
```

If you move the backend to a remote machine, recordings live there, not on
your PC — see `backend/app/recordings.py`. Note the privacy consequence: raw
call audio for both parties is retained indefinitely by default, which is the
opposite of what a deployed version of this should do (see
[section 13](#13-known-limitations)).

---

## 7. How detection actually works

Every window of the far party's speech is scored by **XLSR-Mamba with an
Indic fine-tuned head** (`backend/app/xlsr_mamba.py`):

- **What it is:** XLSR-Mamba (Xiao & Das, arXiv:2411.10027) — a frozen XLS-R
  wav2vec 2.0 backbone feeding a dual-column bidirectional Mamba classifier.
  Its head was fine-tuned (private repo `harshit-nayak/Gadbad-Ghotala`, branch
  `XLSR_MAMBA_FINETUNED`) on Hindi, Bengali and Tamil real speech and
  deepfakes, half of it passed through WhatsApp-style Opus compression. The
  branch reports 0.31% EER on held-out Indic audio, clean and compressed alike.
- **How it is loaded:** the public base checkpoint (`AustinXiao/XLSR-Mamba-LA`)
  with its 129 head tensors replaced by the fine-tuned head — exactly how the
  branch's own loader does it. The backbone goes through
  `backend/app/wav2vec2_port.py` into `transformers`, so fairseq is not needed,
  and the Mamba head is the branch's pure-PyTorch code, so it runs on CPU
  (about 0.8 s per window). Loading is strict: every one of the 565 tensors
  must land. Scores match the branch's own GPU run — the base model to 2.6e-3
  on the logit, the fine-tune within 0.02 on P(real) with 0 of 30 verdicts
  different.
- **Input:** the utterance's real speech, repeat-tiled or cropped to 66,800
  samples (4.18 s), with no normalisation — the branch's preprocessing exactly.

Why this model: on the recorded test calls it scored the real callers as real
in 25 of 28 windows and the tester's own voice in 22 of 23, and still caught a
known deepfake. The previous detector, AntiDeepfake, managed 26 of 28 callers
but only 10 of 23 for the tester's own voice; the original XLSR-SLS called
every real voice fake.

Two more detectors are installed for comparison and off by default:
AntiDeepfake MMS-300M and XLSR-SLS. Add them to `DETECTORS`
(e.g. `xlsr-mamba,antideepfake,xlsr-sls`) and every verdict carries their
scores under `secondary`, without changing the verdict itself.

**Verdicts are not one per chunk.** Three things sit between the audio
arriving and a score coming out:

1. **VAD.** A 4 s slice of the far track is frequently mostly silence — the
   other party is listening while you talk — and this is a *speech*
   anti-spoofing model, so scoring silence produces a meaningless number.
   Silero VAD decides which samples are the other party actually speaking;
   only those are kept.
2. **Window assembly, one utterance at a time.** The model accepts exactly one
   input length: 64,600 samples (4.0375 s). Each window is cut from **one
   utterance** — a single continuous stretch of the far party speaking — and
   never spans a pause. An utterance of 4.04 s or more gets full windows slid
   through it *while it is spoken*, so a long sentence is scored mid-sentence.
   One of 3–4.04 s gets a single window, tile-padded to 64,600 samples (the
   padding the model card specifies for short clips) and flagged `[padded]`.
   Anything shorter is recorded but not scored. The floor is
   `UTTERANCE_MIN_SECONDS`.
3. **Three-band decision.** `likely_real` / `uncertain` / `likely_synthetic`.
   The middle band exists because accusing a genuine customer of being a
   deepfake is the expensive error: it recommends verification rather than
   asserting fraud. Session risk is an EMA of P(spoof) across windows, and the
   `high` band additionally requires the suspicion to persist across
   consecutive windows.

**When no detector can load**, `backend/app/detector.py` falls back to the
original placeholder heuristic (RMS + spectral flatness). It is not a
classifier and its numbers mean nothing — it exists so the pipeline still
demonstrates end to end. Every verdict names the detector that produced it,
and `/health` reports it, so a fallback is never mistaken for a real result.

**Why per-utterance:** an earlier version pooled all kept speech into one
buffer and cut windows from that, so on real calls a single window could join
sentences spoken up to 50 seconds apart — and spliced windows scored measurably
worse than unbroken ones. Per-utterance windows also cut inference about
threefold, which matters: on a real call, CPU inference averaged 2.2 s per
window. The cost is coverage. In quick back-and-forth much of the speech comes
in bursts under 3 s; measured on real calls, a 3 s floor scores 68–86% of
speech and 2 s scores 80–92%. Every session's `summary.json` reports its own
`scored_speech_ratio`.

---

## 8. Isolating WhatsApp's audio specifically

By default the "far" capture is a **system-wide** loopback of your chosen
output device — it captures *everything* playing on it, not just WhatsApp.
Fine for a demo (just close other apps with sound). For cleaner isolation,
two no-code options:

- **Windows Sound Settings → Volume mixer** (Windows 11): set WhatsApp's
  output device explicitly, separate from other apps, then pick that same
  device as "far" in this app.
- **VB-Audio Virtual Cable** (free): set WhatsApp Desktop's output device to
  `CABLE Input`, then select `CABLE Output` as the "far" device here. Use
  Windows' "Listen to this device" on `CABLE Output` if you still want to
  hear the call live while it's being captured.

---

## 9. How it actually captures audio

The **far** track is a **digital tap**, not an acoustic recording: WASAPI
loopback reads the audio stream directly inside Windows' audio engine — the
same bits WhatsApp decoded — before they reach a speaker. No microphone
picks up sound from a speaker for this track, so there's no room noise, no
re-recording loss, and it works even with headphones on or the volume down.

The **near** track (your own voice) is unavoidably a real microphone
capture — there's no equivalent digital tap for your own side without
hooking into WhatsApp's internals.

---

## 10. Why desktop, not mobile

Android blocks apps from capturing another app's call audio
(`AudioPlaybackCapture` explicitly excludes `USAGE_VOICE_COMMUNICATION`, and
`VOICE_CALL`/`VOICE_DOWNLINK` need the privileged `CAPTURE_AUDIO_OUTPUT`
permission). Desktop OSes don't apply that restriction to loopback capture,
so WhatsApp Desktop / Zoom / Teams calls are freely capturable this way —
no root, no special permissions. High-value deepfake-call fraud (fake
executives, fake family members) increasingly happens on exactly these
desktop conferencing calls. Also note: **WhatsApp Web (the browser
version)** has no calling feature at all — this only applies to the
downloadable WhatsApp Desktop app.

---

## 11. Troubleshooting

**"No WASAPI loopback devices found"** — no playback device is currently
active/enabled. Check Windows Sound settings for an enabled output device,
then click **Refresh devices**.

**Far combo box is empty / greyed out** — same as above; also try
unplugging/replugging headphones and refreshing.

**Status stuck on "Connecting..."** — the backend isn't running, the port
is blocked, or the URL is wrong. Confirm `http://localhost:8000/health`
returns `{"status":"ok"}` in a browser first.

**Chunks sent but never "acked"** — a firewall or antivirus is likely
blocking the loopback WebSocket connection to `localhost:8000`; check
Windows Firewall prompts.

**Verdicts never appear, only acks** — most often this is correct behaviour:
a verdict needs ~4 seconds of the *other party actually speaking*, and only
`far` is scored by default. Check in order:
1. Is the far party talking? Watch `far/speech.wav` grow, or the
   `speech_seconds` figure in the log.
2. Is the loopback device the one WhatsApp plays through?
   (section [8](#8-isolating-whatsapps-audio-specifically))
3. `curl http://localhost:8000/health` — is `detector` what you expect?
4. Tail `events.jsonl` in the session folder; `vad_segment` lines tell you
   whether the VAD is finding speech at all.

If the VAD is finding nothing on audio you can clearly hear, try
`$env:VAD_BACKEND = "energy"` to rule the VAD in or out.

**`Fatal error in launcher: Unable to create process using ...`** — the venv
was created before this folder was moved or renamed. Windows bakes the venv's
absolute path into every `Scripts\*.exe` launcher (`pip.exe`, `uvicorn.exe`…),
so those break on a move while `python.exe` keeps working. The launcher scripts
use `python -m pip` for exactly this reason and are unaffected; if you hit it
running `pip` by hand, either use `.\.venv\Scripts\python -m pip ...` instead,
or rebuild the venv:

```powershell
Remove-Item -Recurse -Force .venv
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

**Backend takes up to ~40 s to start** — expected: it loads the 1.28 GB
detector once at startup rather than paying that cost mid-call. `/health`
answers only when it is ready.

**Verdicts lag behind the call / "analysis backlog" warnings** — inference is
slower than capture on this machine. Audio is still recorded in full; only
scoring skips. Windows already default to no overlap inside an utterance, half
the load of 50% overlap. If it still lags, raise `UTTERANCE_MIN_SECONDS` (fewer
short, padded windows) or try `MODEL_PROVIDER=openvino` on an Intel GPU.

**Auto-detect never fires during a real call** — some WhatsApp builds use a
different process name; open Task Manager during a call, find the real
`.exe` name under Details, and set it in the **Process name** field. Also
confirm both mic and speaker are actually active for WhatsApp during the
call (Windows Volume Mixer shows it as an active app).

**No WAV files under `backend/recordings/`** — check `RECORD_LOCALLY` isn't
set to `false`, and check the backend's own working directory (it writes
`recordings/` relative to where you launched it, i.e. `backend/recordings`
when using `scripts\run_backend.ps1`).

**High CPU / choppy audio** — increase the chunk length; 1-2s chunks poll
audio devices more aggressively than 4-5s ones.

---

## 12. Project layout

```
backend/            FastAPI WebSocket server
  app/main.py          entrypoint; loads the model once at startup, /health, /config
  app/config.py        every env var and default, in one place
  app/websocket.py      /ws/audio protocol; ingest on the loop, analysis on a worker
  app/models.py         message schemas
  app/vad.py            Silero VAD (+ energy fallback) and speech-segment hysteresis
  app/analysis.py       speech accumulation -> exact 64,600-sample windows
  app/xlsr_mamba.py     XLSR-Mamba + Indic head (the detector); pure-PyTorch Mamba
  app/wav2vec2_port.py  loads fairseq wav2vec 2.0 backbones into transformers
  app/antideepfake.py   AntiDeepfake MMS-300M (optional comparison detector)
  app/model.py          detector registry: loads each once, fail-soft; XLSR-SLS adapter
  app/detector.py       scores a window with every detector: primary + secondary
  app/risk.py           three-band decision + session risk EMA
  app/artifacts.py      the JSONL forensic log
  app/audio.py          chunk validation
  app/recordings.py     WAV writers: continuous, per-chunk, speech-only, per-window
  scripts/fetch_silero.py    downloads the VAD model
  scripts/verify_pipeline.py checks parity, resampling, VAD and windowing
  scripts/simulate_call.py   replays an audio file through the live pipeline
client/              Windows desktop capture app (Tkinter GUI)
  audio_capture.py      WASAPI loopback + mic capture (PyAudioWPatch)
  resample.py           anti-aliased, stateful downmix/resample to 16 kHz mono
  chunker.py            fixed-duration chunk accumulation
  ws_client.py          WebSocket session, send/ack/reconnect
  call_detector.py      auto-detects WhatsApp call start/end (pycaw)
  app.py                GUI entrypoint, risk meter
scripts/             convenience PowerShell launchers
```

```
WhatsApp Desktop
      │ plays call audio to your output device
      ▼
WASAPI loopback ──► anti-aliased 16k mono ──► chunker (far) ─┐
                                                              │  WebSocket
Microphone ────────► anti-aliased 16k mono ──► chunker (near)┘
                                                              ▼
                                            ┌─────────── FastAPI backend ───────────┐
                                            │  ack + record to disk (event loop)    │
                                            │            │                          │
                                            │            ▼      (worker thread)     │
                                            │   Silero VAD ─► speech accumulator    │
                                            │            │                          │
                                            │            ▼  every 64,600 samples    │
                                            │     XLSR-Mamba ─► 3-band + risk EMA   │
                                            └────────────┬──────────────────────────┘
                                                         ▼
                                              Tkinter client (client/)
                                              live risk meter + verdict log
```

---

## 13. Known limitations

**Detection quality**

- **The thresholds are uncalibrated.** `THRESHOLD_REAL` / `THRESHOLD_SYNTHETIC`
  are placeholders. Until they are set from your own evaluation, treat the
  bands as relative, not as evidence.
- **The detector is specialised, and it forgot some of what it knew.** Only
  its head was fine-tuned, on Hindi/Bengali/Tamil read speech, and it lost
  ground on English benchmark fakes: the branch reports ASVspoof5 EER rising
  from 2.77% to 21.28%, and on a random 40-clip ASVspoof5 sample here it was
  right 75% of the time, missing 5 of 20 spoofs. An English-language voice
  clone may get past it more often than a Hindi one.
- **Only lightly field-tested.** It scored the real voices on the recorded test
  calls correctly (25 of 28 caller windows, 22 of 23 of the tester's own) and
  caught one known deepfake, but it has **not yet been tested with deepfakes
  played through a real WhatsApp call**, and its training data is read speech in
  three languages, not conversational Hinglish.
- **Only the attack systems in IndicSynth are covered** (XTTS, VITS, FreeVC and
  related); newer voice-cloning systems are unvalidated.
- **No codec-aware handling.** WhatsApp audio has been through Opus and packet
  loss before you ever see it; the model never saw that during training.
- **Short utterances are not scored.** With the default 3 s floor, 23–37% of the
  far party's speech on the two real test calls came in shorter bursts and was
  recorded but never scored — quick back-and-forth is exactly where this bites.
  Lower `UTTERANCE_MIN_SECONDS` to trade coverage for more padded windows.
- **Padded windows carry less real speech.** Utterances of 3–4.04 s are scored
  on tile-padded input and flagged `padded`; weigh an isolated verdict on one
  accordingly.
- Only the acoustic/spectral layer exists. No prosody analysis, no
  cross-session speaker consistency.

**Capture**

- Loopback capture is whole-device by default (see [section 8](#8-isolating-whatsapps-audio-specifically)).
- The near track is a real microphone capture and so carries your room; only
  the far track is a clean digital tap.

**Privacy and operations**

- **Raw call audio for both parties is written to disk and never deleted.**
  Nothing rotates or expires it. This is the opposite of what a deployed
  version should do — voice is biometric data under the DPDP Act 2023, and
  the design target is feature-only logging with minimal raw retention. Set
  `RECORD_LOCALLY=false RECORD_CHUNKS=false RECORD_SPEECH=false
  RECORD_WINDOWS=false` for anything resembling real use, and note that both
  parties are being recorded — consent is a legal question here, not just an
  ethical one.
- No authentication by default (see [section 5](#5-configuration-reference)).
- Verdicts are advisory. Nothing blocks or terminates a call.

---

## 14. Verifying the pipeline

```powershell
cd backend
.\.venv\Scripts\python scripts\verify_pipeline.py
```

Checks, in order of how much they would hurt if wrong:

1. **Parity** — a clip scored through the live path (int16 PCM, as it arrives
   over the WebSocket) returns the same probability as the same clip scored
   through `deepfake/xlsr_sls_infer.py`. Currently exact, to 0.00e+00. If this
   drifts, the integration has changed what the model sees and the offline
   evaluation no longer describes the live system.
2. **Resampling** — content above the 8 kHz output Nyquist is filtered out
   rather than folded back into the band, and streaming in 1024-frame device
   reads is bit-identical to converting the stream in one go.
3. **VAD** — real speech padded with silence yields segments on the speech and
   discards the silence.
4. **Windows** — every window is exactly 64,600 samples and covers one
   utterance, never a pause; a long utterance slides by exactly the configured
   hop, sample-exact; and a 3–4.04 s utterance becomes a single window whose
   padding tiles the real speech, as the model card specifies.

`--skip-model` runs everything except parity, without loading the detectors.

To exercise the whole thing without placing a call — useful for demos and for
scoring an existing recording after the fact:

```powershell
.\.venv\Scripts\python scripts\simulate_call.py path\to\audio.wav
```

It speaks the real `/ws/audio` protocol against a running backend, so it drives
VAD, windowing, inference, recording and the artifact log exactly as the
desktop client does.
