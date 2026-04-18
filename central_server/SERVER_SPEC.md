# Central Server — Design Spec

**Author:** Server Agent  
**Source:** `central_server_requirements.md`  
**Date:** 2026-04-17

---

## Role

Orchestrator and scorekeeper for a competitive agentic juggling match. Coordinates N agent-nodes (10–50), dispatches encrypted prompt schedules, ingests performance metrics, computes scores, and serves a live leaderboard.

---

## Stack

| Concern | Choice |
|---|---|
| Language | Python 3.12 + asyncio |
| Transport | ZeroMQ — ROUTER/DEALER pattern |
| API | FastAPI + uvicorn |
| Storage | SQLite via aiosqlite |
| Crypto | `cryptography` lib — X25519 ECDH + AES-256-GCM |

---

## Architecture

```
central_server/
├── main.py                  # asyncio entry point, wires all components
├── config.py                # node tokens, ports, scoring weights from env/file
├── registry/
│   └── nodes.py             # NodeRegistry — PST auth, state tracking, ZMQ identity map
├── network/
│   └── router.py            # ZMQ ROUTER — recv loop, demux, START/STOP dispatch
├── match/
│   ├── store.py             # Versioned match configs in SQLite (replayable)
│   └── manager.py          # State machine: LOBBY → STARTING → RUNNING → FINISHED
├── crypto/
│   └── session.py           # CryptoManager — ECDH session keys, AES-256-GCM prompt encryption
├── metrics/
│   ├── store.py             # Time-series metrics table (node_id, terminal_id, t_rel, ...)
│   └── scoring.py          # Score formula engine
└── api/
    ├── app.py               # FastAPI mount
    ├── admin.py             # Match management REST endpoints
    ├── leaderboard.py      # GET /leaderboard + WS /ws/leaderboard
    └── broadcast.py        # WebSocket connection manager
```

---

## Protocol

| Direction | Socket | Message Types |
|---|---|---|
| Node → Server | ZMQ DEALER → ROUTER | `REGISTER`, `METRICS`, `HOOK` |
| Server → Node | ZMQ ROUTER → DEALER | `REGISTER_OK`, `REGISTER_FAIL`, `START`, `STOP` |
| Browser → Server | HTTP / WebSocket | REST admin, WS leaderboard feed |

### REGISTER payload (Node → Server)
```json
{
  "node_id": "string",
  "hostname": "string",
  "ip": "string",
  "token": "string",
  "ecdh_pubkey": "<base64 X25519 pubkey>"
}
```

### REGISTER_OK payload (Server → Node)
```json
{
  "reconnect": false,
  "was_running": false,
  "server_ecdh_pubkey": "<base64 X25519 pubkey>"
}
```

### START payload (Server → Node)
```json
{
  "match_id": "string",
  "agentname": "claude | codex | cline",
  "t0": 0.0,
  "encrypted_match_key": "<base64 nonce+ciphertext>",
  "schedule": [
    { "delay": 0.0, "encrypted_prompt": "<base64 nonce+ciphertext>" }
  ]
}
```

### METRICS payload (Node → Server)
```json
{
  "node_id": "string",
  "terminal_id": "string",
  "idle_seconds": 0.0,
  "tokens_used": 0,
  "timestamp": 0.0
}
```

---

## Key Hierarchy

```
X25519 ECDH (per node, at registration)
  └─ HKDF-SHA256 → session key (32 bytes, per node)
        └─ AES-256-GCM → wraps match key in START packet

Random AES-256 key (per match, at start)
  └─ AES-256-GCM → encrypts each prompt (unique 12-byte nonce per prompt)
```

Node-side decryption flow:
1. Mirror ECDH with `server_ecdh_pubkey` → derive session key
2. Unwrap `encrypted_match_key` with session key
3. Decrypt each `encrypted_prompt` with match key

Match key is revoked from server memory on match end.

---

## Match Lifecycle

```
LOBBY       — config stored, awaiting node connections
STARTING    — start() called, polling NodeRegistry until all expected nodes READY (timeout: 30s)
RUNNING     — START dispatched, t0 recorded, auto-stop scheduled
FINISHED    — STOP dispatched, match key revoked, replay data persisted
```

Reconnect mid-match: node re-registers → `was_running=True` echoed back → node resumes from its own timer, no new START needed.

---

## Node States

```
CONNECTED → READY → RUNNING → (READY on STOP | DISCONNECTED on drop)
```

---

## Scoring Formula

```
score = (tokens_used × token_weight) − (idle_seconds × idle_penalty)
```

| Parameter | Default | Configurable |
|---|---|---|
| `token_weight` | `0.01` | per match in config |
| `idle_penalty` | `1.0` | per match in config |

No completion bonus. Recomputed on every metric push and broadcast to leaderboard subscribers.

---

## Storage Schema

### matches
```sql
match_id TEXT PRIMARY KEY, version INTEGER, created_at REAL,
duration_s REAL, token_weight REAL, idle_penalty REAL,
state TEXT, t0 REAL, config_json TEXT
```

### metrics
```sql
match_id TEXT, node_id TEXT, terminal_id TEXT,
t_rel REAL, idle_seconds REAL, tokens_used INTEGER
```

### hook_events
```sql
match_id TEXT, node_id TEXT, t_rel REAL,
event_type TEXT, payload_json TEXT
```

All times stored as floats relative to match `t0`, not wall clock.

---

## Build Status

| Phase | Component | Status |
|---|---|---|
| 1 | `registry/nodes.py` | ✅ Complete |
| 1 | `network/router.py` | ✅ Complete |
| 2 | `match/store.py` | ✅ Complete |
| 2 | `match/manager.py` | ✅ Complete |
| 3 | `crypto/session.py` | ✅ Complete |
| 4 | `metrics/store.py` | 🔲 Next |
| 4 | `metrics/scoring.py` | 🔲 Next |
| 5 | `api/admin.py` | 🔲 Pending |
| 5 | `api/leaderboard.py` | 🔲 Pending |
| 6 | `main.py` + `config.py` | 🔲 Pending |

---

## Open Items

- Scoring weight tuning (current defaults are estimates)
- Node auth model confirmed: **Pre-Shared Token (PST)**
- `cognitive_secure.py` produces no output on this Linux environment — Windows VT diagnostic deferred to target machine
