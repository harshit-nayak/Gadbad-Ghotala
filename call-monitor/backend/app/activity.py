"""Tracks whether anyone is actually using the detector, for idle auto-stop.

On a server that sleeps between uses (deploy/aws), a watchdog polls
GET /activity and powers the machine off once nothing has been analysed for a
while. "Activity" means only real analysis work -- a live /ws/audio stream or
an /analyse upload in flight. /ws/monitor and /health deliberately don't count:
any open dashboard tab holds a monitor socket and polls health, and that alone
must never keep a paid machine awake.

Pure ASGI middleware rather than FastAPI's @app.middleware("http"), because
the latter never sees WebSocket connections.
"""

import time

from fastapi import APIRouter

WORK_PATHS = ("/ws/audio", "/analyse")

_started = time.time()
_last_activity = _started
_in_flight = 0

router = APIRouter()


class ActivityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        global _last_activity, _in_flight
        if scope["type"] not in ("http", "websocket") or scope.get("path") not in WORK_PATHS:
            await self.app(scope, receive, send)
            return
        _in_flight += 1
        _last_activity = time.time()
        try:
            await self.app(scope, receive, send)
        finally:
            _in_flight -= 1
            _last_activity = time.time()


@router.get("/activity")
async def activity():
    """busy > 0 while a stream or upload is being analysed; idle_seconds since
    the last one ended (or since startup, if there hasn't been one)."""
    now = time.time()
    return {
        "busy": _in_flight,
        "idle_seconds": 0 if _in_flight else round(now - _last_activity),
        "uptime_seconds": round(now - _started),
    }
