"""Windows audio capture: system-output ("far" / the other party) loopback
via WASAPI, and microphone ("near" / the local user) capture, using
PyAudioWPatch (a WASAPI-loopback-patched PyAudio fork).

Isolating WhatsApp Desktop's call audio specifically (not your whole
system) is a Windows Sound Settings step, not code -- see README.md's
"Isolating WhatsApp's audio" section. This module simply loops back
whichever output device you choose in the client UI.
"""

import queue
import threading
import logging

import pyaudiowpatch as pyaudio

logger = logging.getLogger("audio_capture")

FRAMES_PER_READ = 1024  # native-format frames per blocking read


class AudioDevice:
    def __init__(self, index: int, name: str, sample_rate: int, channels: int, is_loopback: bool):
        self.index = index
        self.name = name
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_loopback = is_loopback

    def __str__(self):
        return self.name


def list_loopback_devices(pa: pyaudio.PyAudio) -> list[AudioDevice]:
    """Output devices you can capture ("far" / the other party's audio).

    Includes the WASAPI loopback of the current default speaker/headphone
    device plus any other render endpoint's loopback PortAudio exposes.
    """
    devices = []
    try:
        wasapi_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError:
        logger.error("WASAPI host API not available on this system")
        return devices

    default_out_index = wasapi_info.get("defaultOutputDevice", -1)
    default_out_name = ""
    if default_out_index != -1:
        try:
            default_out_name = pa.get_device_info_by_index(default_out_index)["name"]
        except Exception:
            default_out_name = ""

    for loopback in pa.get_loopback_device_info_generator():
        name = loopback["name"]
        if default_out_name and default_out_name in name:
            name = f"{name}  (current default output)"
        devices.append(
            AudioDevice(
                index=loopback["index"],
                name=name,
                sample_rate=int(loopback["defaultSampleRate"]),
                channels=int(loopback["maxInputChannels"]),
                is_loopback=True,
            )
        )
    return devices


def list_input_devices(pa: pyaudio.PyAudio) -> list[AudioDevice]:
    """Real microphones ("near" / the local user's voice)."""
    devices = []
    try:
        wasapi_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    except OSError:
        logger.error("WASAPI host API not available on this system")
        return devices

    default_in_index = wasapi_info.get("defaultInputDevice", -1)

    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info.get("hostApi") != wasapi_info["index"]:
            continue
        if info.get("maxInputChannels", 0) <= 0:
            continue
        if info.get("isLoopbackDevice"):
            continue  # loopback "input" devices belong in list_loopback_devices
        name = info["name"]
        if i == default_in_index:
            name = f"{name}  (default microphone)"
        devices.append(
            AudioDevice(
                index=i,
                name=name,
                sample_rate=int(info["defaultSampleRate"]),
                channels=int(info["maxInputChannels"]),
                is_loopback=False,
            )
        )
    return devices


class Recorder:
    """Continuously reads native-format PCM16 frames from a device on a
    background thread and hands raw chunks to `on_frames(raw_bytes)`.
    """

    def __init__(self, pa: pyaudio.PyAudio, device: AudioDevice, on_frames, on_error=None):
        self.pa = pa
        self.device = device
        self.on_frames = on_frames
        self.on_error = on_error
        self._stream = None
        self._thread: threading.Thread | None = None
        self._running = threading.Event()

    def start(self):
        if self._running.is_set():
            return
        self._stream = self.pa.open(
            format=pyaudio.paInt16,
            channels=self.device.channels,
            rate=self.device.sample_rate,
            input=True,
            input_device_index=self.device.index,
            frames_per_buffer=FRAMES_PER_READ,
        )
        self._running.set()
        self._thread = threading.Thread(target=self._loop, name=f"Recorder-{self.device.name}", daemon=True)
        self._thread.start()

    def _loop(self):
        while self._running.is_set():
            try:
                data = self._stream.read(FRAMES_PER_READ, exception_on_overflow=False)
                self.on_frames(data)
            except Exception as e:
                logger.exception(f"Recorder error on {self.device.name}: {e}")
                if self.on_error:
                    self.on_error(str(e))
                break

    def stop(self):
        self._running.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


class DualRecorder:
    """Owns the shared PyAudio instance and both Recorder pipelines."""

    def __init__(self):
        self.pa = pyaudio.PyAudio()
        self.far_recorder: Recorder | None = None
        self.near_recorder: Recorder | None = None

    def loopback_devices(self) -> list[AudioDevice]:
        return list_loopback_devices(self.pa)

    def input_devices(self) -> list[AudioDevice]:
        return list_input_devices(self.pa)

    def start(self, far_device: AudioDevice, near_device: AudioDevice, on_far_frames, on_near_frames, on_error=None):
        self.far_recorder = Recorder(self.pa, far_device, on_far_frames, on_error)
        self.near_recorder = Recorder(self.pa, near_device, on_near_frames, on_error)
        self.far_recorder.start()
        self.near_recorder.start()

    def stop(self):
        if self.far_recorder:
            self.far_recorder.stop()
            self.far_recorder = None
        if self.near_recorder:
            self.near_recorder.stop()
            self.near_recorder = None

    def terminate(self):
        self.stop()
        try:
            self.pa.terminate()
        except Exception:
            pass
