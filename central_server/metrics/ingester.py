import json
import logging
import time
from typing import Callable, Awaitable, Optional

from match.store import MatchStore
from metrics.store import HookEvent, MetricRow, MetricsStore
from metrics.scoring import ScoringEngine

logger = logging.getLogger(__name__)

ScoreCallback = Callable[[str, dict], Awaitable[None]]


class MetricsIngester:
    """
    Implements the on_metrics / on_hook callbacks expected by ZMQRouter.
    Converts raw payloads to t_rel-based rows, persists them, then fires
    an optional score_callback with the recomputed leaderboard so the
    WebSocket broadcast layer can push live updates.
    """

    def __init__(
        self,
        metrics_store: MetricsStore,
        match_store: MatchStore,
        scoring_engine: ScoringEngine,
        score_callback: Optional[ScoreCallback] = None,
    ):
        self._metrics = metrics_store
        self._matches = match_store
        self._scoring = scoring_engine
        self._score_callback = score_callback

    async def on_metrics(self, node_id: str, payload: dict) -> None:
        match_id = payload.get("match_id", "")
        record = await self._matches.get(match_id)
        if record is None or record.t0 is None:
            logger.warning("Metrics for unknown/unstarted match %r — dropping", match_id)
            return

        row = MetricRow(
            match_id=match_id,
            node_id=node_id,
            terminal_id=payload.get("terminal_id", ""),
            t_rel=payload.get("timestamp", time.time()) - record.t0,
            idle_seconds=float(payload.get("idle_seconds", 0.0)),
            tokens_used=int(payload.get("tokens_used", 0)),
        )
        await self._metrics.insert_metric(row)
        logger.debug("Metric stored: node=%s t_rel=%.2f idle=%.1fs tokens=%d",
                     node_id, row.t_rel, row.idle_seconds, row.tokens_used)

        if self._score_callback:
            board = await self._scoring.compute(
                match_id, record.token_weight, record.idle_penalty
            )
            await self._score_callback(match_id, self._scoring.serialize(board))

    async def on_hook(self, node_id: str, payload: dict) -> None:
        match_id = payload.get("match_id", "")
        record = await self._matches.get(match_id)
        if record is None or record.t0 is None:
            logger.warning("Hook for unknown/unstarted match %r — dropping", match_id)
            return

        event = HookEvent(
            match_id=match_id,
            node_id=node_id,
            t_rel=payload.get("timestamp", time.time()) - record.t0,
            event_type=payload.get("event_type", "unknown"),
            payload_json=json.dumps(payload),
        )
        await self._metrics.insert_hook(event)
        logger.info("Hook stored: node=%s type=%s t_rel=%.2f",
                    node_id, event.event_type, event.t_rel)
