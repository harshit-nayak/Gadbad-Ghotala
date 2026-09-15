"""Desktop capture client: Tkinter GUI tying together WASAPI loopback +
mic capture, resampling, chunking, and WebSocket streaming to the backend.

The same controls are also exposed to the GG web page ("Capture client" tab)
through a local HTTP API -- see control_server.py.

Run with: python app.py   (see ../README.md for setup)
"""

import logging
import queue
import sys
import threading
import time
import tkinter as tk
from collections import deque
from tkinter import ttk, messagebox
from datetime import datetime

from audio_capture import DualRecorder, AudioDevice
from resample import StreamingResampler
from chunker import TrackChunker, Chunk
from ws_client import StreamerClient, ConnectionState
from call_detector import WhatsAppCallDetector
from control_server import ControlServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("app")

DEFAULT_SERVER_URL = "ws://localhost:8000/ws/audio"

# Log lines kept for the web page. The window's own log keeps everything.
WEB_LOG_KEEP = 500


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Call Deepfake Screening — Desktop Capture")
        root.geometry("760x680")
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.dual_recorder = DualRecorder()
        self.client: StreamerClient | None = None
        self.chunkers: dict[str, TrackChunker] = {}
        # One resampler per track, held for the whole session: they carry
        # filter state between device buffers (see resample.py).
        self.resamplers: dict[str, StreamingResampler] = {}
        self.ui_queue: "queue.Queue" = queue.Queue()

        self.far_devices: dict[str, AudioDevice] = {}
        self.near_devices: dict[str, AudioDevice] = {}

        self.stats = {"far_sent": 0, "far_acked": 0, "near_sent": 0, "near_acked": 0}
        self.running = False
        self.session_source: str | None = None  # "manual" | "auto" | "web"
        self.call_detector: WhatsAppCallDetector | None = None

        # What the web page sees. Written on the Tk thread, read by the control
        # server's threads, so every access goes through the lock.
        self._web_lock = threading.Lock()
        self._web_state: dict = {}
        self._web_log: deque = deque(maxlen=WEB_LOG_KEEP)
        self._log_seq = 0
        self.risk_value = 0
        self.risk_band: str | None = None
        self.detector_tick: tuple[bool, bool] | None = None

        self._build_ui()
        self._refresh_devices()
        self._publish_web_state()
        self.root.after(100, self._drain_ui_queue)

        self.control = ControlServer(
            get_state=self._web_state_since,
            submit=lambda command, payload: self.ui_queue.put(("web", (command, payload))),
        )
        try:
            self.control.start()
            self._log(f"Web control on {self.control.url} (open the Capture client tab in the GG web page)", "info")
        except OSError as e:
            self.control = None
            self._log(f"Web control API not started ({e}). The web page's Capture client tab won't work.", "error")

    # ---------------------------------------------------------------- UI

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        conn = ttk.LabelFrame(self.root, text="Server")
        conn.pack(fill="x", **pad)
        ttk.Label(conn, text="WebSocket URL:").grid(row=0, column=0, sticky="w")
        self.url_var = tk.StringVar(value=DEFAULT_SERVER_URL)
        ttk.Entry(conn, textvariable=self.url_var, width=45).grid(row=0, column=1, sticky="we", padx=4)
        ttk.Label(conn, text="Auth token (optional):").grid(row=0, column=2, sticky="w")
        self.token_var = tk.StringVar(value="")
        ttk.Entry(conn, textvariable=self.token_var, width=20, show="*").grid(row=0, column=3, sticky="we", padx=4)
        conn.columnconfigure(1, weight=1)

        dev = ttk.LabelFrame(self.root, text="Audio sources")
        dev.pack(fill="x", **pad)
        ttk.Label(dev, text="Far (call audio via loopback):").grid(row=0, column=0, sticky="w")
        self.far_combo = ttk.Combobox(dev, state="readonly", width=55)
        self.far_combo.grid(row=0, column=1, sticky="we", padx=4, pady=2)
        ttk.Label(dev, text="Near (your microphone):").grid(row=1, column=0, sticky="w")
        self.near_combo = ttk.Combobox(dev, state="readonly", width=55)
        self.near_combo.grid(row=1, column=1, sticky="we", padx=4, pady=2)
        ttk.Button(dev, text="Refresh devices", command=self._refresh_devices).grid(row=0, column=2, rowspan=2, padx=6)
        dev.columnconfigure(1, weight=1)

        opts = ttk.LabelFrame(self.root, text="Options")
        opts.pack(fill="x", **pad)
        ttk.Label(opts, text="Chunk length (seconds):").grid(row=0, column=0, sticky="w")
        self.chunk_seconds_var = tk.StringVar(value="4")
        ttk.Spinbox(opts, from_=1, to=10, textvariable=self.chunk_seconds_var, width=5).grid(row=0, column=1, sticky="w", padx=4)

        self.auto_detect_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opts, text="Auto-detect WhatsApp calls and record automatically",
            variable=self.auto_detect_var, command=self._on_auto_detect_toggled,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Label(opts, text="Process name(s):").grid(row=1, column=2, sticky="e")
        self.process_name_var = tk.StringVar(value="WhatsApp.exe, WhatsApp.Root.exe")
        ttk.Entry(opts, textvariable=self.process_name_var, width=28).grid(row=1, column=3, sticky="w", padx=4)

        ttk.Button(opts, text="Scan active audio apps", command=self._scan_audio_processes).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )
        self.detector_tick_var = tk.StringVar(value="")
        ttk.Label(opts, textvariable=self.detector_tick_var, foreground="#555555").grid(
            row=2, column=2, columnspan=2, sticky="w", pady=(4, 0)
        )

        self.require_speaker_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opts, text="Require speaker session too (uncheck to test mic-only detection)",
            variable=self.require_speaker_var,
        ).grid(row=3, column=0, columnspan=4, sticky="w")

        ctrl = ttk.Frame(self.root)
        ctrl.pack(fill="x", **pad)
        self.start_btn = ttk.Button(ctrl, text="Start", command=lambda: self._start(source="manual"))
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(ctrl, text="Stop", command=lambda: self._stop(source="manual"), state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        self.status_var = tk.StringVar(value="Disconnected")
        ttk.Label(ctrl, textvariable=self.status_var, font=("Segoe UI", 10, "bold")).pack(side="left", padx=16)
        self.auto_status_var = tk.StringVar(value="")
        ttk.Label(ctrl, textvariable=self.auto_status_var, foreground="#2c6fbb").pack(side="left", padx=8)

        risk = ttk.LabelFrame(self.root, text="Impersonation risk (far party)")
        risk.pack(fill="x", **pad)
        self.risk_meter = ttk.Progressbar(risk, orient="horizontal", mode="determinate",
                                          maximum=100, length=280)
        self.risk_meter.grid(row=0, column=0, sticky="we", padx=6, pady=4)
        self.risk_band_var = tk.StringVar(value="awaiting speech")
        self.risk_band_label = ttk.Label(risk, textvariable=self.risk_band_var,
                                         font=("Segoe UI", 11, "bold"))
        self.risk_band_label.grid(row=0, column=1, sticky="w", padx=10)
        self.risk_detail_var = tk.StringVar(
            value="Needs ~4s of the other party actually speaking before the first score."
        )
        ttk.Label(risk, textvariable=self.risk_detail_var, foreground="#555555",
                  wraplength=680, justify="left").grid(row=1, column=0, columnspan=2,
                                                       sticky="w", padx=6, pady=(0, 4))
        risk.columnconfigure(0, weight=1)

        stats = ttk.LabelFrame(self.root, text="Stats")
        stats.pack(fill="x", **pad)
        self.stats_var = tk.StringVar(value="far: 0 sent / 0 acked   |   near: 0 sent / 0 acked")
        ttk.Label(stats, textvariable=self.stats_var).pack(anchor="w", padx=6, pady=2)

        log_frame = ttk.LabelFrame(self.root, text="Verdicts / events")
        log_frame.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(log_frame, height=14, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, side="left")
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        scroll.pack(fill="y", side="right")
        self.log.configure(yscrollcommand=scroll.set)
        self.log.tag_config("likely_synthetic", foreground="#c0392b", font=("Segoe UI", 9, "bold"))
        self.log.tag_config("uncertain", foreground="#b9770e")
        self.log.tag_config("likely_real", foreground="#1e8449")
        self.log.tag_config("suspect", foreground="#c0392b")  # legacy placeholder label
        self.log.tag_config("silence", foreground="#888888")
        self.log.tag_config("info", foreground="#2c3e50")
        self.log.tag_config("error", foreground="#c0392b", font=("Segoe UI", 9, "bold"))

    def _refresh_devices(self):
        loopbacks = self.dual_recorder.loopback_devices()
        inputs = self.dual_recorder.input_devices()

        self.far_devices = {str(d): d for d in loopbacks}
        self.near_devices = {str(d): d for d in inputs}

        self.far_combo["values"] = list(self.far_devices.keys())
        self.near_combo["values"] = list(self.near_devices.keys())

        if self.far_devices and not self.far_combo.get():
            default = next((k for k in self.far_devices if "current default output" in k), list(self.far_devices.keys())[0])
            self.far_combo.set(default)
        if self.near_devices and not self.near_combo.get():
            default = next((k for k in self.near_devices if "default microphone" in k), list(self.near_devices.keys())[0])
            self.near_combo.set(default)

        if not loopbacks:
            self._log("No WASAPI loopback devices found. Is a playback device active?", "error")

    # ------------------------------------------------------------ actions

    def _start(self, source: str = "manual"):
        if self.running:
            return  # already recording (e.g. auto-detect fired while a manual session is active)

        # Only a click in this window may open a dialog; auto-detect and the web
        # page report problems in the log instead of blocking the window.
        interactive = source == "manual"
        prefixes = {"auto": "Auto-detect: ", "web": "Web page: "}

        far_key = self.far_combo.get()
        near_key = self.near_combo.get()
        if far_key not in self.far_devices or near_key not in self.near_devices:
            if not interactive:
                self._log(f"{prefixes[source]}can't start, no far/near device is selected.", "error")
                return
            messagebox.showerror("Missing device", "Pick both a far (loopback) and near (microphone) device.")
            return

        far_device = self.far_devices[far_key]
        near_device = self.near_devices[near_key]

        try:
            chunk_seconds = float(self.chunk_seconds_var.get())
        except ValueError:
            chunk_seconds = 2.0

        self.stats = {"far_sent": 0, "far_acked": 0, "near_sent": 0, "near_acked": 0}
        self._update_stats_label()
        self._reset_risk_meter()

        self.client = StreamerClient(
            url=self.url_var.get().strip(),
            token=self.token_var.get().strip() or None,
            on_state=lambda s: self.ui_queue.put(("state", s)),
            on_verdict=lambda v: self.ui_queue.put(("verdict", v)),
            on_ack=lambda a: self.ui_queue.put(("ack", a)),
            on_error=lambda e: self.ui_queue.put(("error", e)),
            on_summary=lambda s: self.ui_queue.put(("summary", s)),
        )

        def make_chunk_sender(track):
            def send(chunk: Chunk):
                self.ui_queue.put(("chunk_sent", track))
                if self.client:
                    self.client.send_chunk(chunk)
            return send

        self.chunkers = {
            "far": TrackChunker("far", chunk_seconds, make_chunk_sender("far")),
            "near": TrackChunker("near", chunk_seconds, make_chunk_sender("near")),
        }

        self.resamplers = {
            "far": StreamingResampler(far_device.sample_rate, far_device.channels),
            "near": StreamingResampler(near_device.sample_rate, near_device.channels),
        }

        def on_far_frames(raw: bytes):
            self.chunkers["far"].add(self.resamplers["far"].process(raw))

        def on_near_frames(raw: bytes):
            self.chunkers["near"].add(self.resamplers["near"].process(raw))

        def on_capture_error(msg: str):
            self.ui_queue.put(("error", f"Capture error: {msg}"))

        try:
            self.client.start()
            self.dual_recorder.start(far_device, near_device, on_far_frames, on_near_frames, on_capture_error)
        except Exception as e:
            if not interactive:
                self._log(f"{prefixes[source]}failed to start recording: {e}", "error")
            else:
                messagebox.showerror("Failed to start", str(e))
            return

        self.running = True
        self.session_source = source
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.far_combo.configure(state="disabled")
        self.near_combo.configure(state="disabled")
        prefix = {"auto": "Auto-detected call — ", "web": "Started from the web page — "}.get(source, "")
        self._log(f"{prefix}Session started: {self.client.session_id}", "info")
        self._log(f"far <- {far_device.name}  ({far_device.sample_rate} Hz, "
                  f"{far_device.channels}ch -> 16 kHz mono)", "info")
        self._log(f"near <- {near_device.name}", "info")
        if self.resamplers["far"].quality != "anti-aliased":
            self._log(
                "WARNING: scipy is missing, so audio is being resampled without an "
                "anti-alias filter. Detector scores will not be trustworthy — run "
                "pip install -r requirements.txt in the client venv.",
                "error",
            )

    def _stop(self, source: str = "manual"):
        if not self.running:
            return
        # Don't let the detector's call-ended signal stop a session the user started
        # manually, and don't let a manual Stop click be silently ignored either --
        # manual Stop always wins.
        if source == "auto" and self.session_source != "auto":
            return

        self.running = False
        self.session_source = None
        try:
            self.dual_recorder.stop()
        except Exception:
            pass
        for resampler in self.resamplers.values():
            resampler.flush()
        for chunker in self.chunkers.values():
            chunker.flush()
        if self.client:
            self.client.stop()
        try:
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")
            self.far_combo.configure(state="readonly")
            self.near_combo.configure(state="readonly")
            self._log("Session stopped", "info")
        except tk.TclError:
            pass  # window already closed; capture/network are already torn down above

    def _on_close(self):
        if self.control:
            self.control.stop()
        if self.call_detector:
            self.call_detector.stop()
        if self.running:
            self._stop(source=self.session_source or "manual")
        self.dual_recorder.terminate()
        self.root.destroy()

    # ---------------------------------------------------- auto-detection

    def _on_auto_detect_toggled(self):
        if self.auto_detect_var.get():
            process_names = [p.strip() for p in self.process_name_var.get().split(",") if p.strip()]
            if not process_names:
                process_names = ["WhatsApp.exe", "WhatsApp.Root.exe"]
            self.call_detector = WhatsAppCallDetector(
                on_call_start=lambda: self.ui_queue.put(("auto_call_start", None)),
                on_call_end=lambda: self.ui_queue.put(("auto_call_end", None)),
                process_names=process_names,
                require_render_active=self.require_speaker_var.get(),
                on_tick=lambda cap, ren: self.ui_queue.put(("detector_tick", (cap, ren))),
            )
            self.call_detector.start()
            self.auto_status_var.set(f"Watching for {', '.join(process_names)}...")
            self._log(
                f"Auto-detect enabled for process(es): {', '.join(process_names)}. "
                f"If it never starts recording during a real call, click 'Scan active audio "
                f"apps' while the call is connected to see the exact process name Windows "
                f"reports, and watch the live mic/speaker readout to the right of that button.",
                "info",
            )
        else:
            if self.call_detector:
                self.call_detector.stop()
                self.call_detector = None
            self.auto_status_var.set("")
            self.detector_tick_var.set("")
            self.detector_tick = None
            self._log("Auto-detect disabled", "info")
            if self.running and self.session_source == "auto":
                self._stop(source="auto")

    def _scan_audio_processes(self):
        from call_detector import list_audio_processes

        rows = list_audio_processes()
        if not rows:
            self._log(
                "Scan: no process currently holds any microphone or speaker session. "
                "Run this again WHILE a WhatsApp call is connected.",
                "info",
            )
            return
        self._log("Scan: audio sessions Windows currently knows about --", "info")
        for name, mic_active, speaker_active in rows:
            mic = "ACTIVE" if mic_active else "idle"
            spk = "ACTIVE" if speaker_active else "idle"
            self._log(f"   {name}:  mic={mic}  speaker={spk}", "info")
        self._log(
            "Put whichever name shows mic=ACTIVE and speaker=ACTIVE during a real call "
            "into the 'Process name' field above.",
            "info",
        )

    # ------------------------------------------------------- web control

    def _handle_web_command(self, command: str, payload: dict):
        """Runs on the Tk thread, exactly like a click in this window."""
        if command == "start":
            if "server_url" in payload:
                self.url_var.set(str(payload["server_url"]))
            if "chunk_seconds" in payload:
                self.chunk_seconds_var.set(str(payload["chunk_seconds"]))
            if not self.running:
                if "far_device" in payload:
                    self.far_combo.set(str(payload["far_device"]))
                if "near_device" in payload:
                    self.near_combo.set(str(payload["near_device"]))
            self._start(source="web")
        elif command == "stop":
            self._stop(source="manual")  # a Stop from the page always wins, like the button
        elif command == "auto_detect":
            if "process_names" in payload:
                self.process_name_var.set(str(payload["process_names"]))
            if "require_speaker" in payload:
                self.require_speaker_var.set(bool(payload["require_speaker"]))
            enabled = bool(payload.get("enabled"))
            if enabled != self.auto_detect_var.get():
                self.auto_detect_var.set(enabled)
                self._on_auto_detect_toggled()
        elif command == "scan":
            self._scan_audio_processes()
        elif command == "refresh_devices":
            self._refresh_devices()

    def _publish_web_state(self):
        """Snapshot what the window shows. Tk variables are only read here, on the Tk thread."""
        tick = self.detector_tick
        state = {
            "running": self.running,
            "session_source": self.session_source,
            "session_id": self.client.session_id if (self.client and self.running) else None,
            "status": self.status_var.get(),
            "server_url": self.url_var.get(),
            "token_set": bool(self.token_var.get().strip()),
            "far_devices": list(self.far_devices),
            "near_devices": list(self.near_devices),
            "far_device": self.far_combo.get(),
            "near_device": self.near_combo.get(),
            "chunk_seconds": self.chunk_seconds_var.get(),
            "auto_detect": bool(self.auto_detect_var.get()),
            "process_names": self.process_name_var.get(),
            "require_speaker": bool(self.require_speaker_var.get()),
            "auto_status": self.auto_status_var.get(),
            "detector_tick": {"mic": tick[0], "speaker": tick[1]} if tick else None,
            "stats": dict(self.stats),
            "risk": {
                "value": self.risk_value,
                "band": self.risk_band,
                "label": self.risk_band_var.get(),
                "detail": self.risk_detail_var.get(),
            },
        }
        with self._web_lock:
            self._web_state = state

    def _web_state_since(self, since: int) -> dict:
        """Called from the control server's threads."""
        with self._web_lock:
            return {
                **self._web_state,
                "log_seq": self._log_seq,
                "log": [entry for entry in self._web_log if entry["id"] > since],
            }

    # --------------------------------------------------------- UI thread

    def _drain_ui_queue(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "state":
                    self._on_state(payload)
                elif kind == "verdict":
                    self._on_verdict(payload)
                elif kind == "ack":
                    self._on_ack(payload)
                elif kind == "summary":
                    self._on_summary(payload)
                elif kind == "error":
                    self._log(str(payload), "error")
                elif kind == "chunk_sent":
                    self.stats[f"{payload}_sent"] += 1
                    self._update_stats_label()
                elif kind == "auto_call_start":
                    self._log("Auto-detect: WhatsApp call started", "info")
                    self._start(source="auto")
                elif kind == "auto_call_end":
                    self._log("Auto-detect: WhatsApp call ended", "info")
                    self._stop(source="auto")  # no-ops if a manual session is active; see _stop's guard
                elif kind == "detector_tick":
                    cap_active, ren_active = payload
                    self.detector_tick = (bool(cap_active), bool(ren_active))
                    mic = "ACTIVE" if cap_active else "idle"
                    spk = "ACTIVE" if ren_active else "idle"
                    self.detector_tick_var.set(f"right now: mic={mic}  speaker={spk}")
                elif kind == "web":
                    command, command_payload = payload
                    try:
                        self._handle_web_command(command, command_payload)
                    except Exception as e:  # noqa: BLE001 -- a bad web request must not kill the UI loop
                        logger.exception(f"Web command {command} failed")
                        self._log(f"Web page: {command} failed: {e}", "error")
        except queue.Empty:
            pass
        except tk.TclError:
            return  # window already gone; don't reschedule
        try:
            self._publish_web_state()
            self.root.after(100, self._drain_ui_queue)
        except tk.TclError:
            pass  # window already gone

    def _on_state(self, state: ConnectionState):
        labels = {
            ConnectionState.DISCONNECTED: "Disconnected",
            ConnectionState.CONNECTING: "Connecting...",
            ConnectionState.CONNECTED: "Connected",
            ConnectionState.STREAMING: "Connected & streaming",
            ConnectionState.ERROR: "Error",
        }
        self.status_var.set(labels.get(state, str(state)))

    def _on_ack(self, ack: dict):
        track = ack.get("track")
        if track in ("far", "near"):
            self.stats[f"{track}_acked"] += 1
            self._update_stats_label()

    RISK_COLORS = {"low": "#1e8449", "elevated": "#b9770e", "high": "#c0392b"}

    def _reset_risk_meter(self):
        self.risk_meter["value"] = 0
        self.risk_value = 0
        self.risk_band = None
        self.risk_band_var.set("awaiting speech")
        self.risk_band_label.configure(foreground="#555555")
        self.risk_detail_var.set(
            "Needs ~4s of the other party actually speaking before the first score."
        )

    def _on_verdict(self, verdict: dict):
        label = verdict.get("label", "?")
        track = verdict.get("track", "?")
        seq = verdict.get("sequence", "?")
        detail = verdict.get("detail", "")
        p_bonafide = verdict.get("p_bonafide")
        speech_s = verdict.get("speech_seconds")
        latency = verdict.get("latency_ms")
        tag = label if label in ("likely_synthetic", "uncertain", "likely_real",
                                 "suspect", "silence") else "info"

        ts = datetime.now().strftime("%H:%M:%S")
        parts = [f"[{ts}] {track} window {seq}  {label}"]
        if p_bonafide is not None:
            parts.append(f"P(real)={p_bonafide:.3f} [{verdict.get('detector', '?')}]")
        # The same window scored by any other loaded detector, for comparison.
        # It does not change the verdict or the risk meter.
        for other in verdict.get("secondary") or []:
            parts.append(f"| {other.get('detector', '?')} P(real)={other.get('p_bonafide', 0):.3f}")
        if speech_s is not None:
            parts.append(f"speech={speech_s:.1f}s")
        if latency is not None:
            parts.append(f"{latency:.0f}ms")
        if verdict.get("padded"):
            # Under one 4 s window. AntiDeepfake scores its real speech as-is;
            # XLSR-SLS needs exactly 4.04 s and scores it tile-padded.
            parts.append("[short]")
        self._log("  ".join(parts) + (f"\n    {detail}" if detail else ""), tag)

        # The meter tracks the far party only -- scoring "near" is a debugging
        # aid, and letting your own voice move the caller's risk would be wrong.
        if track != "far":
            return
        risk = verdict.get("session_risk")
        band = verdict.get("risk_band")
        if risk is None or band is None:
            return
        self.risk_value = round(risk * 100)
        self.risk_band = band
        self.risk_meter["value"] = self.risk_value
        self.risk_band_var.set(f"{band.upper()}  ({risk:.0%})")
        self.risk_band_label.configure(foreground=self.RISK_COLORS.get(band, "#555555"))
        self.risk_detail_var.set(verdict.get("recommendation", ""))

    def _on_summary(self, summary: dict):
        far = (summary.get("risk") or {}).get("far")
        self._log(f"Session summary (detector: {summary.get('detector', '?')})", "info")
        for track, stats in (summary.get("tracks") or {}).items():
            self._log(
                f"   {track}: {stats.get('speech_seconds', 0)}s speech in "
                f"{stats.get('total_frames', 0)} frames "
                f"({stats.get('speech_ratio', 0):.0%} speech), "
                f"{stats.get('windows_emitted', 0)} windows scored "
                f"[VAD: {stats.get('vad_backend', '?')}]",
                "info",
            )
        if far:
            counts = far.get("counts", {})
            self._log(
                f"   far risk: {far.get('risk_band', '?')} ({far.get('session_risk', 0):.0%})  "
                f"real={counts.get('likely_real', 0)} "
                f"uncertain={counts.get('uncertain', 0)} "
                f"synthetic={counts.get('likely_synthetic', 0)}",
                "likely_synthetic" if far.get("risk_band") == "high" else "info",
            )
        if summary.get("artifacts_dir"):
            self._log(f"   recordings + logs: {summary['artifacts_dir']}", "info")

    def _update_stats_label(self):
        self.stats_var.set(
            f"far: {self.stats['far_sent']} sent / {self.stats['far_acked']} acked"
            f"   |   near: {self.stats['near_sent']} sent / {self.stats['near_acked']} acked"
        )

    def _log(self, text: str, tag: str = "info"):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")
        with self._web_lock:
            self._log_seq += 1
            self._web_log.append({"id": self._log_seq, "ts": time.time(), "text": text, "tag": tag})


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
