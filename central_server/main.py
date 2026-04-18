import asyncio
import logging

import uvicorn

import config as cfg_module
from api.app import create_app
from api.broadcast import BroadcastManager
from crypto.session import CryptoManager
from match.manager import MatchManager
from match.store import MatchStore
from metrics.ingester import MetricsIngester
from metrics.scoring import ScoringEngine
from metrics.store import MetricsStore
from network.router import ZMQRouter
from registry.nodes import NodeRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    cfg = cfg_module.load()

    if not cfg.node_tokens:
        logger.warning("No node tokens configured — all registrations will be rejected")

    # ── stores ────────────────────────────────────────────────────────────────
    match_store = MatchStore(cfg.db_path)
    metrics_store = MetricsStore(cfg.db_path)
    await match_store.init()
    await metrics_store.init()

    # ── core components ───────────────────────────────────────────────────────
    registry = NodeRegistry(allowed_tokens=cfg.node_tokens)
    crypto = CryptoManager()
    scoring = ScoringEngine(metrics_store)
    broadcaster = BroadcastManager()

    # ── ingester: store metrics → recompute scores → broadcast ───────────────
    ingester = MetricsIngester(
        metrics_store=metrics_store,
        match_store=match_store,
        scoring_engine=scoring,
        score_callback=broadcaster.broadcast,
    )

    # ── network ───────────────────────────────────────────────────────────────
    router = ZMQRouter(
        registry=registry,
        crypto=crypto,
        port=cfg.zmq_port,
        on_metrics=ingester.on_metrics,
        on_hook=ingester.on_hook,
    )

    match_manager = MatchManager(
        store=match_store,
        router=router,
        registry=registry,
        crypto=crypto,
    )

    # ── fastapi ───────────────────────────────────────────────────────────────
    app = create_app(
        match_manager=match_manager,
        match_store=match_store,
        scoring_engine=scoring,
        broadcaster=broadcaster,
    )

    uvicorn_cfg = uvicorn.Config(
        app,
        host=cfg.host,
        port=cfg.http_port,
        loop="none",
        log_level="warning",
    )
    http_server = uvicorn.Server(uvicorn_cfg)

    # ── boot ──────────────────────────────────────────────────────────────────
    logger.info("Starting ZMQ router on port %d", cfg.zmq_port)
    await router.start()

    logger.info("Starting HTTP server on %s:%d", cfg.host, cfg.http_port)
    try:
        await http_server.serve()
    finally:
        logger.info("Shutting down...")
        await router.stop()
        await match_store.close()
        await metrics_store.close()


if __name__ == "__main__":
    asyncio.run(main())
