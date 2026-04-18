"""
Persists the last START payload to disk so the node can resume
after a reconnect without needing a new START from the server.
"""
import json
import os

_STATE_FILE = "node_state.json"


def save(match_id: str, t0: float, agentname: str, schedule: list[dict]) -> None:
    with open(_STATE_FILE, "w") as f:
        json.dump({"match_id": match_id, "t0": t0, "agentname": agentname, "schedule": schedule}, f)


def load() -> dict | None:
    if not os.path.exists(_STATE_FILE):
        return None
    with open(_STATE_FILE) as f:
        return json.load(f)


def clear() -> None:
    if os.path.exists(_STATE_FILE):
        os.unlink(_STATE_FILE)
