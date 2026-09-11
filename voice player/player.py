"""Voice player for the SENDER machine (the "fake caller").

Plays audio files into a virtual microphone (VB-Cable's "CABLE Input") so
WhatsApp Desktop sends them to the other side of the call exactly as if they
were spoken into a mic. On the receiving laptop the detector captures them
like any other caller.

Every clip played is appended to playlog.csv (UTC start/end, file, real/fake
label) so the detector's per-window scores can later be matched to what was
actually sent.

Setup on this machine:
  1. Install VB-Cable (https://vb-audio.com/Cable/), reboot.
  2. In WhatsApp -> call -> microphone, choose "CABLE Output (VB-Audio ...)".
  3. Here, send to "CABLE Input (VB-Audio ...)" (selected by default).
"""

from __future__ import annotations

import csv
import math
import queue
import socket
import threading
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.signal import resample_poly

HERE = Path(__file__).resolve().parent
LOG_PATH = HERE / "playlog.csv"
LOG_FIELDS = [
    "started_utc", "ended_utc", "file", "label", "clip_seconds",
    "played_seconds", "completed", "send_device", "host",
]
AUDIO_TYPES = [("Audio files", "*.wav *.mp3 *.flac *.ogg"), ("All files", "*.*")]
LABELS = ("fake", "real", "unlabeled")
VIRTUAL_MIC_HINT = "cable input"


@dataclass(frozen=True)
class OutputDevice:
    index: int
    name: str
    rate: int
    channels: int


def _wasapi_index() -> int | None:
    for i, api in enumerate(sd.query_hostapis()):
        if "WASAPI" in api["name"]:
            return i
    return None


def output_devices() -> list[OutputDevice]:
    """Render endpoints. WASAPI only on Windows: MME truncates names to 31
    chars and lists every device several times over."""
    wasapi = _wasapi_index()
    out = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_output_channels"] <= 0:
            continue
        if wasapi is not None and d["hostapi"] != wasapi:
            continue
        out.append(OutputDevice(i, d["name"], int(d["default_samplerate"]), int(d["max_output_channels"])))
    return out


def default_output_index() -> int | None:
    wasapi = _wasapi_index()
    if wasapi is not None:
        idx = sd.query_hostapis(wasapi)["default_output_device"]
    else:
        idx = sd.default.device[1]
    return idx if idx is not None and idx >= 0 else None


def load_mono(path: Path) -> tuple[np.ndarray, int]:
    data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    return data.mean(axis=1), int(rate)


def to_rate(mono: np.ndarray, src: int, dst: int) -> np.ndarray:
    """WASAPI shared mode only accepts the device's own mix rate."""
    if src != dst:
        g = math.gcd(src, dst)
        mono = resample_poly(mono, dst // g, src // g).astype(np.float32)
    return np.clip(mono, -1.0, 1.0)


class _Playback:
    """One clip on one device, on its own thread, so several devices can play
    the same clip at once (virtual mic + monitor headphones).

    Blocking writes, not a callback stream: on WASAPI a callback stream
    started from any thread but the main one fails with PaErrorCode -9999,
    while blocking streams work from any thread."""

    BLOCK_SECONDS = 0.05   # also the Stop reaction time

    def __init__(self, device: OutputDevice, samples: np.ndarray, stop_evt: threading.Event):
        self.device = device
        self.samples = samples
        self.stop_evt = stop_evt
        self.pos = 0
        self.error: Exception | None = None
        self.done = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def _run(self):
        stream = None
        try:
            stream = sd.OutputStream(device=self.device.index, samplerate=self.device.rate,
                                     channels=self.device.channels, dtype="float32")
            stream.start()
            block = max(1, int(self.device.rate * self.BLOCK_SECONDS))
            while self.pos < len(self.samples) and not self.stop_evt.is_set():
                chunk = self.samples[self.pos:self.pos + block]
                stream.write(np.repeat(chunk[:, None], self.device.channels, axis=1))
                self.pos += len(chunk)
            if self.stop_evt.is_set():
                stream.abort()
            else:
                stream.stop()   # returns once the buffered tail has played
        except Exception as e:
            self.error = e
        finally:
            if stream is not None:
                stream.close()
            self.done.set()

    @property
    def completed(self) -> bool:
        return self.error is None and self.pos >= len(self.samples) and not self.stop_evt.is_set()

    @property
    def played_seconds(self) -> float:
        return self.pos / self.device.rate

    def close(self):
        self._thread.join(timeout=2)


def append_log(row: dict):
    new = not LOG_PATH.exists()
    with LOG_PATH.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow(row)


def _utc(ts: datetime) -> str:
    return ts.isoformat(timespec="milliseconds")


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.items: dict[str, dict] = {}   # tree iid -> {path, label, seconds}
        self.stop_evt = threading.Event()
        self.worker: threading.Thread | None = None
        self.ui_q: queue.Queue = queue.Queue()
        self.devices: list[OutputDevice] = []

        root.title("Voice Player - fake caller")
        root.minsize(620, 420)
        self._build()
        self._refresh_devices()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(100, self._drain)

    # ---------- layout ----------
    def _build(self):
        pad = {"padx": 8, "pady": 4}
        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Send to (WhatsApp mic):").grid(row=0, column=0, sticky="w")
        self.send_var = tk.StringVar()
        self.send_box = ttk.Combobox(top, textvariable=self.send_var, state="readonly")
        self.send_box.grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(top, text="Refresh", command=self._refresh_devices).grid(row=0, column=2)

        self.monitor_on = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Also play on:", variable=self.monitor_on).grid(row=1, column=0, sticky="w")
        self.monitor_var = tk.StringVar()
        self.monitor_box = ttk.Combobox(top, textvariable=self.monitor_var, state="readonly")
        self.monitor_box.grid(row=1, column=1, sticky="ew", padx=4, pady=(4, 0))

        mid = ttk.Frame(self.root)
        mid.pack(fill="both", expand=True, **pad)
        self.tree = ttk.Treeview(mid, columns=("label", "seconds", "state"), selectmode="extended")
        self.tree.heading("#0", text="File")
        self.tree.heading("label", text="Label")
        self.tree.heading("seconds", text="Length (s)")
        self.tree.heading("state", text="")
        self.tree.column("#0", width=300)
        self.tree.column("label", width=80, anchor="center")
        self.tree.column("seconds", width=80, anchor="e")
        self.tree.column("state", width=90, anchor="center")
        scroll = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        edit = ttk.Frame(self.root)
        edit.pack(fill="x", **pad)
        ttk.Button(edit, text="Add files...", command=self._add_files).pack(side="left")
        ttk.Button(edit, text="Remove", command=self._remove).pack(side="left", padx=4)
        ttk.Label(edit, text="Mark selected:").pack(side="left", padx=(12, 4))
        for label in LABELS:
            ttk.Button(edit, text=label, command=lambda l=label: self._mark(l)).pack(side="left", padx=2)

        run = ttk.Frame(self.root)
        run.pack(fill="x", **pad)
        self.play_sel_btn = ttk.Button(run, text="Play selected", command=lambda: self._play(selected=True))
        self.play_sel_btn.pack(side="left")
        self.play_all_btn = ttk.Button(run, text="Play all", command=lambda: self._play(selected=False))
        self.play_all_btn.pack(side="left", padx=4)
        self.stop_btn = ttk.Button(run, text="Stop", command=self.stop_evt.set, state="disabled")
        self.stop_btn.pack(side="left")
        ttk.Label(run, text="Pause between clips (s):").pack(side="left", padx=(12, 4))
        self.gap_var = tk.DoubleVar(value=2.0)
        ttk.Spinbox(run, from_=0, to=60, increment=0.5, width=5, textvariable=self.gap_var).pack(side="left")

        self.status_var = tk.StringVar(value=f"Log: {LOG_PATH}")
        ttk.Label(self.root, textvariable=self.status_var, anchor="w").pack(fill="x", padx=8, pady=(0, 8))

    # ---------- devices ----------
    def _refresh_devices(self):
        try:
            self.devices = output_devices()
        except Exception as e:
            messagebox.showerror("Audio devices", f"Could not list output devices:\n{e}")
            self.devices = []
        names = [d.name for d in self.devices]
        self.send_box["values"] = names
        self.monitor_box["values"] = names

        cable = next((d.name for d in self.devices if VIRTUAL_MIC_HINT in d.name.lower()), None)
        if self.send_var.get() not in names:
            self.send_var.set(cable or (names[0] if names else ""))
        if self.monitor_var.get() not in names:
            default = default_output_index()
            monitor = next((d.name for d in self.devices if d.index == default), None)
            if monitor is None or monitor == cable:
                monitor = next((n for n in names if n != cable), "")
            self.monitor_var.set(monitor)
        if cable is None:
            self.status_var.set("No 'CABLE Input' device found - install VB-Cable, or pick another output.")

    def _device(self, name: str) -> OutputDevice | None:
        return next((d for d in self.devices if d.name == name), None)

    # ---------- playlist ----------
    def _add_files(self):
        paths = filedialog.askopenfilenames(title="Choose clips to play", filetypes=AUDIO_TYPES)
        bad = []
        for p in paths:
            path = Path(p)
            try:
                seconds = sf.info(str(path)).duration
            except Exception as e:
                bad.append(f"{path.name}: {e}")
                continue
            iid = self.tree.insert("", "end", text=path.name, values=("unlabeled", f"{seconds:.1f}", ""))
            self.items[iid] = {"path": path, "label": "unlabeled", "seconds": seconds}
        if bad:
            messagebox.showwarning("Some files could not be read", "\n".join(bad))

    def _remove(self):
        if self._busy():
            return
        for iid in self.tree.selection():
            self.tree.delete(iid)
            self.items.pop(iid, None)

    def _mark(self, label: str):
        for iid in self.tree.selection():
            self.items[iid]["label"] = label
            self.tree.set(iid, "label", label)

    # ---------- playback ----------
    def _busy(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def _play(self, selected: bool):
        if self._busy():
            return
        iids = list(self.tree.selection()) if selected else list(self.tree.get_children())
        if not iids:
            self.status_var.set("Nothing to play - add files" + (" and select some." if selected else "."))
            return
        send = self._device(self.send_var.get())
        if send is None:
            messagebox.showerror("Voice Player", "Choose a device to send to.")
            return
        monitor = self._device(self.monitor_var.get()) if self.monitor_on.get() else None
        if monitor is not None and monitor.index == send.index:
            monitor = None
        try:
            gap = max(0.0, float(self.gap_var.get()))
        except (tk.TclError, ValueError):
            gap = 0.0

        self.stop_evt.clear()
        self._set_running(True)
        self.worker = threading.Thread(target=self._run, args=(iids, send, monitor, gap), daemon=True)
        self.worker.start()

    def _run(self, iids: list[str], send: OutputDevice, monitor: OutputDevice | None, gap: float):
        host = socket.gethostname()
        for n, iid in enumerate(iids):
            if self.stop_evt.is_set():
                break
            item = self.items.get(iid)
            if item is None:
                continue
            name = item["path"].name
            try:
                mono, rate = load_mono(item["path"])
                playbacks = [_Playback(send, to_rate(mono, rate, send.rate), self.stop_evt)]
                if monitor is not None:
                    playbacks.append(_Playback(monitor, to_rate(mono, rate, monitor.rate), self.stop_evt))
            except Exception as e:
                self._post("error", f"{name}: {e}")
                continue

            self._post("state", iid, "playing")
            clip_seconds = len(mono) / rate
            started = datetime.now(timezone.utc)
            for p in playbacks:
                p.start()
            while not all(p.done.wait(0.1) for p in playbacks):
                self._post("status", f"Playing {name}  {playbacks[0].played_seconds:5.1f} / {clip_seconds:.1f} s"
                                     f"  ({n + 1}/{len(iids)})")
            ended = datetime.now(timezone.utc)
            for p in playbacks:
                p.close()
            errors = [f"{p.device.name}: {p.error}" for p in playbacks if p.error is not None]
            if errors:
                self._post("error", f"{name}\n" + "\n".join(errors))

            played = min(playbacks[0].played_seconds, clip_seconds)
            completed = playbacks[0].completed
            append_log({
                "started_utc": _utc(started), "ended_utc": _utc(ended), "file": str(item["path"]),
                "label": item["label"], "clip_seconds": f"{clip_seconds:.3f}",
                "played_seconds": f"{played:.3f}", "completed": completed,
                "send_device": send.name, "host": host,
            })
            self._post("state", iid, "played" if completed else "stopped")

            if gap and n < len(iids) - 1:
                self._post("status", f"Pause {gap:g} s")
                self.stop_evt.wait(gap)
        self._post("finished")

    # ---------- worker -> UI ----------
    def _post(self, *msg):
        self.ui_q.put(msg)

    def _drain(self):
        try:
            while True:
                kind, *args = self.ui_q.get_nowait()
                if kind == "status":
                    self.status_var.set(args[0])
                elif kind == "state":
                    iid, state = args
                    if self.tree.exists(iid):
                        self.tree.set(iid, "state", state)
                elif kind == "error":
                    self.status_var.set(f"Error - {args[0]}")
                    messagebox.showerror("Playback error", args[0])
                elif kind == "finished":
                    self._set_running(False)
                    self.status_var.set(f"Done. Log: {LOG_PATH}")
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    def _set_running(self, running: bool):
        self.play_sel_btn["state"] = "disabled" if running else "normal"
        self.play_all_btn["state"] = "disabled" if running else "normal"
        self.stop_btn["state"] = "normal" if running else "disabled"

    def _on_close(self):
        self.stop_evt.set()
        if self.worker is not None:
            self.worker.join(timeout=2)
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
