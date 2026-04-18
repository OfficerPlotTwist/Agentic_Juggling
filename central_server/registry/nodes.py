from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time


class NodeState(Enum):
    CONNECTED = "connected"
    READY = "ready"
    RUNNING = "running"
    DISCONNECTED = "disconnected"


@dataclass
class NodeRecord:
    node_id: str
    hostname: str
    ip: str
    state: NodeState = NodeState.CONNECTED
    zmq_identity: Optional[bytes] = None
    connected_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)


class NodeRegistry:
    def __init__(self, allowed_tokens: dict[str, str]):
        # allowed_tokens: { node_id -> preshared_token }
        self._allowed_tokens = allowed_tokens
        self._nodes: dict[str, NodeRecord] = {}

    def authenticate(self, node_id: str, token: str) -> bool:
        expected = self._allowed_tokens.get(node_id)
        return expected is not None and expected == token

    def register(self, node_id: str, hostname: str, ip: str, zmq_identity: bytes) -> tuple[NodeRecord, bool]:
        """Returns (record, is_reconnect)."""
        is_reconnect = node_id in self._nodes
        if is_reconnect:
            node = self._nodes[node_id]
            node.hostname = hostname
            node.ip = ip
            node.zmq_identity = zmq_identity
            node.last_seen = time.time()
            node.state = NodeState.CONNECTED
        else:
            node = NodeRecord(
                node_id=node_id,
                hostname=hostname,
                ip=ip,
                zmq_identity=zmq_identity,
            )
            self._nodes[node_id] = node
        return node, is_reconnect

    def update_state(self, node_id: str, state: NodeState) -> None:
        if node_id in self._nodes:
            self._nodes[node_id].state = state
            self._nodes[node_id].last_seen = time.time()

    def touch(self, node_id: str) -> None:
        if node_id in self._nodes:
            self._nodes[node_id].last_seen = time.time()

    def get(self, node_id: str) -> Optional[NodeRecord]:
        return self._nodes.get(node_id)

    def all_in_state(self, state: NodeState) -> list[NodeRecord]:
        return [n for n in self._nodes.values() if n.state == state]

    def all_connected(self) -> list[NodeRecord]:
        return [n for n in self._nodes.values() if n.state != NodeState.DISCONNECTED]

    def identity_for(self, node_id: str) -> Optional[bytes]:
        node = self._nodes.get(node_id)
        return node.zmq_identity if node else None
