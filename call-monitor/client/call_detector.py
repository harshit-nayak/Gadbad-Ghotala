"""Detects an active WhatsApp Desktop call without any window/UI inspection.

Signal used: WhatsApp only opens the **microphone** for a voice/video call
(or a voice-note recording), and only plays **continuous output audio**
while a call is actually connected. So "WhatsApp.exe has an active capture
(mic) session AND an active render (speaker) session at the same time,
sustained for a few seconds" is a strong, WhatsApp-version/UI-independent
signal that a call is in progress. This is the same public WASAPI
per-process session API Windows' own Volume Mixer uses -- no hooking, no
special permission, no dependence on WhatsApp's window layout or language.

Requiring the render session too (not just capture) filters out the
obvious false positive: recording a voice note only opens the mic.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable

logger = logging.getLogger("call_detector")

# The Microsoft Store package for WhatsApp Desktop (the common install path
# on Windows 11 -- "Get from Microsoft Store") runs as WhatsApp.Root.exe, NOT
# WhatsApp.exe. Match both so it works regardless of which one is installed.
DEFAULT_PROCESS_NAMES = ("whatsapp.exe", "whatsapp.root.exe")


@dataclass
class SessionInfo:
    process_name: str
    active: bool


def get_capture_sessions() -> list[SessionInfo]:
    """Audio sessions on the default microphone (capture) endpoint."""
    from pycaw.pycaw import AudioUtilities, AudioSession, IAudioSessionControl2

    mic = AudioUtilities.GetMicrophone()
    if mic is None:
        return []
    device = AudioUtilities.CreateDevice(mic)
    mgr = device.AudioSessionManager
    if mgr is None:
        return []
    enumerator = mgr.GetSessionEnumerator()
    out = []
    for i in range(enumerator.GetCount()):
        ctl = enumerator.GetSession(i)
        if ctl is None:
            continue
        ctl2 = ctl.QueryInterface(IAudioSessionControl2)
        if ctl2 is None:
            continue
        session = AudioSession(ctl2)
        proc = session.Process
        out.append(SessionInfo(process_name=proc.name() if proc else "", active=(int(session.State) == 1)))
    return out


def get_render_sessions() -> list[SessionInfo]:
    """Audio sessions on the default speaker/headphone (render) endpoint."""
    from pycaw.pycaw import AudioUtilities

    out = []
    for s in AudioUtilities.GetAllSessions():
        proc = s.Process
        out.append(SessionInfo(process_name=proc.name() if proc else "", active=(int(s.State) == 1)))
    return out


def _any_active(sessions: Iterable[SessionInfo], process_names: set[str]) -> bool:
    return any(s.process_name.lower() in process_names and s.active for s in sessions)


def list_audio_processes() -> list[tuple[str, bool, bool]]:
    """Every process name with a registered mic and/or speaker session,
    each flagged with whether it's active RIGHT NOW: (name, mic_active,
    speaker_active). A session can exist while idle (e.g. an app that used
    the mic earlier), so "registered" != "active" -- this is a diagnostic
    aid to find WhatsApp's exact process name and see live whether Windows
    considers it actively using the mic/speaker. Call it WHILE a call is
    connected to see which name(s) actually go active.
    """
    combined: dict[str, list[bool]] = {}  # name -> [mic_active, speaker_active]

    try:
        for s in get_capture_sessions():
            if s.process_name:
                combined.setdefault(s.process_name, [False, False])[0] |= s.active
    except Exception as e:
        logger.warning(f"list_audio_processes: capture fetch failed: {e}")
    try:
        for s in get_render_sessions():
            if s.process_name:
                combined.setdefault(s.process_name, [False, False])[1] |= s.active
    except Exception as e:
        logger.warning(f"list_audio_processes: render fetch failed: {e}")

    return sorted((name, bool(flags[0]), bool(flags[1])) for name, flags in combined.items())


class WhatsAppCallDetector:
    """Background poller that fires on_call_start()/on_call_end() when a
    matching process's audio sessions go active/inactive for a sustained
    period. Debounced both ways to avoid flapping on brief state blips.

    Callbacks run on the poller's own thread -- they should only hand work
    off (e.g. push to a queue), not touch UI toolkits directly.
    """

    def __init__(
        self,
        on_call_start: Callable[[], None],
        on_call_end: Callable[[], None],
        process_names: Iterable[str] = DEFAULT_PROCESS_NAMES,
        poll_interval_s: float = 1.0,
        start_debounce_s: float = 1.5,
        end_debounce_s: float = 3.0,
        require_render_active: bool = True,
        capture_fetcher: Callable[[], list[SessionInfo]] = get_capture_sessions,
        render_fetcher: Callable[[], list[SessionInfo]] = get_render_sessions,
        on_tick: Callable[[bool, bool], None] | None = None,
    ):
        self.on_call_start = on_call_start
        self.on_call_end = on_call_end
        self.process_names = {p.lower() for p in process_names}
        self.poll_interval_s = poll_interval_s
        self.start_debounce_s = start_debounce_s
        self.end_debounce_s = end_debounce_s
        self.require_render_active = require_render_active
        self._capture_fetcher = capture_fetcher
        self._render_fetcher = render_fetcher
        # Fires on every poll (not just start/end transitions) with the raw
        # (capture_active, render_active) booleans for the matched process --
        # lets the UI show live "what am I seeing right now" feedback.
        self.on_tick = on_tick

        self._thread: threading.Thread | None = None
        self._running = threading.Event()

        self.call_active = False
        self._active_since: float | None = None
        self._inactive_since: float | None = None

    def start(self):
        if self._running.is_set():
            return
        self._running.set()
        self.call_active = False
        self._active_since = None
        self._inactive_since = None
        self._thread = threading.Thread(target=self._loop, name="WhatsAppCallDetector", daemon=True)
        self._thread.start()

    def stop(self):
        self._running.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _raw_active_detailed(self) -> tuple[bool, bool]:
        """Returns (capture_active, render_active) for the matched process
        name(s), each independently -- so callers can see partial matches
        (e.g. mic active but speaker not) instead of just a final verdict.
        """
        try:
            capture_sessions = self._capture_fetcher()
            capture_active = _any_active(capture_sessions, self.process_names)
        except Exception as e:
            logger.warning(f"Failed to read microphone sessions: {e}")
            capture_active = False
        try:
            render_sessions = self._render_fetcher()
            render_active = _any_active(render_sessions, self.process_names)
        except Exception as e:
            logger.warning(f"Failed to read speaker sessions: {e}")
            render_active = False
        return capture_active, render_active

    def poll_once(self, now: float | None = None):
        """One debounce-state-machine step. Split out from _loop for unit testing."""
        now = time.monotonic() if now is None else now
        capture_active, render_active = self._raw_active_detailed()
        if self.on_tick:
            try:
                self.on_tick(capture_active, render_active)
            except Exception as e:
                logger.warning(f"on_tick callback raised: {e}")
        raw_active = capture_active and (render_active if self.require_render_active else True)

        if raw_active:
            self._inactive_since = None
            if self._active_since is None:
                self._active_since = now
            if not self.call_active and (now - self._active_since) >= self.start_debounce_s:
                self.call_active = True
                logger.info("Call detected (sustained mic+speaker session active)")
                self.on_call_start()
        else:
            self._active_since = None
            if self._inactive_since is None:
                self._inactive_since = now
            if self.call_active and (now - self._inactive_since) >= self.end_debounce_s:
                self.call_active = False
                logger.info("Call ended (session inactive)")
                self.on_call_end()

    def _loop(self):
        while self._running.is_set():
            self.poll_once()
            time.sleep(self.poll_interval_s)
