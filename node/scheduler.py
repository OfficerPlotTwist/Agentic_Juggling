import asyncio
import logging
import time
from typing import Callable, Awaitable

from crypto import NodeCrypto
from window import AgentWindow

logger = logging.getLogger(__name__)

PromptFiredCallback = Callable[[str, str], Awaitable[None]]  # (terminal_id, prompt)


class MatchScheduler:
    """
    Receives an encrypted schedule from the START packet.
    Decrypts each prompt only at fire time and spawns a new AgentWindow.
    """

    def __init__(self, crypto: NodeCrypto, agentname: str):
        self._crypto = crypto
        self._agentname = agentname
        self._tasks: list[asyncio.Task] = []
        self._windows: list[AgentWindow] = []
        self._match_id: str | None = None
        self._t0: float | None = None

    async def start(self, match_id: str, t0: float, schedule: list[dict]) -> None:
        """
        schedule: [{"delay": float, "encrypted_prompt": str}, ...]  sorted by delay.
        t0: unix timestamp of match start (from server).
        """
        self._match_id = match_id
        self._t0 = t0
        now = time.time()
        elapsed = now - t0

        for i, entry in enumerate(schedule):
            delay = entry["delay"]
            encrypted_prompt = entry["encrypted_prompt"]
            terminal_id = f"{match_id}-t{i}"
            wait = max(0.0, delay - elapsed)
            task = asyncio.create_task(
                self._fire(wait, terminal_id, encrypted_prompt)
            )
            self._tasks.append(task)

        logger.info("Scheduled %d prompts for match %s (elapsed=%.1fs)", len(schedule), match_id, elapsed)

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for w in self._windows:
            await w.close()
        if self._match_id:
            self._crypto.revoke_match_key(self._match_id)
        self._tasks.clear()
        self._windows.clear()

    async def _fire(self, wait: float, terminal_id: str, encrypted_prompt: str) -> None:
        if wait > 0:
            await asyncio.sleep(wait)

        # Decrypt only at fire time — plaintext never exists before this moment
        prompt = self._crypto.decrypt_prompt(self._match_id, encrypted_prompt)

        window = AgentWindow(terminal_id, self._agentname)
        self._windows.append(window)
        await window.open(prompt)
        logger.info("Fired terminal %s", terminal_id)
