# Central Server — Setup Instructions

## Requirements

- Python 3.12+
- pip

---

## 1. Install Dependencies

```bash
pip install pyzmq aiosqlite fastapi uvicorn cryptography
```

---

## 2. Configure Node Tokens

Each node that will connect to the server needs a pre-shared token. Create a
`node_tokens.json` file in the `central_server/` directory:

```json
{
  "node-1": "your-secret-token-for-node-1",
  "node-2": "your-secret-token-for-node-2",
  "node-3": "your-secret-token-for-node-3"
}
```

Node IDs must match exactly what each node sends in its REGISTER message.
Tokens should be long random strings — at least 32 characters recommended.

Alternatively, pass tokens inline via environment variable:

```bash
export NODE_TOKENS='{"node-1":"tok1","node-2":"tok2"}'
```

---

## 3. Environment Variables

All settings have defaults and are optional unless noted.

| Variable | Default | Description |
|---|---|---|
| `NODE_TOKENS_FILE` | `node_tokens.json` | Path to node tokens JSON file |
| `NODE_TOKENS` | `{}` | Inline token JSON (fallback if file not found) |
| `ZMQ_PORT` | `5555` | Port nodes connect to over ZMQ |
| `HTTP_PORT` | `8080` | Port for the HTTP/WebSocket API |
| `HOST` | `0.0.0.0` | Bind address |
| `DB_PATH` | `central_server.db` | SQLite database file path |

---

## 4. Run the Server

From the `central_server/` directory:

```bash
cd central_server/
python3 main.py
```

With environment overrides:

```bash
ZMQ_PORT=5555 HTTP_PORT=8080 DB_PATH=/var/data/matches.db python3 main.py
```

The server starts two services:
- **ZMQ ROUTER** on port 5555 — accepts node connections
- **HTTP + WebSocket** on port 8080 — admin API and leaderboard

---

## 5. Create and Run a Match

### Create a match

```bash
curl -X POST http://localhost:8080/match \
  -H "Content-Type: application/json" \
  -d '{
    "duration_s": 300,
    "token_weight": 0.01,
    "idle_penalty": 1.0,
    "nodes": [
      {
        "node_id": "node-1",
        "agentname": "claude",
        "schedule": [
          { "delay": 0.0, "prompt": "Write a hello world program" },
          { "delay": 60.0, "prompt": "Now add error handling" }
        ]
      },
      {
        "node_id": "node-2",
        "agentname": "codex",
        "schedule": [
          { "delay": 0.0, "prompt": "Write a fibonacci function" },
          { "delay": 60.0, "prompt": "Optimise it with memoization" }
        ]
      }
    ]
  }'
```

Response:
```json
{ "match_id": "abc-123", "state": "LOBBY" }
```

### Start the match

Ensure all nodes are connected and ready first, then:

```bash
curl -X POST http://localhost:8080/match/abc-123/start
```

### Stop the match manually

```bash
curl -X POST http://localhost:8080/match/abc-123/stop
```

The match also stops automatically when `duration_s` elapses.

---

## 6. View the Leaderboard

### Snapshot (HTTP)

```bash
curl http://localhost:8080/leaderboard/abc-123
```

### Live feed (WebSocket)

Connect to:
```
ws://localhost:8080/ws/leaderboard/abc-123
```

The server sends an immediate snapshot on connect, then pushes an updated
leaderboard every time a node reports new metrics.

Example message:
```json
{
  "match_id": "abc-123",
  "rankings": [
    { "rank": 1, "node_id": "node-1", "score": 8.2, "tokens_used": 900, "idle_seconds": 0.8 },
    { "rank": 2, "node_id": "node-2", "score": -7.2, "tokens_used": 180, "idle_seconds": 9.0 }
  ]
}
```

---

## 7. Other API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/match` | List all matches |
| `GET` | `/match/{id}` | Get match details |
| `GET` | `/docs` | Interactive API docs (Swagger UI) |

---

## 8. Node Registration (for node developers)

Nodes must connect to the server's ZMQ ROUTER socket and send a REGISTER
message before a match can start.

**Frame format:** `[REGISTER][payload_json]`

**Payload:**
```json
{
  "node_id": "node-1",
  "hostname": "my-machine",
  "ip": "192.168.1.10",
  "token": "your-secret-token-for-node-1",
  "ecdh_pubkey": "<base64-encoded X25519 public key>"
}
```

The server responds with `REGISTER_OK` containing a `server_ecdh_pubkey`.
The node uses this to derive a shared session key via X25519 ECDH + HKDF-SHA256.

When the match starts, the node receives a `START` message containing:
- `encrypted_match_key` — the match AES-256-GCM key, wrapped with the session key
- `schedule` — list of `{ delay, encrypted_prompt }` entries

The node decrypts each prompt using the match key and fires them at `t0 + delay`.

---

## 9. Scoring Formula

```
score = (tokens_used × token_weight) − (idle_seconds × idle_penalty)
```

Default weights: `token_weight = 0.01`, `idle_penalty = 1.0`

These are configurable per match in the create request.

---

## 10. File Layout

```
central_server/
├── main.py          — entry point
├── config.py        — configuration loader
├── node_tokens.json — node PST tokens (create this yourself)
├── registry/        — node state tracking
├── network/         — ZMQ transport
├── match/           — match lifecycle and storage
├── crypto/          — ECDH key exchange and AES-GCM encryption
├── metrics/         — ingestion, storage, scoring
├── api/             — HTTP and WebSocket API
├── SERVER_SPEC.md   — full architecture spec
└── SETUP.md         — this file
```
