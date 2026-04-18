import json
import os
import socket
from dataclasses import dataclass


@dataclass
class Config:
    node_id: str
    token: str
    server_host: str
    server_port: int
    metrics_interval: float
    agent: str  # "claude" | "codex" | "cline"


def load(path: str = "node_config.json") -> Config:
    with open(path) as f:
        d = json.load(f)
    return Config(
        node_id=os.environ.get("NODE_ID", d["node_id"]),
        token=os.environ.get("NODE_TOKEN", d["token"]),
        server_host=os.environ.get("SERVER_HOST", d.get("server_host", "127.0.0.1")),
        server_port=int(os.environ.get("SERVER_PORT", d.get("server_port", 5555))),
        metrics_interval=float(d.get("metrics_interval", 5.0)),
        agent=d.get("agent", "claude"),
    )


def default_node_id() -> str:
    return socket.gethostname()
