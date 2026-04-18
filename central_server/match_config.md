# Example Match Configuration

A 3-hour match with 3 nodes (claude, codex, cline) each receiving 6 prompts
spaced 30 minutes apart. Prompts escalate in complexity over the match duration.

---

## curl Command

```bash
curl -X POST http://localhost:8080/match \
  -H "Content-Type: application/json" \
  -d '{
    "duration_s": 10800,
    "token_weight": 0.01,
    "idle_penalty": 1.0,
    "nodes": [
      {
        "node_id": "node-1",
        "agentname": "claude",
        "schedule": [
          { "delay": 0,    "prompt": "Write a REST API in Python with a single /health endpoint that returns {status: ok}" },
          { "delay": 1800, "prompt": "Add a /users endpoint that supports GET and POST with in-memory storage" },
          { "delay": 3600, "prompt": "Add input validation and return proper HTTP error codes for bad requests" },
          { "delay": 5400, "prompt": "Add a /users/{id} endpoint supporting GET, PUT, and DELETE" },
          { "delay": 7200, "prompt": "Write a full test suite covering all endpoints including edge cases" },
          { "delay": 9000, "prompt": "Add rate limiting: max 10 requests per minute per IP, return 429 when exceeded" }
        ]
      },
      {
        "node_id": "node-2",
        "agentname": "codex",
        "schedule": [
          { "delay": 0,    "prompt": "Write a REST API in Python with a single /health endpoint that returns {status: ok}" },
          { "delay": 1800, "prompt": "Add a /users endpoint that supports GET and POST with in-memory storage" },
          { "delay": 3600, "prompt": "Add input validation and return proper HTTP error codes for bad requests" },
          { "delay": 5400, "prompt": "Add a /users/{id} endpoint supporting GET, PUT, and DELETE" },
          { "delay": 7200, "prompt": "Write a full test suite covering all endpoints including edge cases" },
          { "delay": 9000, "prompt": "Add rate limiting: max 10 requests per minute per IP, return 429 when exceeded" }
        ]
      },
      {
        "node_id": "node-3",
        "agentname": "cline",
        "schedule": [
          { "delay": 0,    "prompt": "Write a REST API in Python with a single /health endpoint that returns {status: ok}" },
          { "delay": 1800, "prompt": "Add a /users endpoint that supports GET and POST with in-memory storage" },
          { "delay": 3600, "prompt": "Add input validation and return proper HTTP error codes for bad requests" },
          { "delay": 5400, "prompt": "Add a /users/{id} endpoint supporting GET, PUT, and DELETE" },
          { "delay": 7200, "prompt": "Write a full test suite covering all endpoints including edge cases" },
          { "delay": 9000, "prompt": "Add rate limiting: max 10 requests per minute per IP, return 429 when exceeded" }
        ]
      }
    ]
  }'
```

---

## Schedule Breakdown

| Prompt | Time | Task |
|---|---|---|
| 1 | 0:00 | Health endpoint |
| 2 | 0:30 | Users CRUD (in-memory) |
| 3 | 1:00 | Input validation + error codes |
| 4 | 1:30 | Per-user GET, PUT, DELETE |
| 5 | 2:00 | Full test suite |
| 6 | 2:30 | Rate limiting |

Match ends automatically at **3:00:00**.

---

## Notes

- All three nodes receive identical prompts at identical times (symmetric match)
- For an asymmetric match, give each node a different `schedule`
- `delay` is in seconds relative to `t0` (match start)
- `duration_s: 10800` = 3 hours
- Prompts are encrypted in transit — competitors cannot read upcoming tasks
