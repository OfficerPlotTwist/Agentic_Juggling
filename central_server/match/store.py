import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import aiosqlite


class MatchState(Enum):
    LOBBY = "LOBBY"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"


@dataclass
class PromptEntry:
    delay: float
    prompt: str


@dataclass
class NodeAssignment:
    node_id: str
    agentname: str  # "claude" | "codex" | "cline"
    schedule: list[PromptEntry]


@dataclass
class MatchConfig:
    duration_s: float
    nodes: list[NodeAssignment]
    token_weight: float = 0.01
    idle_penalty: float = 1.0
    match_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: int = 1
    created_at: float = field(default_factory=time.time)


@dataclass
class MatchRecord:
    match_id: str
    version: int
    created_at: float
    duration_s: float
    token_weight: float
    idle_penalty: float
    state: MatchState
    t0: Optional[float]
    config_json: str  # serialized for replay


class MatchStore:
    def __init__(self, db_path: str = "matches.db"):
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                match_id     TEXT PRIMARY KEY,
                version      INTEGER NOT NULL DEFAULT 1,
                created_at   REAL NOT NULL,
                duration_s   REAL NOT NULL,
                token_weight REAL NOT NULL,
                idle_penalty REAL NOT NULL,
                state        TEXT NOT NULL DEFAULT 'LOBBY',
                t0           REAL,
                config_json  TEXT NOT NULL
            )
        """)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def create(self, config: MatchConfig) -> MatchRecord:
        config_json = json.dumps([
            {
                "node_id": na.node_id,
                "agentname": na.agentname,
                "schedule": [{"delay": p.delay, "prompt": p.prompt} for p in na.schedule],
            }
            for na in config.nodes
        ])
        record = MatchRecord(
            match_id=config.match_id,
            version=config.version,
            created_at=config.created_at,
            duration_s=config.duration_s,
            token_weight=config.token_weight,
            idle_penalty=config.idle_penalty,
            state=MatchState.LOBBY,
            t0=None,
            config_json=config_json,
        )
        await self._db.execute(
            """INSERT INTO matches
               (match_id, version, created_at, duration_s, token_weight, idle_penalty, state, t0, config_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record.match_id, record.version, record.created_at, record.duration_s,
             record.token_weight, record.idle_penalty, record.state.value,
             record.t0, record.config_json),
        )
        await self._db.commit()
        return record

    async def get(self, match_id: str) -> Optional[MatchRecord]:
        async with self._db.execute(
            "SELECT * FROM matches WHERE match_id = ?", (match_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_record(row)

    async def list_all(self) -> list[MatchRecord]:
        async with self._db.execute(
            "SELECT * FROM matches ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_record(r) for r in rows]

    async def update_state(
        self, match_id: str, state: MatchState, t0: Optional[float] = None
    ) -> None:
        if t0 is not None:
            await self._db.execute(
                "UPDATE matches SET state = ?, t0 = ? WHERE match_id = ?",
                (state.value, t0, match_id),
            )
        else:
            await self._db.execute(
                "UPDATE matches SET state = ? WHERE match_id = ?",
                (state.value, match_id),
            )
        await self._db.commit()

    @staticmethod
    def parse_assignments(config_json: str) -> list[NodeAssignment]:
        return [
            NodeAssignment(
                node_id=na["node_id"],
                agentname=na["agentname"],
                schedule=[PromptEntry(**p) for p in na["schedule"]],
            )
            for na in json.loads(config_json)
        ]

    @staticmethod
    def _row_to_record(row: aiosqlite.Row) -> MatchRecord:
        return MatchRecord(
            match_id=row["match_id"],
            version=row["version"],
            created_at=row["created_at"],
            duration_s=row["duration_s"],
            token_weight=row["token_weight"],
            idle_penalty=row["idle_penalty"],
            state=MatchState(row["state"]),
            t0=row["t0"],
            config_json=row["config_json"],
        )
