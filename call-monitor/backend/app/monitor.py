"""The /ws/monitor endpoint: a read-only live feed for dashboards.

/ws/audio answers only the socket that sent the audio (the desktop capture
client), so a browser UI has no way to see its verdicts. This hub fans every
session event out to any number of watchers instead:

    {"type": "hello", "health": {...}, "active": [...]}   on connect
    {"type": "session_start", "session_id", "source", "started_at", "detector"}
    {"type": "verdict", ...}                              VerdictMessage, unchanged
    {"type": "session_summary", ...}                      SessionSummaryMessage, unchanged

A watcher that connects mid-call gets the active session and its verdicts so
far in `hello`, so a page refresh doesn't reset the risk meter to zero.
Watchers never send anything; a slow or dead one is dropped, never waited on.
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app import config

logger = logging.getLogger("monitor")
router = APIRouter()

# Verdicts replayed to a late joiner, per session. A long call produces one
# window per ~4 s of speech, so this covers the better part of an hour.
_REPLAY_LIMIT = 500
_SEND_TIMEOUT_S = 2.0


class MonitorHub:
    def __init__(self):
        self.watchers: set[WebSocket] = set()
        # session_id -> {"start": dict, "verdicts": [dict]}
        self.active: dict[str, dict] = {}

    async def publish(self, message: dict | str) -> None:
        text = message if isinstance(message, str) else json.dumps(message)
        data = json.loads(text) if isinstance(message, str) else message
        self._remember(data)
        if not self.watchers:
            return
        watchers = list(self.watchers)
        results = await asyncio.gather(
            *(asyncio.wait_for(ws.send_text(text), _SEND_TIMEOUT_S) for ws in watchers),
            return_exceptions=True,
        )
        for ws, result in zip(watchers, results):
            if isinstance(result, BaseException):
                self.watchers.discard(ws)

    def _remember(self, data: dict) -> None:
        kind, session_id = data.get("type"), data.get("session_id")
        if kind == "session_start":
            self.active[session_id] = {"start": data, "verdicts": []}
        elif kind == "verdict" and session_id in self.active:
            verdicts = self.active[session_id]["verdicts"]
            verdicts.append(data)
            del verdicts[:-_REPLAY_LIMIT]
        elif kind == "session_summary":
            self.active.pop(session_id, None)

    def snapshot(self) -> list[dict]:
        return [{"session": s["start"], "verdicts": s["verdicts"]} for s in self.active.values()]


HUB = MonitorHub()


@router.websocket("/ws/monitor")
async def websocket_monitor_endpoint(websocket: WebSocket):
    if config.AUTH_TOKEN and websocket.query_params.get("token") != config.AUTH_TOKEN:
        # Browsers can't set headers on a WebSocket, so the token comes as ?token=.
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return

    await websocket.accept()
    # Imported here: main imports this module, and health lives in main.
    from app.main import health_check

    health = await health_check()
    await websocket.send_text(json.dumps({
        "type": "hello",
        "health": health.model_dump(),
        "active": HUB.snapshot(),
    }))
    HUB.watchers.add(websocket)
    logger.info(f"Monitor connected: {websocket.client} ({len(HUB.watchers)} watching)")

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    finally:
        HUB.watchers.discard(websocket)
        logger.info(f"Monitor disconnected: {websocket.client} ({len(HUB.watchers)} watching)")
