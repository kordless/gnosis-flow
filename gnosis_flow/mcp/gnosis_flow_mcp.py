#!/usr/bin/env python3
"""
MCP connector for Gnosis Flow Monitor

Exposes simple tools to control a running gnosis-flow instance via its TCP control server.

Tools:
- gf_status(host, port)
- gf_add_watch(path, host, port)
- gf_add_log(path, host, port)
- gf_stop(host, port)
- gf_rules(host, port)  # returns current rules and basic info

Usage:
  python -m gnosis_flow.mcp.gnosis_flow_mcp

Requires the 'mcp' package (fastmcp server). Install with:
  pip install 'mcp>=0.4.0'
"""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Optional

try:
    from mcp.server.fastmcp import FastMCP, Context
except Exception as e:  # pragma: no cover
    raise SystemExit("Missing dependency: install with `pip install mcp` to run the MCP connector") from e


def _send_control_command(cmd: dict, host: str, port: int, timeout: float = 3.0) -> dict:
    data = (json.dumps(cmd) + "\n").encode()
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(data)
        s.shutdown(socket.SHUT_WR)
        buf = s.recv(65536)
    if not buf:
        return {}
    try:
        return json.loads(buf.decode())
    except Exception:
        return {"raw": buf.decode(errors="ignore")}


def _default_host_port() -> tuple[str, int]:
    host = os.environ.get("GF_HOST", "127.0.0.1")
    port = int(os.environ.get("GF_PORT", "8765"))
    return host, port


mcp = FastMCP("gnosis-flow-mcp")


@mcp.tool()
async def gf_status(host: Optional[str] = None, port: Optional[int] = None) -> dict:
    """Return status from a running gnosis-flow monitor."""
    h, p = _default_host_port()
    if host:
        h = host
    if port:
        p = port
    return _send_control_command({"cmd": "status"}, h, p)


@mcp.tool()
async def gf_add_watch(path: str, host: Optional[str] = None, port: Optional[int] = None) -> dict:
    """Add a directory to the running monitor's watch list."""
    h, p = _default_host_port()
    if host:
        h = host
    if port:
        p = port
    ap = str(Path(path).resolve())
    return _send_control_command({"cmd": "add_watch", "path": ap}, h, p)


@mcp.tool()
async def gf_add_log(path: str, host: Optional[str] = None, port: Optional[int] = None) -> dict:
    """Add a log file to be tailed by the running monitor."""
    h, p = _default_host_port()
    if host:
        h = host
    if port:
        p = port
    ap = str(Path(path).resolve())
    return _send_control_command({"cmd": "add_log", "path": ap}, h, p)


@mcp.tool()
async def gf_stop(host: Optional[str] = None, port: Optional[int] = None) -> dict:
    """Ask the running monitor to stop."""
    h, p = _default_host_port()
    if host:
        h = host
    if port:
        p = port
    return _send_control_command({"cmd": "stop"}, h, p)


@mcp.tool()
async def gf_rules(host: Optional[str] = None, port: Optional[int] = None) -> dict:
    """Return basic rules information by reading the rules.yaml if accessible.

    Looks up .gnosis-flow/rules.yaml under CWD; this is a convenience tool.
    """
    rules_path = Path.cwd() / ".gnosis-flow" / "rules.yaml"
    if not rules_path.exists():
        return {"ok": False, "error": f"Rules not found at {rules_path}"}
    try:
        text = rules_path.read_text(encoding="utf-8")
        return {"ok": True, "path": str(rules_path), "yaml": text}
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    mcp.run()

