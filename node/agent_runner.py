"""
Runs inside xterm. Connects to parent's Unix socket, receives the prompt,
feeds it to the agent via PTY stdin (echo disabled so prompt stays hidden),
then streams metrics back to the parent.
"""
import json
import os
import pty
import re
import socket
import sys
import termios
import time

TOKEN_RE = re.compile(r"(?:tokens?[\s:]+|input[\s:]+)(\d+)", re.IGNORECASE)

AGENT_COMMANDS = {
    "claude": ["claude"],
    "codex":  ["codex"],
    "cline":  ["cline"],
}


def receive_prompt(sock_path: str) -> str:
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.connect(sock_path)
    buf = b""
    while b"\n" not in buf:
        buf += conn.recv(4096)
    data = json.loads(buf.split(b"\n")[0])
    return conn, data["prompt"]


def feed_prompt(master_fd: int, prompt: str) -> None:
    attrs = termios.tcgetattr(master_fd)
    orig = attrs[3]
    attrs[3] &= ~termios.ECHO
    termios.tcsetattr(master_fd, termios.TCSANOW, attrs)
    os.write(master_fd, (prompt + "\n").encode())
    attrs[3] = orig
    termios.tcsetattr(master_fd, termios.TCSANOW, attrs)


def run(sock_path: str, agentname: str, terminal_id: str) -> None:
    conn, prompt = receive_prompt(sock_path)

    cmd = AGENT_COMMANDS.get(agentname, [agentname])
    master_fd, slave_fd = pty.openpty()

    pid = os.fork()
    if pid == 0:
        # child: exec agent with slave as stdin
        os.close(master_fd)
        os.dup2(slave_fd, 0)
        os.close(slave_fd)
        os.execvp(cmd[0], cmd)
        sys.exit(1)

    os.close(slave_fd)
    feed_prompt(master_fd, prompt)

    tokens_used = 0
    last_output = time.time()
    buf = b""

    def push_metrics() -> None:
        idle = time.time() - last_output
        msg = json.dumps({"terminal_id": terminal_id, "idle_seconds": idle, "tokens_used": tokens_used})
        try:
            conn.sendall((msg + "\n").encode())
        except OSError:
            pass

    last_push = time.time()

    while True:
        try:
            chunk = os.read(master_fd, 4096)
        except OSError:
            break

        text = chunk.decode(errors="replace")
        sys.stdout.write(text)
        sys.stdout.flush()
        last_output = time.time()

        for m in TOKEN_RE.finditer(text):
            tokens_used += int(m.group(1))

        if time.time() - last_push >= 5.0:
            push_metrics()
            last_push = time.time()

    push_metrics()
    conn.close()
    os.close(master_fd)
    os.waitpid(pid, 0)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("usage: agent_runner.py <sock_path> <agentname> <terminal_id>")
        sys.exit(1)
    run(sys.argv[1], sys.argv[2], sys.argv[3])
