# Central Server Requirements

## Role
The central server is the **orchestrator and scorekeeper** for a competitive agentic juggling match. It coordinates multiple agent-nodes, dispatches timed prompt sequences, and collects performance metrics.

---

## Responsibilities

### 1. Match Configuration
- Define a match: assign `agentname` (claude, codex, cline) per node, compose prompt lists with corresponding float timestamps, set match duration
- Store match configs as versioned records (multiple matches, replayable)

### 2. Start Signal Dispatch
- On match start, broadcast a `START` packet to each registered node over TCP/ZMQ
- Packet schema:
  ```json
  {
    "agentname": "claude | codex | cline",
    "t0": 0.0,
    "schedule": [
      { "delay": 0.0, "prompt": "..." }
    ]
  }
  ```
- Prompts must be **encrypted in transit** (AES-GCM or ChaCha20-Poly1305 with per-match key)
- Each node gets its own prompt schedule (can differ per node for asymmetric matches)

### 3. Node Registry
- Nodes register on connect with `{ node_id, hostname, ip }`
- Server tracks connection state: `connected / ready / running / disconnected`
- Must handle node reconnects mid-match gracefully

### 4. Metrics Ingestion
- Receive periodic metric pushes from each node:
  ```json
  {
    "node_id": "string",
    "terminal_id": "string",
    "idle_seconds": 0.0,
    "tokens_used": 0,
    "timestamp": 0.0
  }
  ```
- Store time-series metrics per node per terminal

### 5. Scoring / Leaderboard
- Compute scores from metrics (formula TBD — likely penalizes idle time, rewards task completion signals)
- Expose a live leaderboard via HTTP endpoint or WebSocket feed

### 6. Hook Signal Receiver
- Nodes send hook events back (agent completed a task, error, etc.)
- Server logs these with timestamps relative to `t0`

### 7. Match Lifecycle
- States: `LOBBY → STARTING → RUNNING → FINISHED`
- Server signals `STOP` to all nodes at match end
- Stores full match replay data

---

## Interface Summary

| Direction | Protocol | Purpose |
|---|---|---|
| Server → Node | TCP/ZMQ PUSH | START, STOP signals |
| Node → Server | TCP/ZMQ PUSH | Metrics, hook events |
| Browser → Server | HTTP/WebSocket | Leaderboard, admin UI |

---

## Non-Functional Requirements
- Handle **N nodes concurrently** (10–50 range assumed)
- Metric push interval: configurable, default 5s
- All times stored as floats relative to match `t0`, not wall clock
- Prompt payloads encrypted; key exchange happens at node registration

---

## Open Questions
- Scoring formula (idle penalty weight, token cost weight, task completion bonus)
- Server stack/language (needed before speccing protocol layer)
- Authentication model for node registration
