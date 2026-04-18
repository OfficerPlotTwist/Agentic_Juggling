# AGENTIC_JUGGLING — Project CLAUDE.md

## What This Is

A competitive multi-agent benchmarking system. A central server orchestrates N agent-nodes (Claude, Codex, Cline) in timed "juggling matches" — dispatching encrypted prompt schedules, ingesting performance metrics, and scoring agents on token throughput vs. idle time.

## Repository Layout

```
AGENTIC_JUGGLING/
├── central_server/          # Python asyncio server — orchestrator & scorekeeper
├── node/                    # Python asyncio client — runs on each competing machine
├── agents/                  # Agent session logs and communication (git repo)
│   └── Code_Integrity_Agent.md
├── agentspeak.md            # Live inter-agent message board (read/append each session)
├── central_server_requirements.md
└── central_server/SERVER_SPEC.md   # Authoritative design spec
```

## Key Roles

| Component | Purpose |
|---|---|
| `central_server/` | ZMQ ROUTER, match lifecycle, crypto, metrics ingestion, FastAPI leaderboard |
| `node/` | ZMQ DEALER, ECDH session, match scheduler, metrics reporter, agent runner |
| `agentspeak.md` | Agent-to-agent comms — check here for pending tasks before starting work |

## Stack

- Python 3.12 + asyncio
- ZeroMQ (pyzmq) — ROUTER/DEALER
- FastAPI + uvicorn — HTTP + WebSocket leaderboard
- SQLite via aiosqlite
- `cryptography` lib — X25519 ECDH + AES-256-GCM

## Central Server Build Status

| Phase | Component | Status |
|---|---|---|
| 1 | `registry/nodes.py`, `network/router.py` | ✅ Complete |
| 2 | `match/store.py`, `match/manager.py` | ✅ Complete |
| 3 | `crypto/session.py` | ✅ Complete |
| 4 | `metrics/store.py`, `metrics/scoring.py` | 🔲 Next |
| 5 | `api/admin.py`, `api/leaderboard.py` | 🔲 Pending |
| 6 | `main.py` + `config.py` wiring | 🔲 Pending |

## Crypto Key Hierarchy

```
X25519 ECDH (per node, at registration)
  └─ HKDF-SHA256 → session key (32 bytes)
        └─ AES-256-GCM → wraps per-match AES-256 key in START packet

Per-match AES-256 key (random, generated at match start)
  └─ AES-256-GCM → encrypts each prompt (unique 12-byte nonce per prompt)
```

Match key is revoked from server memory on match end.

## Scoring Formula

```
score = (tokens_used × token_weight) − (idle_seconds × idle_penalty)
```

Defaults: `token_weight=0.01`, `idle_penalty=1.0`. Recomputed on every metric push.

## Match Lifecycle

```
LOBBY → STARTING → RUNNING → FINISHED
```

Reconnect mid-match: node re-registers → `was_running=True` → node resumes from its own timer.

## Protocol

| Direction | Socket | Message Types |
|---|---|---|
| Node → Server | ZMQ DEALER→ROUTER | `REGISTER`, `METRICS`, `HOOK` |
| Server → Node | ZMQ ROUTER→DEALER | `REGISTER_OK`, `REGISTER_FAIL`, `START`, `STOP` |
| Browser → Server | HTTP/WebSocket | REST admin, WS leaderboard feed |

## Agent Communication

`agentspeak.md` is the shared message board. Agents post status updates and requests there. Always read it at session start and append with agent identity headers:

```
**TO:** <recipient>
**FROM:** <your agent name>
**RE:** <subject>
```

## Working in This Repo

- `agents/` is the git repo (branch: master, main: main)
- `central_server/` and `node/` are source trees tracked via the agents repo
- Full spec: `central_server/SERVER_SPEC.md`
- Requirements: `central_server_requirements.md`
