import asyncio
import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from .rules import load_rules, default_rules_yaml, evaluate_log_line, evaluate_file_text
from .actions import dispatch


@dataclass
class FileEvent:
    kind: str  # "created" | "modified" | "deleted"
    path: str
    ts: float


class DirWatcher:
    def __init__(self, path: str, poll_interval: float = 1.0):
        self.root = Path(path)
        self.poll = poll_interval
        self._snapshot: Dict[str, float] = {}
        self._running = False

    def _scan(self) -> Dict[str, float]:
        snap: Dict[str, float] = {}
        if not self.root.exists():
            return snap
        for p in self.root.rglob("*"):
            if p.is_file():
                try:
                    snap[str(p)] = p.stat().st_mtime
                except FileNotFoundError:
                    continue
        return snap

    async def run(self):
        self._running = True
        self._snapshot = self._scan()
        while self._running:
            await asyncio.sleep(self.poll)
            new = self._scan()
            # Detect changes
            old_set, new_set = set(self._snapshot.keys()), set(new.keys())
            created = new_set - old_set
            deleted = old_set - new_set
            # Modified
            modified = {p for p in (new_set & old_set) if new[p] > self._snapshot[p]}
            ts = time.time()
            for p in sorted(created):
                yield FileEvent("created", p, ts)
            for p in sorted(modified):
                yield FileEvent("modified", p, ts)
            for p in sorted(deleted):
                yield FileEvent("deleted", p, ts)
            self._snapshot = new

    def stop(self):
        self._running = False


class LogTailer:
    def __init__(self, path: str, poll_interval: float = 0.5):
        self.path = Path(path)
        self.poll = poll_interval
        self._running = False
        self._offset = 0
        self._inode: Optional[int] = None

    def _open(self):
        f = self.path.open("rb")
        st = self.path.stat()
        self._inode = getattr(st, "st_ino", None)
        return f

    async def run(self):
        self._running = True
        f = None
        try:
            if self.path.exists():
                f = self._open()
                f.seek(0, os.SEEK_END)
                self._offset = f.tell()
        except FileNotFoundError:
            f = None

        while self._running:
            await asyncio.sleep(self.poll)
            try:
                if not self.path.exists():
                    continue
                st = self.path.stat()
                inode = getattr(st, "st_ino", None)
                if f is None or (self._inode is not None and inode is not None and inode != self._inode):
                    # Rotated or first open
                    if f:
                        f.close()
                    f = self._open()
                    self._offset = 0
                f.seek(self._offset)
                data = f.read()
                if data:
                    self._offset = f.tell()
                    for line in data.decode(errors="ignore").splitlines():
                        yield {
                            "path": str(self.path),
                            "line": line,
                            "ts": time.time(),
                        }
            except FileNotFoundError:
                continue

    def stop(self):
        self._running = False


class ControlServer:
    def __init__(self, host: str, port: int, state: "MonitorState"):
        self.host = host
        self.port = port
        self.state = state
        self.server = None

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        data = await reader.readline()
        try:
            cmd = json.loads(data.decode()) if data else {}
        except Exception:
            cmd = {}
        resp = await self._dispatch(cmd)
        writer.write((json.dumps(resp) + "\n").encode())
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    async def _dispatch(self, cmd: dict) -> dict:
        typ = cmd.get("cmd")
        if typ == "add_log":
            path = cmd.get("path")
            if not path:
                return {"ok": False, "error": "missing path"}
            await self.state.add_log(path)
            return {"ok": True, "added": path}
        if typ == "add_watch":
            path = cmd.get("path")
            if not path:
                return {"ok": False, "error": "missing path"}
            await self.state.add_watch(path)
            return {"ok": True, "added": path}
        if typ == "status":
            return {
                "ok": True,
                "dirs": sorted(self.state.watched_dirs),
                "logs": sorted(self.state.tailed_logs),
                "events": self.state.event_count,
                "lines": self.state.line_count,
            }
        if typ == "stop":
            await self.state.stop()
            return {"ok": True, "stopping": True}
        return {"ok": False, "error": "unknown cmd"}

    async def start(self):
        self.server = await asyncio.start_server(self.handle, self.host, self.port)

    async def wait_closed(self):
        if self.server:
            async with self.server:
                await self.server.serve_forever()


class MonitorState:
    def __init__(self, poll_interval: float = 1.0, state_dir: Optional[str] = None):
        self.poll_interval = poll_interval
        self.watched_dirs: Set[str] = set()
        self.tailed_logs: Set[str] = set()
        self._dir_tasks: Dict[str, asyncio.Task] = {}
        self._log_tasks: Dict[str, asyncio.Task] = {}
        self._running = True
        self.event_count = 0
        self.line_count = 0
        self.state_dir = Path(state_dir) if state_dir else None
        # Load rules
        self.rules_path = (self.state_dir / "rules.yaml") if self.state_dir else None
        self.rules = []
        if self.rules_path:
            if not self.rules_path.exists():
                self.rules_path.write_text(default_rules_yaml(), encoding="utf-8")
            self.rules = load_rules(self.rules_path)

    async def add_watch(self, path: str):
        p = os.path.abspath(path)
        if p in self._dir_tasks:
            return
        self.watched_dirs.add(p)
        watcher = DirWatcher(p, poll_interval=self.poll_interval)

        async def _task():
            async for ev in watcher.run():
                self.event_count += 1
                await self.on_file_event(ev)

        task = asyncio.create_task(_task())
        self._dir_tasks[p] = task

    async def add_log(self, path: str):
        p = os.path.abspath(path)
        if p in self._log_tasks:
            return
        self.tailed_logs.add(p)
        tailer = LogTailer(p)

        async def _task():
            async for item in tailer.run():
                self.line_count += 1
                await self.on_log_line(item)

        task = asyncio.create_task(_task())
        self._log_tasks[p] = task

    async def on_file_event(self, ev: FileEvent):
        print(f"[file] {ev.kind} {ev.path}")
        # On modify, scan text windows if rules apply
        if ev.kind == "modified" and self.rules:
            p = Path(ev.path)
            try:
                # Read bounded content
                # If the file is large, evaluate_file_text handles windows
                text = p.read_text(encoding="utf-8", errors="ignore")
                hits = evaluate_file_text(p, text, self.rules)
                for h in hits:
                    dispatch(h.get("action", {}), {"path": str(p), "rule": h.get("rule"), "hit": h})
            except Exception:
                pass

    async def on_log_line(self, item: dict):
        path = Path(item.get("path"))
        line = item.get("line")
        print(f"[log] {path.name}: {line}")
        if self.rules:
            hits = evaluate_log_line(path, line, self.rules)
            for h in hits:
                dispatch(h.get("action", {}), {"path": str(path), "rule": h.get("rule"), "hit": h, "line": line})

    async def stop(self):
        self._running = False
        # cancel tasks
        for t in list(self._dir_tasks.values()) + list(self._log_tasks.values()):
            t.cancel()


def daemonize():
    """Simple UNIX double-fork daemonization."""
    if os.name != "posix":
        return
    try:
        pid = os.fork()
        if pid > 0:
            os._exit(0)
    except OSError:
        return
    os.setsid()
    try:
        pid = os.fork()
        if pid > 0:
            os._exit(0)
    except OSError:
        return
    os.umask(0)
    os.chdir("/")


async def run_monitor(initial_dirs: List[str], initial_logs: List[str], host: str, port: int, poll_interval: float, state_dir: Optional[str] = None):
    state = MonitorState(poll_interval=poll_interval, state_dir=state_dir)
    ctrl = ControlServer(host, port, state)
    await ctrl.start()

    for d in initial_dirs:
        await state.add_watch(d)
    for l in initial_logs:
        await state.add_log(l)

    print(f"Monitor running. Control server on {host}:{port}. Press Ctrl-C to stop.")
    try:
        while True:
            await asyncio.sleep(3600)
    except (asyncio.CancelledError, KeyboardInterrupt):
        await state.stop()
        print("Monitor stopped.")
