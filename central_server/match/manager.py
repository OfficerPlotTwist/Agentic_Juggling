import asyncio
import logging
import time

from crypto.session import CryptoManager
from match.store import MatchConfig, MatchRecord, MatchState, MatchStore, NodeAssignment
from network.router import MSG_START, MSG_STOP, ZMQRouter
from registry.nodes import NodeRegistry, NodeState

logger = logging.getLogger(__name__)

_READY_POLL = 0.5  # seconds between readiness checks


class MatchError(Exception):
    pass


class MatchManager:
    def __init__(self, store: MatchStore, router: ZMQRouter, registry: NodeRegistry, crypto: CryptoManager):
        self._store = store
        self._router = router
        self._registry = registry
        self._crypto = crypto
        self._auto_stop_tasks: dict[str, asyncio.Task] = {}

    async def create(self, config: MatchConfig) -> MatchRecord:
        record = await self._store.create(config)
        logger.info("Match created: %s (%.1fs, %d nodes)", record.match_id, record.duration_s, len(config.nodes))
        return record

    async def start(self, match_id: str, ready_timeout: float = 30.0) -> None:
        record = await self._store.get(match_id)
        if record is None:
            raise MatchError(f"Match {match_id} not found")
        if record.state != MatchState.LOBBY:
            raise MatchError(f"Cannot start match in state {record.state.value}")

        assignments = MatchStore.parse_assignments(record.config_json)
        expected = {na.node_id for na in assignments}

        await self._store.update_state(match_id, MatchState.STARTING)
        logger.info("Match %s: LOBBY → STARTING (awaiting %s)", match_id, expected)

        try:
            await self._await_ready(match_id, expected, ready_timeout)
        except MatchError:
            await self._store.update_state(match_id, MatchState.LOBBY)
            raise

        t0 = time.time()
        await self._store.update_state(match_id, MatchState.RUNNING, t0=t0)
        logger.info("Match %s: STARTING → RUNNING (t0=%.3f)", match_id, t0)

        await self._dispatch_start(match_id, t0, record, assignments)

        task = asyncio.create_task(self._auto_stop(match_id, record.duration_s))
        self._auto_stop_tasks[match_id] = task

    async def stop(self, match_id: str) -> None:
        record = await self._store.get(match_id)
        if record is None:
            raise MatchError(f"Match {match_id} not found")
        if record.state == MatchState.FINISHED:
            return

        # Cancel scheduled auto-stop if this is a manual stop
        task = self._auto_stop_tasks.pop(match_id, None)
        if task:
            task.cancel()

        assignments = MatchStore.parse_assignments(record.config_json)
        for na in assignments:
            sent = await self._router.send(na.node_id, MSG_STOP, {"match_id": match_id})
            if sent:
                self._registry.update_state(na.node_id, NodeState.READY)
                logger.info("STOP sent to node %s", na.node_id)
            else:
                logger.warning("Could not reach node %s for STOP", na.node_id)

        self._crypto.revoke_match_key(match_id)
        await self._store.update_state(match_id, MatchState.FINISHED)
        logger.info("Match %s: → FINISHED", match_id)

    async def get(self, match_id: str) -> MatchRecord:
        record = await self._store.get(match_id)
        if record is None:
            raise MatchError(f"Match {match_id} not found")
        return record

    # ── internals ─────────────────────────────────────────────────────────────

    async def _await_ready(
        self, match_id: str, expected: set[str], timeout: float
    ) -> None:
        deadline = time.monotonic() + timeout
        while True:
            ready = {n.node_id for n in self._registry.all_in_state(NodeState.READY)}
            if expected.issubset(ready):
                return
            if time.monotonic() >= deadline:
                missing = expected - ready
                raise MatchError(f"Ready timeout for match {match_id} — missing nodes: {missing}")
            await asyncio.sleep(_READY_POLL)

    async def _dispatch_start(
        self,
        match_id: str,
        t0: float,
        record: MatchRecord,
        assignments: list[NodeAssignment],
    ) -> None:
        self._crypto.generate_match_key(match_id)

        for na in assignments:
            if not self._crypto.has_session(na.node_id):
                logger.warning("No crypto session for node %s — cannot encrypt START", na.node_id)
                continue

            raw_schedule = [{"delay": p.delay, "prompt": p.prompt} for p in na.schedule]
            encrypted_schedule = self._crypto.encrypt_schedule(match_id, raw_schedule)
            encrypted_match_key = self._crypto.encrypt_match_key_for_node(match_id, na.node_id)

            payload = {
                "match_id": match_id,
                "agentname": na.agentname,
                "t0": t0,
                "encrypted_match_key": encrypted_match_key,
                "schedule": encrypted_schedule,
            }
            sent = await self._router.send(na.node_id, MSG_START, payload)
            if sent:
                self._registry.update_state(na.node_id, NodeState.RUNNING)
                logger.info("START → node %s (%s, %d prompts)", na.node_id, na.agentname, len(na.schedule))
            else:
                logger.warning("START failed for node %s — not reachable", na.node_id)

    async def _auto_stop(self, match_id: str, delay: float) -> None:
        await asyncio.sleep(delay)
        logger.info("Match %s duration elapsed — auto-stopping", match_id)
        try:
            await self.stop(match_id)
        except MatchError as exc:
            logger.error("Auto-stop failed for match %s: %s", match_id, exc)
