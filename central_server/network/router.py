import asyncio
import json
import logging
from typing import Callable, Awaitable

import zmq
import zmq.asyncio

from crypto.session import CryptoManager
from registry.nodes import NodeRegistry, NodeState

logger = logging.getLogger(__name__)

# Inbound message types (Node → Server)
MSG_REGISTER = b"REGISTER"
MSG_METRICS = b"METRICS"
MSG_HOOK = b"HOOK"

# Outbound message types (Server → Node)
MSG_REGISTER_OK = b"REGISTER_OK"
MSG_REGISTER_FAIL = b"REGISTER_FAIL"
MSG_START = b"START"
MSG_STOP = b"STOP"

MetricsHandler = Callable[[str, dict], Awaitable[None]]
HookHandler = Callable[[str, dict], Awaitable[None]]


class ZMQRouter:
    def __init__(
        self,
        registry: NodeRegistry,
        crypto: CryptoManager,
        port: int = 5555,
        on_metrics: MetricsHandler | None = None,
        on_hook: HookHandler | None = None,
    ):
        self._registry = registry
        self._crypto = crypto
        self._port = port
        self._on_metrics = on_metrics
        self._on_hook = on_hook
        self._ctx = zmq.asyncio.Context()
        self._socket: zmq.asyncio.Socket | None = None
        self._running = False

    async def start(self) -> None:
        self._socket = self._ctx.socket(zmq.ROUTER)
        self._socket.bind(f"tcp://*:{self._port}")
        self._running = True
        logger.info("ZMQ ROUTER bound on port %d", self._port)
        asyncio.create_task(self._recv_loop())

    async def stop(self) -> None:
        self._running = False
        if self._socket:
            self._socket.close()
        self._ctx.term()

    async def send(self, node_id: str, msg_type: bytes, payload: dict) -> bool:
        identity = self._registry.identity_for(node_id)
        if identity is None:
            logger.warning("No ZMQ identity for node %s — likely disconnected", node_id)
            return False
        await self._socket.send_multipart([identity, msg_type, json.dumps(payload).encode()])
        return True

    async def broadcast(self, msg_type: bytes, payloads: dict[str, dict]) -> None:
        """Send per-node payloads to all connected nodes. payloads keyed by node_id."""
        tasks = [self.send(nid, msg_type, payload) for nid, payload in payloads.items()]
        await asyncio.gather(*tasks)

    # ── recv loop ──────────────────────────────────────────────────────────────

    async def _recv_loop(self) -> None:
        while self._running:
            try:
                frames = await self._socket.recv_multipart()
                asyncio.create_task(self._dispatch(frames))
            except zmq.ZMQError as exc:
                if self._running:
                    logger.error("ZMQ recv error: %s", exc)

    async def _dispatch(self, frames: list[bytes]) -> None:
        if len(frames) < 3:
            logger.warning("Malformed message: %d frames", len(frames))
            return

        identity, msg_type, raw = frames[0], frames[1], frames[2]

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Non-JSON payload from identity %r", identity)
            return

        if msg_type == MSG_REGISTER:
            await self._handle_register(identity, payload)
        elif msg_type == MSG_METRICS:
            await self._handle_metrics(payload)
        elif msg_type == MSG_HOOK:
            await self._handle_hook(payload)
        else:
            logger.warning("Unknown msg_type %r", msg_type)

    # ── handlers ───────────────────────────────────────────────────────────────

    async def _handle_register(self, identity: bytes, payload: dict) -> None:
        node_id = payload.get("node_id", "")
        token = payload.get("token", "")
        hostname = payload.get("hostname", "")
        ip = payload.get("ip", "")
        ecdh_pubkey = payload.get("ecdh_pubkey", "")

        if not self._registry.authenticate(node_id, token):
            logger.warning("Auth failed for node_id=%r", node_id)
            await self._socket.send_multipart([
                identity, MSG_REGISTER_FAIL, b'{"reason":"invalid token"}',
            ])
            return

        if not ecdh_pubkey:
            logger.warning("Missing ecdh_pubkey from node %r", node_id)
            await self._socket.send_multipart([
                identity, MSG_REGISTER_FAIL, b'{"reason":"missing ecdh_pubkey"}',
            ])
            return

        prev_state = self._registry.get(node_id)
        was_running = prev_state is not None and prev_state.state == NodeState.RUNNING

        node, is_reconnect = self._registry.register(node_id, hostname, ip, identity)

        # ECDH: derive session key, get server pubkey to return
        server_pubkey_b64 = self._crypto.establish_session(node_id, ecdh_pubkey)

        if not was_running:
            self._registry.update_state(node_id, NodeState.READY)

        logger.info("Node %s registered (reconnect=%s, was_running=%s)", node_id, is_reconnect, was_running)

        await self._socket.send_multipart([
            identity,
            MSG_REGISTER_OK,
            json.dumps({
                "reconnect": is_reconnect,
                "was_running": was_running,
                "server_ecdh_pubkey": server_pubkey_b64,
            }).encode(),
        ])

    async def _handle_metrics(self, payload: dict) -> None:
        node_id = payload.get("node_id", "")
        if not self._registry.get(node_id):
            logger.warning("Metrics from unregistered node %r — dropping", node_id)
            return
        self._registry.touch(node_id)
        if self._on_metrics:
            await self._on_metrics(node_id, payload)

    async def _handle_hook(self, payload: dict) -> None:
        node_id = payload.get("node_id", "")
        if not self._registry.get(node_id):
            logger.warning("Hook from unregistered node %r — dropping", node_id)
            return
        self._registry.touch(node_id)
        if self._on_hook:
            await self._on_hook(node_id, payload)
