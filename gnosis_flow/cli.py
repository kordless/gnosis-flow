import asyncio
import json
import os
import socket
from pathlib import Path
from typing import Optional
import sys

import typer


app = typer.Typer(help="Gnosis Flow Monitor: async file/log watcher with triggerable actions")
tools_app = typer.Typer(help="Inspect in-process tools (schemas, categories)")
app.add_typer(tools_app, name="tools")


def _send_control_command(cmd: dict, host: str = "127.0.0.1", port: int = 8765, timeout: float = 3.0) -> dict:
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


@app.command()
def start(
    dir: Optional[str] = typer.Option(None, "--dir", help="Project directory to run in (defaults to CWD)", metavar="PATH"),
    log: Optional[str] = typer.Option(None, "--log", help="Log file to tail (can pass multiple)", metavar="FILE"),
    host: str = typer.Option("127.0.0.1", help="Control server host"),
    port: int = typer.Option(8765, help="Control server port"),
    poll: float = typer.Option(1.0, help="Polling interval in seconds"),
    daemon: bool = typer.Option(False, "--daemon", help="Run in background and log to .gnosis-flow/monitor.log"),
    http: bool = typer.Option(False, "--http", help="Expose a simple HTTP status endpoint on /status"),
    http_port: int = typer.Option(8766, "--http-port", help="HTTP status port when --http is enabled"),
    yes: bool = typer.Option(False, "--yes", help="Auto-confirm prompts like adding .gnosis-flow to .gitignore"),
):
    """Run the monitor in single-project mode.

    - Creates a `.gnosis-flow/` directory under the project root.
    - Offers to add `.gnosis-flow` to `.gitignore` if a Git repo is detected.
    - Starts the control server and watchers; can daemonize with `--daemon`.
    """
    from .runtime import run_monitor, daemonize
    from .util import project_root_from_cwd, ensure_state_dir, is_git_repo, add_to_gitignore, is_in_gitignore

    project = Path(dir).resolve() if dir else project_root_from_cwd()
    state = ensure_state_dir(project)

    if is_git_repo(project):
        entry = ".gnosis-flow"
        gi = project / ".gitignore"
        if is_in_gitignore(project, entry):
            typer.echo(f"{entry} already present in {gi}")
        else:
            # Offer to add to .gitignore
            if yes or typer.confirm(f"Add '{entry}' to {gi}?"):
                if add_to_gitignore(project, entry):
                    typer.echo(f"Added {entry} to {gi}")

    initial_dirs = [str(project)]
    if log:
        initial_logs = [l.strip() for l in (log if isinstance(log, list) else [log])]
    else:
        initial_logs = []

    if daemon:
        log_file = state / "monitor.log"
        typer.echo(f"Starting daemon, logging to {log_file}")
        daemonize()
        # In child: continue to run monitor and redirect output
        sys.stdout = open(log_file, "a", buffering=1)
        sys.stderr = open(log_file, "a", buffering=1)

    asyncio.run(
        run_monitor(
            initial_dirs=initial_dirs,
            initial_logs=initial_logs,
            host=host,
            port=port,
            poll_interval=poll,
            state_dir=str(state),
            http_enabled=http,
            http_port=http_port,
        )
    )


@app.command("add-log")
def add_log(path: str, host: str = "127.0.0.1", port: int = 8765):
    """Add a log file to tail in the running monitor."""
    resp = _send_control_command({"cmd": "add_log", "path": os.path.abspath(path)}, host, port)
    typer.echo(json.dumps(resp, indent=2))


@app.command("add-watch")
def add_watch(path: str, host: str = "127.0.0.1", port: int = 8765):
    """Add a directory to watch for file changes in the running monitor."""
    resp = _send_control_command({"cmd": "add_watch", "path": os.path.abspath(path)}, host, port)
    typer.echo(json.dumps(resp, indent=2))


@app.command()
def status(host: str = "127.0.0.1", port: int = 8765):
    """Get current monitor status: watched dirs/logs and stats."""
    resp = _send_control_command({"cmd": "status"}, host, port)
    typer.echo(json.dumps(resp, indent=2))


@app.command()
def stop(host: str = "127.0.0.1", port: int = 8765):
    """Ask the running monitor to stop gracefully."""
    resp = _send_control_command({"cmd": "stop"}, host, port)
    typer.echo(json.dumps(resp, indent=2))


if __name__ == "__main__":
    app()


def main():
    """Entry point for console_scripts."""
    app()


@tools_app.command("list")
def tools_list():
    """List available tools with name, description, and category."""
    try:
        from .ahp_compat import get_global_registry
        reg = get_global_registry()
        rows = []
        for schema in reg.get_schemas():
            name = schema.get("name")
            cat = None
            # find category from registry internal map (best-effort)
            for c, names in getattr(reg, "categories", {}).items():
                if name in names:
                    cat = c
                    break
            rows.append({"name": name, "description": schema.get("description", ""), "category": cat or "general"})
        typer.echo(json.dumps(rows, indent=2, ensure_ascii=False))
    except Exception as e:
        typer.echo(json.dumps({"error": str(e)}))


@tools_app.command("info")
def tools_info(name: str):
    """Show schema for a specific tool."""
    try:
        from .ahp_compat import get_global_registry
        reg = get_global_registry()
        tool = reg.get_tool(name)
        schema = getattr(tool, "get_schema", lambda: {} )()
        typer.echo(json.dumps(schema, indent=2, ensure_ascii=False))
    except Exception as e:
        typer.echo(json.dumps({"error": str(e)}))
