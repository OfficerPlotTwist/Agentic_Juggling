import asyncio
import json
import logging
import socket
import time
from typing import Callable, Awaitable

import zmq
import zmq.asyncio

from crypto import NodeCrypto

logger = logging.getLogger(__name__)

MSG_REGISTER    = b"REGISTER"
MSG_METRICS     = b"METRICS"
MSG_HOOK        = b"HOOK"
MSG_REGISTER_OK = b"REGISTER_OK"
MSG_REGISTER_FAIL = b"REGISTER_FAIL"
MSG_START       = b"START"
MSG_STOP        = b"STOP"

StartHandler = Callable[[dict], Awaitable[None]]
StopHandler  = Callable[[], Awaitable[None]]


class ServerConnection:
    def __init__(
        self,
        node_id: str,
        token: str,
        crypto: NodeCrypto,
        server_host: str,
        server_port: int,
        on_start: StartHandler | None = None,
        on_stop: StopHandler | None = None,
    ):
        self._node_id = node_id
        self._token = token
        self._crypto = crypto
        self._addr = f"tcp://{server_host}:{server_port}"
        self._on_start = on_start
        self._on_stop = on_stop
        self._ctx = zmq.asyncio.Context()
        self._socket: zmq.asyncio.Socket | None = None
        self._running = False

    async def connect_and_register(self) -> bool:
        self._socket = self._ctx.socket(zmq.DEALER)
        self._socket.connect(self._addr)

        payload = {
            "node_id": self._node_id,
            "token": self._token,
            "hostname": socket.gethostname(),
            "ip": socket.gethostbyname(socket.gethostname()),
            "ecdh_pubkey": self._crypto.pubkey_b64(),
        }
        await self._socket.send_multipart([MSG_REGISTER, json.dumps(payload).encode()])

        try:
            frames = await asyncio.wait_for(self._socket.recv_multipart(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error("Registration timeout")
            return False

        msg_type, raw = frames[0], frames[1]
        response = json.loads(raw)

        if msg_type == MSG_REGISTER_FAIL:
            logger.error("Registration rejected: %s", response.get("reason"))
            return False, False

        if msg_type == MSG_REGISTER_OK:
            self._crypto.derive_session_key(response["server_ecdh_pubkey"])
            logger.info(
                "Registered. reconnect=%s was_running=%s",
                response.get("reconnect"), response.get("was_running"),
            )
            self._running = True
            asyncio.create_task(self._recv_loop())
            return True, response.get("was_running", False)

        logger.error("Unexpected registration response: %r", msg_type)
        return False, False

    async def send_metrics(self, terminal_id: str, idle_seconds: float, tokens_used: int) -> None:
        payload = {
            "node_id": self._node_id,
            "terminal_id": terminal_id,
            "idle_seconds": idle_seconds,
            "tokens_used": tokens_used,
            "timestamp": time.time(),
        }
        await self._socket.send_multipart([MSG_METRICS, json.dumps(payload).encode()])

    async def send_hook(self, event_type: str, data: dict) -> None:
        payload = {"node_id": self._node_id, "event_type": event_type, **data}
        await self._socket.send_multipart([MSG_HOOK, json.dumps(payload).encode()])

    async def close(self) -> None:
        self._running = False
        if self._socket:
            self._socket.close()
        self._ctx.term()

    # ── recv loop ──────────────────────────────────────────────────────────────

    async def _recv_loop(self) -> None:
        while self._running:
            try:
                frames = await self._socket.recv_multipart()
                asyncio.create_task(self._dispatch(frames))
            except zmq.ZMQError as exc:
                if self._running:
                    logger.error("ZMQ error: %s", exc)

    async def _dispatch(self, frames: list[bytes]) -> None:
        if len(frames) < 2:
            return
        msg_type, raw = frames[0], frames[1]
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return

        if msg_type == MSG_START and self._on_start:
            await self._on_start(payload)
        elif msg_type == MSG_STOP and self._on_stop:
            await self._on_stop()
        else:
            logger.warning("Unhandled msg_type: %r", msg_type)
