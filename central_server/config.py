import json
import os
from dataclasses import dataclass, field


@dataclass
class ServerConfig:
    zmq_port: int = 5555
    http_port: int = 8080
    host: str = "0.0.0.0"
    db_path: str = "central_server.db"
    # node_id -> preshared token
    node_tokens: dict[str, str] = field(default_factory=dict)


def load() -> ServerConfig:
    cfg = ServerConfig(
        zmq_port=int(os.getenv("ZMQ_PORT", 5555)),
        http_port=int(os.getenv("HTTP_PORT", 8080)),
        host=os.getenv("HOST", "0.0.0.0"),
        db_path=os.getenv("DB_PATH", "central_server.db"),
    )

    # Node tokens: path to a JSON file mapping node_id -> token
    tokens_path = os.getenv("NODE_TOKENS_FILE", "node_tokens.json")
    if os.path.exists(tokens_path):
        with open(tokens_path) as f:
            cfg.node_tokens = json.load(f)
    else:
        # Fall back to inline env var: NODE_TOKENS='{"node-1":"tok1","node-2":"tok2"}'
        raw = os.getenv("NODE_TOKENS", "{}")
        cfg.node_tokens = json.loads(raw)

    return cfg
