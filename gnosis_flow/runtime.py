import asyncio
import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from .rules import load_rules, default_rules_yaml, evaluate_log_line, evaluate_file_text
from .actions import dispatch
from .ahp_compat import get_global_registry


@dataclass
class FileEvent:
    kind: str  # "created" | "modified" | "deleted"
    path: str
    ts: float


@dataclass
class FileStat:
    path: str
    last_line_count: Optional[int] = None
    # list of [ts, delta_lines]
    changes: List[List[float]] = None

    def __post_init__(self):
        if self.changes is None:
            self.changes = []

    def add_delta(self, ts: float, delta: int):
        self.changes.append([float(ts), int(delta)])
        # Trim to last 5 minutes
        cutoff = ts - 300.0
        self.changes = [c for c in self.changes if c[0] >= cutoff]

    def rates(self) -> Dict[str, float]:
        """Compute average rate and acceleration over last 5 minutes.

        Returns lines_per_min, accel_lines_per_min2 (difference between last half and first half rates per minute).
        """
        if not self.changes:
            return {"rate_5m": 0.0, "accel_5m": 0.0}
        now = max(c[0] for c in self.changes)
        cutoff = now - 300.0
        window = [c for c in self.changes if c[0] >= cutoff]
        if not window:
            return {"rate_5m": 0.0, "accel_5m": 0.0}
        total = sum(c[1] for c in window)
        elapsed = max(1.0, (max(c[0] for c in window) - min(c[0] for c in window)))
        rate = total / (elapsed / 60.0)
        # Split halves
        mid = cutoff + 150.0
        first = [c for c in window if c[0] < mid]
        second = [c for c in window if c[0] >= mid]
        def _rate(group: List[List[float]]):
            if not group:
                return 0.0
            tot = sum(c[1] for c in group)
            el = max(1.0, (max(c[0] for c in group) - min(c[0] for c in group)))
            return tot / (el / 60.0)
        r1 = _rate(first)
        r2 = _rate(second)
        accel = (r2 - r1) / 5.0  # per minute^2 across 5 minutes
        return {"rate_5m": float(round(rate, 3)), "accel_5m": float(round(accel, 3))}


class DirWatcher:
    def __init__(self, path: str, poll_interval: float = 1.0, exclude_prefixes: Optional[List[str]] = None):
        self.root = Path(path)
        self.poll = poll_interval
        self._snapshot_files: Dict[str, float] = {}
        self._snapshot_dirs: Set[str] = set()
        self._running = False
        self._excl: List[str] = [str(Path(p)) for p in (exclude_prefixes or [])]

    def _scan(self) -> Tuple[Dict[str, float], Set[str]]:
        files: Dict[str, float] = {}
        dirs: Set[str] = set()
        if not self.root.exists():
            return files, dirs
        for p in self.root.rglob("*"):
            try:
                sp = str(p)
                # skip excluded prefixes
                skip = False
                for ex in self._excl:
                    if sp == ex or sp.startswith(ex + os.sep):
                        skip = True
                        break
                if skip:
                    continue
                if p.is_dir():
                    dirs.add(sp)
                elif p.is_file():
                    files[sp] = p.stat().st_mtime
            except FileNotFoundError:
                continue
        return files, dirs

    async def run(self):
        self._running = True
        self._snapshot_files, self._snapshot_dirs = self._scan()
        while self._running:
            await asyncio.sleep(self.poll)
            new_files, new_dirs = self._scan()
            # Detect file changes
            oldf, newf = set(self._snapshot_files.keys()), set(new_files.keys())
            created = newf - oldf
            deleted = oldf - newf
            modified = {p for p in (newf & oldf) if new_files[p] > self._snapshot_files[p]}
            # Detect directory creations/deletions
            oldd, newd = self._snapshot_dirs, new_dirs
            dir_created = newd - oldd
            dir_deleted = oldd - newd
            ts = time.time()
            for p in sorted(created):
                yield FileEvent("created", p, ts)
            for p in sorted(modified):
                yield FileEvent("modified", p, ts)
            for p in sorted(deleted):
                yield FileEvent("deleted", p, ts)
            for p in sorted(dir_created):
                yield FileEvent("dir_created", p, ts)
            for p in sorted(dir_deleted):
                yield FileEvent("dir_deleted", p, ts)
            self._snapshot_files = new_files
            self._snapshot_dirs = new_dirs

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


class HttpStatusServer:
    """Minimal HTTP server to expose /status without extra deps."""
    def __init__(self, host: str, port: int, state: "MonitorState"):
        self.host = host
        self.port = port
        self.state = state
        self.server = None

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await reader.readuntil(b"\r\n\r\n")
        except asyncio.IncompleteReadError:
            data = await reader.read(1024)
        first = (data or b"").split(b"\r\n", 1)[0].decode(errors="ignore")
        method, raw_path, *_ = (first.split(" ") + ["", ""])[:3]
        path, _, query = raw_path.partition("?")
        qs = {}
        if query:
            for kv in query.split("&"):
                if not kv:
                    continue
                k, _, v = kv.partition("=")
                qs[k] = v
        handled = False
        if path.startswith("/status"):
            body = json.dumps({
                "ok": True,
                "dirs": sorted(self.state.watched_dirs),
                "logs": sorted(self.state.tailed_logs),
                "events": self.state.event_count,
                "lines": self.state.line_count,
            }).encode()
            headers = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                b"Access-Control-Allow-Origin: *\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
            )
            writer.write(headers + body)
            handled = True
        elif path.startswith("/tools/usage"):
            try:
                from .metrics import get_tool_usage
                body = json.dumps(get_tool_usage()).encode()
            except Exception:
                body = json.dumps({}).encode()
            headers = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                b"Access-Control-Allow-Origin: *\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
            )
            writer.write(headers + body)
            handled = True
        elif path.startswith("/tools/") and path.endswith("/schema"):
            # /tools/<name>/schema
            try:
                name = path[len("/tools/"):-len("/schema")].strip("/")
                from .ahp_compat import get_global_registry
                reg = get_global_registry()
                tool = reg.get_tool(name)
                schema = getattr(tool, "get_schema", lambda: {} )()
                body = json.dumps(schema).encode()
            except Exception as e:
                body = json.dumps({"error": str(e)}).encode()
            headers = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                b"Access-Control-Allow-Origin: *\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
            )
            writer.write(headers + body)
            handled = True
        elif path.startswith("/tools"):
            # list schemas
            try:
                from .ahp_compat import get_global_registry
                reg = get_global_registry()
                schemas = reg.get_schemas()
                # attach categories
                cats = getattr(reg, "categories", {})
                out = []
                for s in schemas:
                    nm = s.get("name")
                    cat = None
                    for k, v in cats.items():
                        if nm in v:
                            cat = k
                            break
                    out.append({"name": nm, "description": s.get("description", ""), "category": cat or "general"})
                body = json.dumps(out).encode()
            except Exception as e:
                body = json.dumps({"error": str(e)}).encode()
            headers = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                b"Access-Control-Allow-Origin: *\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
            )
            writer.write(headers + body)
            handled = True
        elif path.startswith("/events"):
            # return recent events (last N lines)
            limit = 200
            try:
                limit = int(qs.get("limit", "200"))
            except Exception:
                limit = 200
            lines: List[str] = []
            try:
                evp = self.state.events_path
                if evp and evp.exists():
                    content = evp.read_text(encoding="utf-8").splitlines()
                    lines = content[-limit:]
            except Exception:
                lines = []
            body = ("[" + ",".join(lines) + "]").encode()
            headers = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                b"Access-Control-Allow-Origin: *\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
            )
            writer.write(headers + body)
            handled = True
        elif path.startswith("/console.js"):
            body = CONSOLE_JS.encode()
            headers = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/javascript; charset=utf-8\r\n"
                b"Access-Control-Allow-Origin: *\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
            )
            writer.write(headers + body)
            handled = True
        elif path.startswith("/console.css"):
            body = CONSOLE_CSS.encode()
            headers = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/css; charset=utf-8\r\n"
                b"Access-Control-Allow-Origin: *\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
            )
            writer.write(headers + body)
            handled = True
        elif path.startswith("/console") or path == "/":
            body = CONSOLE_HTML.encode()
            headers = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/html; charset=utf-8\r\n"
                b"Access-Control-Allow-Origin: *\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
            )
            writer.write(headers + body)
            handled = True
        elif path.startswith("/stream"):
            # SSE stream
            headers = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/event-stream\r\n"
                b"Cache-Control: no-cache\r\n"
                b"Connection: keep-alive\r\n"
                b"Access-Control-Allow-Origin: *\r\n\r\n"
            )
            try:
                writer.write(headers)
                await writer.drain()
            except Exception:
                # Failed to establish stream
                return
            q = self.state.bcast.add_subscriber()
            try:
                # Send initial hello
                try:
                    writer.write(b"event: hello\ndata: {}\n\n")
                    await writer.drain()
                except Exception:
                    return
                keep = True
                while keep:
                    try:
                        evt = await asyncio.wait_for(q.get(), timeout=15.0)
                        payload = ("data: " + json.dumps(evt, ensure_ascii=False) + "\n\n").encode()
                        writer.write(payload)
                        await writer.drain()
                    except asyncio.TimeoutError:
                        # heartbeat comment
                        try:
                            writer.write(b": keep-alive\n\n")
                            await writer.drain()
                        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                            keep = False
                        except Exception:
                            keep = False
                    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                        keep = False
                    except asyncio.CancelledError:
                        keep = False
                    except Exception:
                        # Any other error: stop this stream
                        keep = False
            finally:
                self.state.bcast.remove_subscriber(q)
                try:
                    writer.close()
                except Exception:
                    pass
            return
        if not handled:
            body = b"OK"
            headers = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/plain; charset=utf-8\r\n"
                b"Access-Control-Allow-Origin: *\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
            )
            writer.write(headers + body)
        try:
            await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def start(self):
        self.server = await asyncio.start_server(self.handle, self.host, self.port)

    async def wait_closed(self):
        if self.server:
            async with self.server:
                await self.server.serve_forever()


# Static UI assets (inline for packaging simplicity)
CONSOLE_HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Gnosis Flow · Live Console</title>
    <link rel="stylesheet" href="/console.css" />
  </head>
  <body>
    <header>
      <div class="title">Gnosis Flow · Live Console</div>
      <div class="controls">
        <button id="pauseBtn">Pause</button>
        <button id="clearBtn">Clear</button>
        <input id="filter" placeholder="Filter (type: log|file|hit, path, rule)" />
      </div>
    </header>
    <main id="log"></main>
    <script src="/console.js"></script>
  </body>
  </html>
"""

CONSOLE_CSS = """
:root { --bg:#0f1115; --panel:#151924; --fg:#e5e7eb; --muted:#9aa0a6; --ok:#34d399; --warn:#f59e0b; --err:#ef4444; --acc:#5eead4; }
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace}
header{position:sticky;top:0;background:linear-gradient(180deg,var(--panel),rgba(21,25,36,0.6));border-bottom:1px solid rgba(255,255,255,0.06);display:flex;gap:16px;align-items:center;justify-content:space-between;padding:10px 12px}
.title{font-weight:700;letter-spacing:.3px}
.controls{display:flex;gap:8px;align-items:center}
button{background:rgba(94,234,212,.12);color:var(--fg);border:1px solid rgba(94,234,212,.4);padding:6px 10px;border-radius:8px;cursor:pointer}
input{background:rgba(255,255,255,.06);color:var(--fg);border:1px solid rgba(255,255,255,.12);border-radius:8px;padding:6px 8px;min-width:280px}
main{padding:10px 12px}
.row{display:flex;gap:10px;align-items:flex-start;padding:6px 8px;border-bottom:1px solid rgba(255,255,255,.06)}
.badge{padding:2px 6px;border-radius:6px;font-weight:700;min-width:44px;text-align:center}
.file{background:rgba(52,211,153,.15);border:1px solid rgba(52,211,153,.5)}
.log{background:rgba(94,234,212,.12);border:1px solid rgba(94,234,212,.4)}
.hit{background:rgba(245,158,11,.12);border:1px solid rgba(245,158,11,.5)}
.dir{background:rgba(147,197,253,.12);border:1px solid rgba(147,197,253,.5)}
.meta{color:var(--muted)}
.jsonbtn{margin-left:auto}
details{margin-left:auto}
pre{white-space:pre-wrap;word-break:break-word}
"""

CONSOLE_JS = """
(function(){
  const log = document.getElementById('log');
  const pauseBtn = document.getElementById('pauseBtn');
  const clearBtn = document.getElementById('clearBtn');
  const filter = document.getElementById('filter');
  let paused = false;
  let filterTxt = '';
  const buf = [];

  function matchesFilter(text, json){
    if(!filterTxt) return true;
    const ft = filterTxt.toLowerCase();
    const hay = (text + ' ' + JSON.stringify(json)).toLowerCase();
    return hay.includes(ft);
  }

  function row(kind, text, json){
    if(!matchesFilter(text, json)) return;
    const div = document.createElement('div');
    div.className = 'row';
    const badge = document.createElement('span');
    badge.className = 'badge ' + kind;
    badge.textContent = kind.toUpperCase();
    const span = document.createElement('span');
    const ts = json.ts ? new Date(json.ts * 1000) : new Date();
    const tsStr = ts.toLocaleTimeString();
    span.textContent = `[${tsStr}] ` + text;
    const det = document.createElement('details');
    const sum = document.createElement('summary');
    sum.textContent = '{ }';
    sum.className = 'jsonbtn';
    const pre = document.createElement('pre');
    pre.textContent = JSON.stringify(json, null, 2);
    det.appendChild(sum); det.appendChild(pre);
    div.appendChild(badge); div.appendChild(span); div.appendChild(det);
    log.appendChild(div);
    // Scroll
    window.requestAnimationFrame(()=>{ window.scrollTo(0, document.body.scrollHeight); });
  }

  pauseBtn.onclick = ()=>{ paused = !paused; pauseBtn.textContent = paused? 'Resume' : 'Pause'; };
  clearBtn.onclick = ()=>{ log.innerHTML=''; };
  filter.oninput = ()=>{ filterTxt = filter.value.trim(); renderAll(); };

  function pushEvent(obj){
    buf.push(obj);
    renderOne(obj);
  }

  function renderOne(obj){
    if(paused) return;
    if(!obj || !obj.type) return;
    if(obj.type === 'file_event'){
      row('file', `${obj.kind} ${obj.path}`, obj);
    } else if(obj.type === 'dir_event'){
      const kind = (obj.kind || '').replace('dir_', '');
      row('dir', `${kind} ${obj.path}`, obj);
    } else if(obj.type === 'log_line'){
      row('log', `${obj.path} :: ${obj.line}`, obj);
    } else if(obj.type === 'rule_hit'){
      const sim = obj.similarity != null ? ` sim=${obj.similarity}` : '';
      row('hit', `${obj.rule}${sim} :: ${obj.path}`, obj);
    } else if(obj.type === 'file_stats'){
      const extra = (obj.added_lines!=null && obj.deleted_lines!=null) ? ` (+${obj.added_lines}/-${obj.deleted_lines})` : '';
      row('file', `Δlines=${obj.delta_lines}${extra} rate_5m=${obj.rate_5m} accel_5m=${obj.accel_5m} :: ${obj.path}`, obj);
    }
  }

  function renderAll(){
    log.innerHTML = '';
    for(const e of buf){ renderOne(e); }
  }

  const es = new EventSource('/stream');
  es.onmessage = (ev)=>{
    try{
      const obj = JSON.parse(ev.data);
      pushEvent(obj);
    }catch(e){}
  };

  // preload recent events
  fetch('/events?limit=200').then(r=>r.json()).then(arr=>{
    if(Array.isArray(arr)){
      for(const e of arr){ buf.push(e); }
      renderAll();
    }
  }).catch(()=>{});
})();
"""


class Broadcaster:
    def __init__(self, max_queue: int = 200):
        self.subs: List[asyncio.Queue] = []
        self.max_queue = max_queue

    def add_subscriber(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self.max_queue)
        self.subs.append(q)
        return q

    def remove_subscriber(self, q: asyncio.Queue) -> None:
        try:
            self.subs.remove(q)
        except ValueError:
            pass

    def publish(self, event: Dict[str, Any]) -> None:
        # Try to enqueue, drop oldest on overflow
        for q in list(self.subs):
            if q.full():
                try:
                    _ = q.get_nowait()
                except Exception:
                    pass
            try:
                q.put_nowait(event)
            except Exception:
                # Disconnect bad subscriber
                try:
                    self.subs.remove(q)
                except Exception:
                    pass


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
        # File stats persistence
        self.stats_path = (self.state_dir / "file_stats.json") if self.state_dir else None
        self.file_stats: Dict[str, FileStat] = {}
        self._load_stats()
        # Broadcaster for SSE
        self.bcast = Broadcaster()
        # Exclude prefixes (state dir and common noise)
        self.exclude_prefixes: List[str] = []
        if self.state_dir:
            self.exclude_prefixes.append(str(self.state_dir))
        # Also exclude common noisy folders within watched roots by default
        # (we'll apply as absolute prefixes when adding watches)
        self.default_exclude_names: List[str] = [
            ".git", "node_modules", ".venv", ".gnosis-flow",
            "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
            "dist", "build", ".idea", ".vscode",
        ]
        # Optional config: .gnosis-flow/config.yaml with exclude_names: [ ... ]
        self.config_path = (self.state_dir / "config.yaml") if self.state_dir else None
        self.extra_exclude_names: List[str] = []
        if self.config_path and self.config_path.exists():
            try:
                import yaml  # local dependency already present
                cfg = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
                self.extra_exclude_names = list(cfg.get("exclude_names", []) or [])
            except Exception:
                self.extra_exclude_names = []
        # Discover built-in tools (lenient)
        try:
            reg = get_global_registry()
            tools_dir = Path(__file__).parent / "ahp_tools"
            reg.discover_tools(tools_dir, strict=False)
        except Exception:
            pass
        # Event log path
        self.events_path = (self.state_dir / "events.ndjson") if self.state_dir else None

    def log_event(self, event: Dict[str, Any]) -> None:
        if not self.events_path:
            return
        try:
            self.events_path.parent.mkdir(parents=True, exist_ok=True)
            with self.events_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception:
            pass
        # Snapshots for line diffing
        self.snapshots_dir = (self.state_dir / "snapshots") if self.state_dir else None
        if self.snapshots_dir:
            try:
                self.snapshots_dir.mkdir(exist_ok=True)
            except Exception:
                pass

    def _load_stats(self):
        if not self.stats_path or not self.stats_path.exists():
            return
        try:
            data = json.loads(self.stats_path.read_text(encoding="utf-8"))
            for p, obj in data.items():
                self.file_stats[p] = FileStat(path=p, last_line_count=obj.get("last_line_count"), changes=obj.get("changes", []))
        except Exception:
            pass

    def _save_stats(self):
        if not self.stats_path:
            return
        try:
            out = {p: {"last_line_count": fs.last_line_count, "changes": fs.changes} for p, fs in self.file_stats.items()}
            self.stats_path.write_text(json.dumps(out), encoding="utf-8")
        except Exception:
            pass

    async def add_watch(self, path: str):
        p = os.path.abspath(path)
        if p in self._dir_tasks:
            return
        self.watched_dirs.add(p)
        # Build absolute exclude prefixes for this root
        excl = []
        # State dir (already absolute)
        excl.extend(self.exclude_prefixes)
        # Common folders under this root
        names = list(set(self.default_exclude_names + self.extra_exclude_names))
        for name in names:
            cand = os.path.join(p, name)
            excl.append(cand)
        watcher = DirWatcher(p, poll_interval=self.poll_interval, exclude_prefixes=excl)

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
        # Directory events
        if ev.kind in ("dir_created", "dir_deleted"):
            print(f"[dir] {ev.kind.split('_')[1]} {ev.path}")
            try:
                evt = {"type": "dir_event", "path": ev.path, "kind": ev.kind, "ts": ev.ts}
                self.bcast.publish(evt)
                self.log_event(evt)
            except Exception:
                pass
            return

        print(f"[file] {ev.kind} {ev.path}")
        try:
            evt = {"type": "file_event", "path": ev.path, "kind": ev.kind, "ts": ev.ts}
            self.bcast.publish(evt)
            self.log_event(evt)
        except Exception:
            pass
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
                    try:
                        evt = {"type": "rule_hit", "path": str(p), "rule": h.get("rule"), "ts": time.time(), **{k: v for k, v in h.items() if k not in ("action",)}}
                        self.bcast.publish(evt)
                        self.log_event(evt)
                    except Exception:
                        pass
            except Exception:
                pass
        # Track line changes and acceleration; compute +/- using snapshots for small text files
        if ev.kind == "modified":
            p = Path(ev.path)
            stat = self.file_stats.get(ev.path) or FileStat(path=ev.path)
            # If this path is being tailed as a log, we rely on tail updates for line counts
            lines_changed = None
            added_lines = None
            deleted_lines = None
            try:
                size_ok = p.exists() and p.stat().st_size <= 10_000_000
                if str(p) not in self.tailed_logs and size_ok:
                    # Count lines cheaply
                    text = p.read_text(encoding="utf-8", errors="ignore")
                    new_lines = text.splitlines()
                    new_count = len(new_lines)
                    # Diff against snapshot (only if reasonably small file)
                    added_lines = 0
                    deleted_lines = 0
                    try:
                        if self.snapshots_dir and p.stat().st_size <= 2_000_000:
                            import hashlib
                            snap_path = self.snapshots_dir / (hashlib.sha1(ev.path.encode()).hexdigest() + ".txt")
                            prev_text = ""
                            if snap_path.exists():
                                prev_text = snap_path.read_text(encoding="utf-8", errors="ignore")
                            prev_lines = prev_text.splitlines()
                            # Compute diff
                            import difflib
                            for d in difflib.ndiff(prev_lines, new_lines):
                                if d.startswith("+ "):
                                    added_lines += 1
                                elif d.startswith("- "):
                                    deleted_lines += 1
                            # Save snapshot
                            try:
                                snap_path.write_text(text, encoding="utf-8")
                            except Exception:
                                pass
                    except Exception:
                        # Ignore snapshot diff errors
                        added_lines = None
                        deleted_lines = None
                    if stat.last_line_count is not None:
                        lines_changed = new_count - stat.last_line_count
                    else:
                        lines_changed = 0
                    stat.last_line_count = new_count
                else:
                    # Unknown or large; default to 0 for file events (log tail updates handle growth)
                    if stat.last_line_count is None:
                        stat.last_line_count = 0
                    lines_changed = 0
            except Exception:
                lines_changed = None
            if lines_changed is not None:
                stat.add_delta(ev.ts, int(lines_changed))
                self.file_stats[ev.path] = stat
                self._save_stats()
                rates = stat.rates()
                if added_lines is not None and deleted_lines is not None:
                    print(f"[file] Δlines={lines_changed} (+{added_lines}/-{deleted_lines}) rate_5m={rates['rate_5m']} l/m accel_5m={rates['accel_5m']} l/m^2")
                else:
                    print(f"[file] Δlines={lines_changed} rate_5m={rates['rate_5m']} l/m accel_5m={rates['accel_5m']} l/m^2")
                try:
                    payload = {"type": "file_stats", "path": ev.path, "delta_lines": lines_changed, "ts": time.time(), **rates}
                    if added_lines is not None and deleted_lines is not None:
                        payload.update({"added_lines": added_lines, "deleted_lines": deleted_lines})
                    self.bcast.publish(payload)
                    self.log_event(payload)
                except Exception:
                    pass

    async def on_log_line(self, item: dict):
        path = Path(item.get("path"))
        line = item.get("line")
        print(f"[log] {path.name}: {line}")
        try:
            evt = {"type": "log_line", "path": str(path), "line": line, "ts": item.get("ts", time.time())}
            self.bcast.publish(evt)
            self.log_event(evt)
        except Exception:
            pass
        if self.rules:
            hits = evaluate_log_line(path, line, self.rules)
            for h in hits:
                dispatch(h.get("action", {}), {"path": str(path), "rule": h.get("rule"), "hit": h, "line": line})
                try:
                    evt = {"type": "rule_hit", "path": str(path), "rule": h.get("rule"), "ts": time.time(), **{k: v for k, v in h.items() if k not in ("action",)}}
                    self.bcast.publish(evt)
                    self.log_event(evt)
                except Exception:
                    pass
        # Update per-file stats for acceleration (count lines appended)
        ts = item.get("ts", time.time())
        stat = self.file_stats.get(str(path)) or FileStat(path=str(path))
        last = stat.last_line_count or 0
        stat.last_line_count = last + 1
        stat.add_delta(ts, 1)
        self.file_stats[str(path)] = stat
        self._save_stats()

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


async def run_monitor(initial_dirs: List[str], initial_logs: List[str], host: str, port: int, poll_interval: float, state_dir: Optional[str] = None, http_enabled: bool = False, http_port: int = 8766):
    state = MonitorState(poll_interval=poll_interval, state_dir=state_dir)
    # Expose state dir for actions/metrics via env
    try:
        if state.state_dir:
            os.environ["GNOSIS_FLOW_STATE_DIR"] = str(state.state_dir)
    except Exception:
        pass
    ctrl = ControlServer(host, port, state)
    await ctrl.start()
    http_srv = None
    if http_enabled:
        http_srv = HttpStatusServer(host, http_port, state)
        await http_srv.start()

    for d in initial_dirs:
        await state.add_watch(d)
    for l in initial_logs:
        await state.add_log(l)

    msg = f"Monitor running. Control server on {host}:{port}."
    if http_enabled:
        msg += f" HTTP status on http://{host}:{http_port}/status."
    msg += " Press Ctrl-C to stop."
    print(msg)
    try:
        while True:
            await asyncio.sleep(3600)
    except (asyncio.CancelledError, KeyboardInterrupt):
        await state.stop()
        print("Monitor stopped.")
