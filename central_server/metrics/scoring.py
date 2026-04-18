from dataclasses import dataclass

from metrics.store import MetricsStore


@dataclass
class NodeScore:
    node_id: str
    tokens_used: int
    idle_seconds: float
    score: float


@dataclass
class Leaderboard:
    match_id: str
    rankings: list[NodeScore]  # sorted descending by score


class ScoringEngine:
    def __init__(self, metrics_store: MetricsStore):
        self._metrics = metrics_store

    async def compute(self, match_id: str, token_weight: float, idle_penalty: float) -> Leaderboard:
        totals = await self._metrics.get_totals_per_node(match_id)

        rankings = sorted(
            [
                NodeScore(
                    node_id=node_id,
                    tokens_used=data["tokens_used"],
                    idle_seconds=data["idle_seconds"],
                    score=round(
                        data["tokens_used"] * token_weight
                        - data["idle_seconds"] * idle_penalty,
                        4,
                    ),
                )
                for node_id, data in totals.items()
            ],
            key=lambda ns: ns.score,
            reverse=True,
        )

        return Leaderboard(match_id=match_id, rankings=rankings)

    def serialize(self, board: Leaderboard) -> dict:
        return {
            "match_id": board.match_id,
            "rankings": [
                {
                    "rank": i + 1,
                    "node_id": ns.node_id,
                    "score": ns.score,
                    "tokens_used": ns.tokens_used,
                    "idle_seconds": ns.idle_seconds,
                }
                for i, ns in enumerate(board.rankings)
            ],
        }
