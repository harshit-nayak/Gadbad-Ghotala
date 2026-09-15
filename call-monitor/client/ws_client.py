"""WebSocket client: session lifecycle + chunk transmission + reconnect,
mirroring the Android app's WebSocketStreamer.kt but trimmed down for a
desktop client talking to a backend on the same LAN/machine.
"""

import json
import logging
import threading
import time
import uuid
from collections import deque
from enum import Enum

import websocket  # websocket-client

from chunker import Chunk

logger = logging.getLogger("ws_client")

MAX_RETRY_QUEUE = 40
BASE_BACKOFF_S = 1.0
MAX_BACKOFF_S = 16.0


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STREAMING = "streaming"
    ERROR = "error"


class StreamerClient:
    def __init__(self, url: str, token: str | None, on_state=None, on_verdict=None,
                 on_ack=None, on_error=None, on_summary=None):
        self.url = url
        self.token = token
        self.on_state = on_state or (lambda s: None)
        self.on_verdict = on_verdict or (lambda v: None)
        self.on_ack = on_ack or (lambda a: None)
        self.on_error = on_error or (lambda e: None)
        self.on_summary = on_summary or (lambda s: None)

        self.session_id = str(uuid.uuid4())
        self._ws: websocket.WebSocketApp | None = None
        self._ws_thread: threading.Thread | None = None
        self._send_lock = threading.Lock()
        self._pending = deque(maxlen=MAX_RETRY_QUEUE)  # (metadata_json, payload_bytes)

        self._should_run = False
        self._reconnect_attempts = 0
        self._reconnect_timer: threading.Timer | None = None

        self._state = ConnectionState.DISCONNECTED

    # -- public API -----------------------------------------------------

    def start(self):
        self._should_run = True
        self._reconnect_attempts = 0
        self.session_id = str(uuid.uuid4())
        self._connect()

    def stop(self):
        self._should_run = False
        if self._reconnect_timer:
            self._reconnect_timer.cancel()
            self._reconnect_timer = None
        self._send_session_end()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        self._set_state(ConnectionState.DISCONNECTED)

    def send_chunk(self, chunk: Chunk):
        metadata = {
            "type": "audio_chunk",
            "session_id": self.session_id,
            "track": chunk.track,
            "sequence": chunk.sequence,
            "timestamp": chunk.timestamp_ms,
            "duration_ms": chunk.duration_ms,
            "sample_rate": 16000,
            "channels": 1,
            "encoding": "pcm_s16le",
            "payload_size": len(chunk.payload),
        }
        self._pending.append((json.dumps(metadata), chunk.payload))
        self._flush_pending()

    # -- internals --------------------------------------------------------

    def _set_state(self, state: ConnectionState):
        self._state = state
        self.on_state(state)

    def _connect(self):
        self._set_state(ConnectionState.CONNECTING)
        headers = []
        if self.token:
            headers.append(f"Authorization: Bearer {self.token}")

        self._ws = websocket.WebSocketApp(
            self.url,
            header=headers,
            on_open=self._on_open,
            on_message=self._on_message,
            on_close=self._on_close,
            on_error=self._on_ws_error,
        )
        self._ws_thread = threading.Thread(
            target=self._ws.run_forever,
            kwargs={"ping_interval": 15, "ping_timeout": 10},
            daemon=True,
        )
        self._ws_thread.start()

    def _on_open(self, ws):
        logger.info("WebSocket connected")
        self._reconnect_attempts = 0
        self._set_state(ConnectionState.CONNECTED)
        start_msg = {
            "type": "session_start",
            "session_id": self.session_id,
            "sample_rate": 16000,
            "channels": 1,
            "encoding": "pcm_s16le",
            "source": "whatsapp_desktop",
        }
        with self._send_lock:
            ws.send(json.dumps(start_msg))
        self._flush_pending()

    def _on_message(self, ws, message: str):
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        kind = data.get("type")
        if kind == "chunk_ack":
            self.on_ack(data)
        elif kind == "verdict":
            self.on_verdict(data)
        elif kind == "session_summary":
            self.on_summary(data)
        elif kind == "error":
            self.on_error(data.get("message", "unknown server error"))

    def _on_close(self, ws, code, reason):
        logger.info(f"WebSocket closed: {code} {reason}")
        if self._should_run:
            self._schedule_reconnect()
        else:
            self._set_state(ConnectionState.DISCONNECTED)

    def _on_ws_error(self, ws, error):
        logger.error(f"WebSocket error: {error}")
        self.on_error(str(error))
        if not self._should_run:
            self._set_state(ConnectionState.ERROR)

    def _schedule_reconnect(self):
        backoff = min(BASE_BACKOFF_S * (2 ** self._reconnect_attempts), MAX_BACKOFF_S)
        self._reconnect_attempts += 1
        self._set_state(ConnectionState.CONNECTING)
        logger.info(f"Reconnecting in {backoff:.1f}s (attempt {self._reconnect_attempts})")
        self._reconnect_timer = threading.Timer(backoff, self._connect)
        self._reconnect_timer.daemon = True
        self._reconnect_timer.start()

    def _flush_pending(self):
        if self._state not in (ConnectionState.CONNECTED, ConnectionState.STREAMING):
            return
        ws = self._ws
        if ws is None or ws.sock is None or not ws.sock.connected:
            return
        with self._send_lock:
            while self._pending:
                metadata_json, payload = self._pending[0]
                try:
                    ws.send(metadata_json)
                    ws.send(payload, opcode=websocket.ABNF.OPCODE_BINARY)
                except Exception as e:
                    logger.warning(f"Send failed, will retry: {e}")
                    break
                self._pending.popleft()
                self._set_state(ConnectionState.STREAMING)

    def _send_session_end(self):
        ws = self._ws
        if ws is None or ws.sock is None or not ws.sock.connected:
            return
        try:
            with self._send_lock:
                ws.send(json.dumps({"type": "session_end", "session_id": self.session_id}))
        except Exception:
            pass
