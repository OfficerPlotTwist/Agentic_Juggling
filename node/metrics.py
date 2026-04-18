import asyncio
import logging

from window import all_windows

logger = logging.getLogger(__name__)


class MetricsReporter:
    """
    Periodically reads metrics from all open AgentWindows
    and pushes them to the central server via the connection.
    """

    def __init__(self, connection, interval: float = 5.0):
        self._conn = connection
        self._interval = interval
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            windows = all_windows()
            if not windows:
                continue
            for terminal_id, window in windows.items():
                try:
                    await self._conn.send_metrics(
                        terminal_id=terminal_id,
                        idle_seconds=window.idle_seconds,
                        tokens_used=window.tokens_used,
                    )
                except Exception as exc:
                    logger.warning("Failed to push metrics for %s: %s", terminal_id, exc)
