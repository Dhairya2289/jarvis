"""JARVIS Multi-Machine Control — SSH Bridge

Allows Jarvis to manage other computers on the local network
using Tailscale and paramiko (SSH).
"""
from __future__ import annotations

import logging
from pathlib import Path

_log = logging.getLogger(__name__)


def execute_remote_bash(
    host: str,
    command: str,
    *,
    user: str = "dhairya",
    timeout: int = 10,
) -> str:
    """Run *command* on *host* via SSH."""
    try:
        import paramiko
    except ImportError:
        return "[ERROR] paramiko not installed.  Run: pip install paramiko"

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh_key = Path.home() / ".ssh/id_rsa"
    if not ssh_key.exists():
        ssh_key = Path.home() / ".ssh/id_ed25519"
    if not ssh_key.exists():
        msg = "[ERROR] No SSH key found at ~/.ssh/id_rsa or id_ed25519"
        _log.warning(msg)
        return msg

    try:
        client.connect(
            host,
            username=user,
            key_filename=str(ssh_key),
            timeout=timeout,
        )
        _stdin, stdout, stderr = client.exec_command(command)  # noqa: S602
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        client.close()
        return f"[{host}] OUT: {out}\nERR: {err}"
    except Exception as exc:
        _log.error("SSH to %s failed: %s", host, exc, exc_info=True)
        return f"[ERROR] SSH to {host} failed: {exc}"


def execute_remote_health(host: str) -> str:
    """Fetch basic health stats from a remote machine."""
    cmd = "free -m | awk '/Mem:/ {print $3\"/\"$2\"MB\"}' && uptime -p"
    return execute_remote_bash(host, cmd)


__all__ = ["execute_remote_bash", "execute_remote_health"]
