import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class BroadcastManager:
    def __init__(self):
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, match_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.setdefault(match_id, set()).add(ws)
        logger.info("WS client connected to match %s (%d total)",
                    match_id, len(self._connections[match_id]))

    def disconnect(self, match_id: str, ws: WebSocket) -> None:
        if match_id in self._connections:
            self._connections[match_id].discard(ws)

    async def broadcast(self, match_id: str, data: dict) -> None:
        dead: set[WebSocket] = set()
        for ws in self._connections.get(match_id, set()):
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._connections[match_id].discard(ws)
