from dataclasses import dataclass
from typing import Optional

import aiosqlite


@dataclass
class MetricRow:
    match_id: str
    node_id: str
    terminal_id: str
    t_rel: float
    idle_seconds: float
    tokens_used: int


@dataclass
class HookEvent:
    match_id: str
    node_id: str
    t_rel: float
    event_type: str
    payload_json: str


class MetricsStore:
    def __init__(self, db_path: str = "matches.db"):
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id     TEXT NOT NULL,
                node_id      TEXT NOT NULL,
                terminal_id  TEXT NOT NULL,
                t_rel        REAL NOT NULL,
                idle_seconds REAL NOT NULL,
                tokens_used  INTEGER NOT NULL
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_metrics_match_node
            ON metrics (match_id, node_id)
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS hook_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id     TEXT NOT NULL,
                node_id      TEXT NOT NULL,
                t_rel        REAL NOT NULL,
                event_type   TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_hooks_match
            ON hook_events (match_id)
        """)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def insert_metric(self, row: MetricRow) -> None:
        await self._db.execute(
            """INSERT INTO metrics
               (match_id, node_id, terminal_id, t_rel, idle_seconds, tokens_used)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (row.match_id, row.node_id, row.terminal_id,
             row.t_rel, row.idle_seconds, row.tokens_used),
        )
        await self._db.commit()

    async def insert_hook(self, event: HookEvent) -> None:
        await self._db.execute(
            """INSERT INTO hook_events
               (match_id, node_id, t_rel, event_type, payload_json)
               VALUES (?, ?, ?, ?, ?)""",
            (event.match_id, event.node_id, event.t_rel,
             event.event_type, event.payload_json),
        )
        await self._db.commit()

    async def get_metrics_for_match(self, match_id: str) -> list[MetricRow]:
        async with self._db.execute(
            "SELECT * FROM metrics WHERE match_id = ? ORDER BY t_rel ASC",
            (match_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            MetricRow(
                match_id=r["match_id"], node_id=r["node_id"],
                terminal_id=r["terminal_id"], t_rel=r["t_rel"],
                idle_seconds=r["idle_seconds"], tokens_used=r["tokens_used"],
            )
            for r in rows
        ]

    async def get_totals_per_node(self, match_id: str) -> dict[str, dict]:
        """Returns {node_id: {tokens_used, idle_seconds}} aggregated over all terminals."""
        async with self._db.execute(
            """SELECT node_id,
                      SUM(tokens_used)  AS total_tokens,
                      SUM(idle_seconds) AS total_idle
               FROM metrics
               WHERE match_id = ?
               GROUP BY node_id""",
            (match_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return {
            r["node_id"]: {
                "tokens_used": r["total_tokens"] or 0,
                "idle_seconds": r["total_idle"] or 0.0,
            }
            for r in rows
        }

    async def get_hooks_for_match(self, match_id: str) -> list[HookEvent]:
        async with self._db.execute(
            "SELECT * FROM hook_events WHERE match_id = ? ORDER BY t_rel ASC",
            (match_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            HookEvent(
                match_id=r["match_id"], node_id=r["node_id"], t_rel=r["t_rel"],
                event_type=r["event_type"], payload_json=r["payload_json"],
            )
            for r in rows
        ]
