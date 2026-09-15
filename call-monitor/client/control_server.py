"""Local HTTP control API, so the GG web page can show and drive this client.

    GET  /state?since=N     everything the window shows, plus log lines with id > N
    POST /start             {"server_url"?, "far_device"?, "near_device"?, "chunk_seconds"?}
    POST /stop
    POST /auto_detect       {"enabled", "process_names"?, "require_speaker"?}
    POST /scan              list processes holding mic/speaker sessions (into the log)
    POST /refresh_devices

Commands are handed to the Tk thread through `submit` and run exactly as the
window's own buttons do, so the window and the web page never disagree.

This API can start recording the microphone, so it only listens on 127.0.0.1
and only answers pages served from localhost: a request carrying any other
Origin (another website open in the same browser) or any other Host header
(DNS rebinding) is refused. Extra origins can be allowed with
CLIENT_CONTROL_ORIGINS=http://host:port,... Standard library only.
"""

import json
import logging
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("control_server")

CONTROL_HOST = os.getenv("CLIENT_CONTROL_HOST", "127.0.0.1")
CONTROL_PORT = int(os.getenv("CLIENT_CONTROL_PORT", "8001"))
EXTRA_ORIGINS = {o.strip().rstrip("/") for o in os.getenv("CLIENT_CONTROL_ORIGINS", "").split(",") if o.strip()}

COMMANDS = {"start", "stop", "auto_detect", "scan", "refresh_devices"}
MAX_BODY_BYTES = 16_384

_LOCAL_ORIGIN = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$")
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}


def origin_allowed(origin: str | None) -> bool:
    # No Origin header: not a cross-site browser request (curl, scripts).
    return origin is None or bool(_LOCAL_ORIGIN.match(origin)) or origin in EXTRA_ORIGINS


def host_allowed(host: str | None) -> bool:
    if not host:
        return False
    name = re.match(r"^(\[[^\]]+\]|[^:]+)", host)
    return bool(name) and name.group(1).lower() in _LOCAL_HOSTS


class _Handler(BaseHTTPRequestHandler):
    server_version = "CaptureClientControl/1"

    def log_message(self, fmt, *args):  # keep per-request lines out of the console
        logger.debug(fmt, *args)

    # -- helpers -------------------------------------------------------------

    def _origin(self) -> str | None:
        return self.headers.get("Origin")

    def _refuse_if_foreign(self) -> bool:
        origin = self._origin()
        if origin_allowed(origin) and host_allowed(self.headers.get("Host")):
            return False
        logger.warning(f"Refused control request from origin={origin!r} host={self.headers.get('Host')!r}")
        self._send(403, {"error": "Only pages served from localhost may control the capture client"}, cors=False)
        return True

    def _send(self, code: int, body: dict | None, cors: bool = True) -> None:
        data = b"" if body is None else json.dumps(body).encode()
        self.send_response(code)
        if body is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        origin = self._origin()
        if cors and origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        if data:
            self.wfile.write(data)

    # -- verbs ---------------------------------------------------------------

    def do_OPTIONS(self):
        if self._refuse_if_foreign():
            return
        self.send_response(204)
        origin = self._origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self._refuse_if_foreign():
            return
        url = urlparse(self.path)
        if url.path != "/state":
            self._send(404, {"error": "Not found"})
            return
        try:
            since = int(parse_qs(url.query).get("since", ["0"])[0])
        except ValueError:
            since = 0
        self._send(200, self.server.get_state(since))

    def do_POST(self):
        if self._refuse_if_foreign():
            return
        command = urlparse(self.path).path.strip("/")
        if command not in COMMANDS:
            self._send(404, {"error": f"Unknown command: {command}"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            self._send(400, {"error": "Bad request body"})
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            payload = None
        if not isinstance(payload, dict):
            self._send(400, {"error": "Body must be a JSON object"})
            return
        self.server.submit(command, payload)
        self._send(202, {"accepted": command})


class ControlServer:
    def __init__(self, get_state: Callable[[int], dict], submit: Callable[[str, dict], None],
                 host: str = CONTROL_HOST, port: int = CONTROL_PORT):
        self.host = host
        self.port = port
        self._get_state = get_state
        self._submit = submit
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        httpd.daemon_threads = True
        httpd.get_state = self._get_state
        httpd.submit = self._submit
        self._httpd = httpd
        self._thread = threading.Thread(target=httpd.serve_forever, name="ControlServer", daemon=True)
        self._thread.start()
        logger.info(f"Web control API listening on {self.url}")

    def stop(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._httpd = None
