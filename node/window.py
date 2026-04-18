"""
Each AgentWindow spawns an xterm that runs agent_runner.py.
The prompt is delivered via a Unix domain socket so it never appears
in process args, env vars, or terminal scrollback before fire time.
"""
import asyncio
import json
import logging
import os
import socket
import tempfile

logger = logging.getLogger(__name__)

# terminal_id -> AgentWindow
_registry: dict[str, "AgentWindow"] = {}


class AgentWindow:
    def __init__(self, terminal_id: str, agentname: str):
        self.terminal_id = terminal_id
        self.agentname = agentname
        self._sock_path: str | None = None
        self._server_sock: socket.socket | None = None
        self._xterm_proc: asyncio.subprocess.Process | None = None
        # metrics received from agent_runner over the socket
        self.idle_seconds: float = 0.0
        self.tokens_used: int = 0

    async def open(self, prompt: str) -> None:
        self._sock_path = tempfile.mktemp(prefix="aj_", suffix=".sock")
        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sock.bind(self._sock_path)
        self._server_sock.listen(1)
        self._server_sock.setblocking(False)

        runner = os.path.join(os.path.dirname(__file__), "agent_runner.py")
        self._xterm_proc = await asyncio.create_subprocess_exec(
            "xterm",
            "-T", f"agent:{self.terminal_id}",
            "-e", "python3", runner,
            self._sock_path, self.agentname, self.terminal_id,
        )

        _registry[self.terminal_id] = self
        asyncio.create_task(self._deliver_prompt_and_collect(prompt))
        logger.info("Opened window terminal_id=%s agent=%s", self.terminal_id, self.agentname)

    async def close(self) -> None:
        if self._xterm_proc and self._xterm_proc.returncode is None:
            self._xterm_proc.terminate()
        if self._server_sock:
            self._server_sock.close()
        if self._sock_path and os.path.exists(self._sock_path):
            os.unlink(self._sock_path)
        _registry.pop(self.terminal_id, None)

    # ── private ────────────────────────────────────────────────────────────────

    async def _deliver_prompt_and_collect(self, prompt: str) -> None:
        loop = asyncio.get_event_loop()
        try:
            conn, _ = await asyncio.wait_for(
                loop.sock_accept(self._server_sock), timeout=15.0
            )
        except asyncio.TimeoutError:
            logger.error("agent_runner did not connect for terminal %s", self.terminal_id)
            return

        # Delete socket file immediately after connection
        if self._sock_path and os.path.exists(self._sock_path):
            os.unlink(self._sock_path)

        conn.setblocking(False)
        msg = json.dumps({"prompt": prompt}).encode() + b"\n"
        await loop.sock_sendall(conn, msg)

        # Collect metrics updates until agent_runner closes connection
        buf = b""
        while True:
            try:
                chunk = await asyncio.wait_for(loop.sock_recv(conn, 4096), timeout=5.0)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self._apply_metrics(json.loads(line))
            except asyncio.TimeoutError:
                continue
            except (json.JSONDecodeError, ConnectionResetError):
                break

        conn.close()

    def _apply_metrics(self, data: dict) -> None:
        self.idle_seconds = data.get("idle_seconds", self.idle_seconds)
        self.tokens_used = data.get("tokens_used", self.tokens_used)


def all_windows() -> dict[str, AgentWindow]:
    return _registry
