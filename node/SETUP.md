# Node — Setup Instructions

The node runs on each competitor's machine. It connects to the central server,
receives the match START signal, decrypts the prompt schedule, and fires each
prompt into a new xterm terminal window at the correct time.

---

## Requirements

- Linux (xterm, PTY, and Unix domain sockets are required)
- Python 3.12+
- `xterm` installed
- At least one agent CLI on PATH: `claude`, `codex`, or `cline`

Install xterm if not present:
```bash
sudo apt install xterm
```

---

## 1. Install Python Dependencies

```bash
pip install pyzmq cryptography
```

---

## 2. Configure the Node

Edit `node_config.json` in the `node/` directory:

```json
{
  "node_id": "node-1",
  "token": "your-secret-token",
  "server_host": "192.168.1.100",
  "server_port": 5555,
  "metrics_interval": 5.0,
  "agent": "claude"
}
```

| Field | Description |
|---|---|
| `node_id` | Unique ID for this node — must match the ID registered on the central server |
| `token` | Pre-shared token — must match the token in the server's `node_tokens.json` |
| `server_host` | IP or hostname of the central server |
| `server_port` | ZMQ port on the central server (default `5555`) |
| `metrics_interval` | How often to push metrics to the server in seconds (default `5.0`) |
| `agent` | Which agent CLI to run: `claude`, `codex`, or `cline` |

All fields except `metrics_interval` can be overridden with environment variables:

| Environment Variable | Overrides |
|---|---|
| `NODE_ID` | `node_id` |
| `NODE_TOKEN` | `token` |
| `SERVER_HOST` | `server_host` |
| `SERVER_PORT` | `server_port` |

---

## 3. Run the Node

From the `node/` directory:

```bash
cd node/
python3 main.py
```

To use a custom config file path:

```bash
python3 main.py /path/to/my_config.json
```

With environment variable overrides:

```bash
SERVER_HOST=192.168.1.100 NODE_TOKEN=mysecret python3 main.py
```

---

## 4. What Happens at Runtime

1. **Registration** — node connects to the central server over ZMQ, sends its
   `node_id`, `token`, and an ephemeral X25519 public key for ECDH key exchange.
   The server responds with its own public key; the node derives a shared session key.

2. **Ready** — node enters the READY state and waits for a START signal.

3. **Match start** — server sends a START packet containing:
   - `t0` — the unix timestamp when the match began
   - `encrypted_match_key` — the match AES-256-GCM key, wrapped with the session key
   - `schedule` — list of `{ delay, encrypted_prompt }` entries

4. **Prompt scheduling** — the node decrypts the match key, then schedules each
   prompt to fire at `t0 + delay`. Prompts are decrypted only at fire time —
   plaintext never exists in memory before it is needed.

5. **Terminal windows** — at each fire time, a new `xterm` window opens running
   the agent CLI. The prompt is delivered via a Unix domain socket directly into
   the agent's PTY stdin with echo disabled. Competitors see the agent working
   but cannot read the prompt before it fires.

6. **Metrics** — every `metrics_interval` seconds, the node reads token counts
   and idle time from each open terminal and pushes them to the central server.

7. **Match end** — server sends STOP. All terminals are closed, the match key
   is revoked from memory, and the node returns to READY.

---

## 5. Reconnect Behaviour

If the node loses connection mid-match and reconnects, it automatically resumes
from saved state (`node_state.json`). Prompt timings are recalculated against
the original `t0` so no prompts are missed or duplicated.

The state file is deleted when the match ends cleanly.

---

## 6. Agent CLI Requirements

The agent specified in `node_config.json` must be installed and runnable as a
bare command. Test before match day:

```bash
# Claude
claude --version

# Codex
codex --version

# Cline
cline --version
```

If the command is not on PATH, add it:
```bash
export PATH="$PATH:/path/to/agent/bin"
```

---

## 7. File Layout

```
node/
├── main.py          — entry point
├── node_config.json — configuration (edit this)
├── config.py        — config loader
├── connection.py    — ZMQ client, registration, recv loop
├── crypto.py        — ECDH key exchange, AES-256-GCM prompt decryption
├── scheduler.py     — fires prompts at t0+delay, spawns AgentWindows
├── window.py        — xterm process manager, Unix socket prompt delivery
├── agent_runner.py  — runs inside xterm, feeds prompt to agent via PTY
├── metrics.py       — periodic metrics push to central server
└── state.py         — persists match state to disk for reconnect resume
```
