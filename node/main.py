import asyncio
import logging
import sys

import config as cfg
import state
from connection import ServerConnection
from crypto import NodeCrypto
from metrics import MetricsReporter
from scheduler import MatchScheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run(conf: cfg.Config) -> None:
    crypto = NodeCrypto()
    scheduler: MatchScheduler | None = None
    reporter: MetricsReporter | None = None

    async def on_start(payload: dict) -> None:
        nonlocal scheduler, reporter

        match_id = payload["match_id"]
        agentname = payload.get("agentname", conf.agent)
        t0 = payload["t0"]
        encrypted_match_key = payload["encrypted_match_key"]
        schedule = payload["schedule"]

        crypto.unwrap_match_key(match_id, encrypted_match_key)
        state.save(match_id, t0, agentname, schedule)

        scheduler = MatchScheduler(crypto, agentname)
        await scheduler.start(match_id, t0, schedule)

        reporter = MetricsReporter(conn, interval=conf.metrics_interval)
        reporter.start()

        logger.info("Match %s started", match_id)

    async def on_stop() -> None:
        logger.info("STOP received")
        if reporter:
            reporter.stop()
        if scheduler:
            await scheduler.stop()
        state.clear()

    async def resume_if_needed(was_running: bool) -> None:
        if not was_running:
            return
        saved = state.load()
        if not saved:
            logger.warning("was_running=True but no saved state — waiting for fresh START")
            return
        logger.info("Resuming match %s from saved state", saved["match_id"])
        await on_start(saved)

    conn = ServerConnection(
        node_id=conf.node_id,
        token=conf.token,
        crypto=crypto,
        server_host=conf.server_host,
        server_port=conf.server_port,
        on_start=on_start,
        on_stop=on_stop,
    )

    ok, was_running = await conn.connect_and_register()
    if not ok:
        logger.error("Could not register with server — exiting")
        sys.exit(1)

    await resume_if_needed(was_running)
    logger.info("Node %s ready, waiting for START", conf.node_id)

    try:
        await asyncio.Event().wait()  # run until interrupted
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        if reporter:
            reporter.stop()
        if scheduler:
            await scheduler.stop()
        await conn.close()


if __name__ == "__main__":
    conf_path = sys.argv[1] if len(sys.argv) > 1 else "node_config.json"
    try:
        conf = cfg.load(conf_path)
    except FileNotFoundError:
        logger.error("Config file not found: %s", conf_path)
        sys.exit(1)

    asyncio.run(run(conf))
