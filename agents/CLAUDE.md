# agents/ — CLAUDE.md

This directory is the git repo for AGENTIC_JUGGLING agent session logs and communication.

See `../CLAUDE.md` for full project context, build status, protocol spec, and architecture.

## This Directory

- `Code_Integrity_Agent.md` — session log for the Code Integrity Agent (code review, debugging, cross-platform fixes)
- `agentspeak.md` (project root) — live inter-agent message board; read and append each session

## Code Integrity Agent Scope

| In scope | Out of scope |
|---|---|
| `central_server/` code review | ASCII animator tooling |
| `node/` code review | `terminaltexteffects` / Windows VT fixes |
| Crypto correctness | `cognitive_secure.py` / `play.py` |
| Protocol validation | Terminal display concerns |

## Current Pending Work

- Review `crypto/session.py` (Phase 3, now complete) — security review of X25519 ECDH + AES-256-GCM
- Validate encrypted prompt payload wire format vs. node receiver
- Stand by for Phase 4 (`metrics/store.py`, `metrics/scoring.py`) delivery
