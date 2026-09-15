"""Replay an audio file through the live pipeline as if it were a call.

    python scripts/simulate_call.py ../../deepfake/df00.mp3
    python scripts/simulate_call.py far.wav --near me.wav --realtime

Speaks the real /ws/audio protocol against a running backend, so it exercises
exactly what the desktop client exercises -- VAD, window assembly, inference,
recording and the artifact log -- without needing a WhatsApp call, a second
person, or a working loopback device.

Useful for demos (replay a known deepfake and watch the risk band move), for
regression testing after changing thresholds, and for scoring an existing call
recording after the fact.

Needs the backend running:  python -m app.main
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import config  # noqa: E402

BAND_MARK = {"low": "OK  ", "elevated": "WARN", "high": "HIGH"}


def load_pcm16_mono_16k(path: Path) -> np.ndarray:
    """Any audio file -> int16 mono at 16 kHz, matching what the client sends."""
    import soundfile as sf

    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if sr != config.SAMPLE_RATE:
        import math

        from scipy.signal import resample_poly

        g = math.gcd(int(sr), config.SAMPLE_RATE)
        mono = resample_poly(mono, config.SAMPLE_RATE // g, int(sr) // g)
    return np.clip(np.rint(mono * 32768.0), -32768, 32767).astype("<i2")


async def stream(url: str, token: str | None, tracks: dict[str, np.ndarray],
                 chunk_seconds: float, realtime: bool) -> int:
    import websockets

    session_id = str(uuid.uuid4())
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    chunk_samples = int(config.SAMPLE_RATE * chunk_seconds)

    verdicts: list[dict] = []
    summary: dict | None = None
    acks = 0

    async with websockets.connect(url, additional_headers=headers, max_size=None) as ws:
        await ws.send(json.dumps({
            "type": "session_start", "session_id": session_id,
            "sample_rate": config.SAMPLE_RATE, "channels": 1,
            "encoding": "pcm_s16le", "source": "simulate_call.py",
        }))
        print(f"session  : {session_id}")
        for name, samples in tracks.items():
            print(f"{name:9}: {len(samples)/config.SAMPLE_RATE:.1f}s")
        print(f"chunks   : {chunk_seconds}s"
              f"{' (paced in real time)' if realtime else ' (as fast as possible)'}\n")

        async def receive():
            nonlocal acks, summary
            try:
                async for raw in ws:
                    message = json.loads(raw)
                    kind = message.get("type")
                    if kind == "chunk_ack":
                        acks += 1
                    elif kind == "verdict":
                        verdicts.append(message)
                        band = message.get("risk_band", "?")
                        print(
                            f"  [{BAND_MARK.get(band, '?   ')}] "
                            f"{message['track']} window {message['sequence']:>2}  "
                            f"{message['label']:<16} "
                            f"P(real)={message.get('p_bonafide', 0):.3f}  "
                            f"risk={message.get('session_risk', 0):.2f}  "
                            f"speech={message.get('speech_seconds', 0):.1f}s  "
                            f"{message.get('latency_ms', 0):.0f}ms"
                        )
                    elif kind == "session_summary":
                        summary = message
                    elif kind == "error":
                        print(f"  ERROR from server: {message.get('message')}", file=sys.stderr)
            except Exception:  # noqa: BLE001
                pass  # connection closed by teardown

        receiver = asyncio.create_task(receive())

        sequences = {name: 0 for name in tracks}
        offset, longest = 0, max(len(s) for s in tracks.values())
        while offset < longest:
            for name, samples in tracks.items():
                piece = samples[offset:offset + chunk_samples]
                if not len(piece):
                    continue
                payload = piece.tobytes()
                await ws.send(json.dumps({
                    "type": "audio_chunk", "session_id": session_id, "track": name,
                    "sequence": sequences[name], "timestamp": int(time.time() * 1000),
                    "duration_ms": int(len(piece) / config.SAMPLE_RATE * 1000),
                    "sample_rate": config.SAMPLE_RATE, "channels": 1,
                    "encoding": "pcm_s16le", "payload_size": len(payload),
                }))
                await ws.send(payload)
                sequences[name] += 1
            offset += chunk_samples
            await asyncio.sleep(chunk_seconds if realtime else 0.01)

        await ws.send(json.dumps({"type": "session_end", "session_id": session_id}))
        # Give the backend room to drain its queue, flush the VAD and score the
        # final window before the socket closes under it.
        for _ in range(600):
            if summary is not None:
                break
            await asyncio.sleep(0.1)
        receiver.cancel()

    print(f"\n{acks} chunks acked, {len(verdicts)} verdicts")
    if summary:
        for track, stats in (summary.get("tracks") or {}).items():
            print(f"  {track}: {stats['speech_seconds']}s speech "
                  f"({stats['speech_ratio']:.0%} of {stats['total_frames']} frames), "
                  f"{stats['windows_emitted']} windows, VAD={stats['vad_backend']}")
        for track, risk in (summary.get("risk") or {}).items():
            print(f"  {track} risk: {risk['risk_band'].upper()} "
                  f"({risk['session_risk']:.0%})  counts={risk['counts']}  "
                  f"mean P(real)={risk['mean_p_bonafide']}")
        print(f"  detector: {summary.get('detector')}")
        print(f"  artifacts: {summary.get('artifacts_dir')}")
    else:
        print("  (no session_summary received)", file=sys.stderr)
    return 0 if verdicts else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("far", help="audio to send as the other party (the scored track)")
    ap.add_argument("--near", help="audio to send as your own mic (optional)")
    ap.add_argument("--url", default="ws://localhost:8000/ws/audio")
    ap.add_argument("--token", default=None, help="AUTH_TOKEN, if the backend requires one")
    ap.add_argument("--chunk-seconds", type=float, default=4.0)
    ap.add_argument("--realtime", action="store_true",
                    help="pace chunks at wall-clock speed, as a real call would")
    args = ap.parse_args()

    tracks = {"far": load_pcm16_mono_16k(Path(args.far))}
    if args.near:
        tracks["near"] = load_pcm16_mono_16k(Path(args.near))

    try:
        return asyncio.run(stream(args.url, args.token, tracks,
                                  args.chunk_seconds, args.realtime))
    except OSError as e:
        print(f"Could not reach {args.url}: {e}\nIs the backend running? "
              f"(python -m app.main)", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
