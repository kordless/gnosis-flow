from __future__ import annotations

import ast
import math
import os
import sqlite3
import time
from collections import deque, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, Dict, Iterable, List, Optional, Tuple, Set


def _posix_rel(path: str, root: Path) -> str:
    p = Path(path)
    try:
        rel = p.resolve().relative_to(root.resolve())
    except Exception:
        # best effort: if absolute but not under root, just use name
        try:
            rel = p.resolve().name
        except Exception:
            rel = Path(path).name
    return rel.as_posix()


@dataclass
class Edge:
    src: str
    etype: str
    dst: str
    weight: float
    count: int
    last_seen: float
    explain: str


class GraphStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_schema()

    def _conn(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
        return con

    def _ensure_schema(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS nodes(
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    label TEXT,
                    meta TEXT
                );
                CREATE TABLE IF NOT EXISTS edges(
                    src TEXT NOT NULL,
                    type TEXT NOT NULL,
                    dst TEXT NOT NULL,
                    weight REAL NOT NULL,
                    count INTEGER NOT NULL,
                    last_seen REAL NOT NULL,
                    explain TEXT,
                    PRIMARY KEY(src, type, dst)
                );
                CREATE TABLE IF NOT EXISTS ix_file_paths(
                    path TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS meta(
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )

    def set_meta(self, key: str, value: str) -> None:
        with self._conn() as con:
            con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, value))

    def get_meta(self, key: str) -> Optional[str]:
        with self._conn() as con:
            cur = con.execute("SELECT value FROM meta WHERE key=?", (key,))
            row = cur.fetchone()
            return row[0] if row else None

    def ensure_file_node(self, relpath: str) -> str:
        node_id = f"file:{relpath}"
        with self._conn() as con:
            con.execute("INSERT OR IGNORE INTO nodes(id,type,label,meta) VALUES(?,?,?,?)", (node_id, "file", relpath, None))
            con.execute("INSERT OR REPLACE INTO ix_file_paths(path,node_id) VALUES(?,?)", (relpath, node_id))
        return node_id

    def ensure_term_node(self, term: str) -> str:
        node_id = f"term:{term}"
        with self._conn() as con:
            con.execute("INSERT OR IGNORE INTO nodes(id,type,label,meta) VALUES(?,?,?,?)", (node_id, "term", term, None))
        return node_id

    def node_for_path(self, relpath: str) -> Optional[str]:
        with self._conn() as con:
            cur = con.execute("SELECT node_id FROM ix_file_paths WHERE path=?", (relpath,))
            row = cur.fetchone()
            return row[0] if row else None

    def upsert_edge(self, e: Edge) -> None:
        with self._conn() as con:
            con.execute(
                "INSERT INTO edges(src,type,dst,weight,count,last_seen,explain) VALUES(?,?,?,?,?,?,?)\n"
                "ON CONFLICT(src,type,dst) DO UPDATE SET weight=excluded.weight, count=excluded.count, last_seen=excluded.last_seen, explain=excluded.explain",
                (e.src, e.etype, e.dst, float(e.weight), int(e.count), float(e.last_seen), e.explain),
            )

    def upsert_edge_undirected(self, a: str, etype: str, b: str, weight: float, count: int, last_seen: float, explain: str) -> None:
        self.upsert_edge(Edge(a, etype, b, weight, count, last_seen, explain))
        self.upsert_edge(Edge(b, etype, a, weight, count, last_seen, explain))

    def neighbors(self, node_id: str, types: Optional[List[str]] = None, min_w: float = 0.0, limit: int = 50) -> List[Edge]:
        q = "SELECT src,type,dst,weight,count,last_seen,explain FROM edges WHERE src=?"
        args: List[object] = [node_id]
        if types:
            q += " AND type IN (%s)" % ",".join(["?"] * len(types))
            args.extend(types)
        if min_w:
            q += " AND weight >= ?"
            args.append(min_w)
        q += " ORDER BY weight DESC, last_seen DESC LIMIT ?"
        args.append(limit)
        with self._conn() as con:
            cur = con.execute(q, args)
            rows = cur.fetchall()
        return [Edge(*row) for row in rows]

    def edges_between(self, a: str, b: str) -> List[Edge]:
        with self._conn() as con:
            cur = con.execute(
                "SELECT src,type,dst,weight,count,last_seen,explain FROM edges WHERE (src=? AND dst=?) OR (src=? AND dst=?)",
                (a, b, b, a),
            )
            rows = cur.fetchall()
        return [Edge(*row) for row in rows]

    def node_overview(self, node_id: str) -> Dict[str, object]:
        with self._conn() as con:
            cur = con.execute("SELECT type,label FROM nodes WHERE id=?", (node_id,))
            row = cur.fetchone()
            if not row:
                return {}
            ntype, label = row
            degs: Dict[str, int] = {}
            for trow in con.execute("SELECT type, COUNT(*) FROM edges WHERE src=? GROUP BY type", (node_id,)):
                degs[trow[0]] = int(trow[1])
        return {"id": node_id, "type": ntype, "label": label, "degree": degs}

    def search_files(self, q: str, limit: int = 20) -> List[str]:
        if not q:
            return []
        like = f"%{q}%"
        with self._conn() as con:
            cur = con.execute("SELECT path FROM ix_file_paths WHERE path LIKE ? ORDER BY path LIMIT ?", (like, limit))
            return [r[0] for r in cur.fetchall()]


class GraphManager:
    def __init__(self, root: Path, state_dir: Path, window_sec: int = 900, decay_tau_sec: int = 86400,
                 terms: Optional[List[str]] = None, shared_tokens_enabled: bool = False, max_file_kb: int = 256):
        self.root = root
        self.state_dir = state_dir
        self.store = GraphStore(state_dir / "graph.db")
        self.window_sec = int(window_sec)
        self.decay_tau_sec = int(decay_tau_sec)
        # Co-activity recent events (path -> deque[ts]) and a global deque for sliding window pairs
        self.recent: Deque[Tuple[str, float]] = deque()
        self.last_import_build: float = 0.0
        self.exclude_names = {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", "dist", "build"}
        # Terms
        self.terms: Set[str] = set((terms or []))
        # Shared tokens
        self.shared_tokens_enabled = bool(shared_tokens_enabled)
        self.max_file_kb = int(max_file_kb)
        self._token_index: Dict[str, Set[str]] = {}  # token -> set(relpath)
        self._file_tokens: Dict[str, Set[str]] = {}
        try:
            from datasketch import MinHash
            self._have_datasketch = True
            self._file_minhash: Dict[str, object] = {}
        except Exception:
            self._have_datasketch = False
            self._file_minhash = {}

    # ---- Edge builders ----
    def _dir_sibling_edges(self, relpath: str) -> None:
        p = (self.root / relpath).resolve()
        parent = p.parent
        try:
            if not parent.exists():
                return
            siblings = [c for c in parent.iterdir() if c.is_file() and c.name != p.name]
        except Exception:
            return
        n_sib = max(0, len(siblings))
        depth = len(parent.resolve().relative_to(self.root.resolve()).parts) if parent.exists() else 0
        depth_factor = 1.0 / (1.0 + depth)
        base = 1.0 / (1.0 + math.log(1.0 + (n_sib or 1)))
        w = base * depth_factor
        src = self.store.ensure_file_node(relpath)
        for s in siblings:
            # skip excluded names
            if s.name in self.exclude_names:
                continue
            dst_rel = _posix_rel(str(s), self.root)
            dst = self.store.ensure_file_node(dst_rel)
            now = time.time()
            self.store.upsert_edge_undirected(src, "dir_sibling", dst, w, 1, now, f"sibling in {parent.name} (#={n_sib})")

    def _scan_imports(self) -> None:
        # Build a simple map of module path -> file relpath
        mod_to_file: Dict[str, str] = {}
        for py in self.root.rglob("*.py"):
            try:
                if any(n in py.parts for n in self.exclude_names):
                    continue
                rel = _posix_rel(str(py), self.root)
                parts = Path(rel).with_suffix("").parts
                if parts[-1] == "__init__":
                    mod = ".".join(parts[:-1])
                else:
                    mod = ".".join(parts)
                mod_to_file[mod] = rel
            except Exception:
                continue

        def resolve_module(mod: str, from_file: str, level: int = 0) -> Optional[str]:
            if level:
                # relative import
                base = Path(from_file).parent
                for _ in range(level - 1):
                    base = base.parent
                if mod:
                    target = base / mod.replace(".", "/")
                else:
                    target = base
                # try file.py then package/__init__.py
                cand1 = target.with_suffix(".py").as_posix()
                cand2 = (target / "__init__.py").as_posix()
                for cand in (cand1, cand2):
                    try:
                        Path(self.root / cand).resolve().stat()
                        return _posix_rel(str(self.root / cand), self.root)
                    except Exception:
                        continue
                return None
            # absolute module
            # try exact, then progressively trim to find a package and append module
            if mod in mod_to_file:
                return mod_to_file.get(mod)
            parts = mod.split(".")
            while parts:
                prefix = ".".join(parts)
                if prefix in mod_to_file:
                    return mod_to_file[prefix]
                parts.pop()
            return None

        now = time.time()
        for py in self.root.rglob("*.py"):
            if any(n in py.parts for n in self.exclude_names):
                continue
            try:
                text = py.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(text)
            except Exception:
                continue
            src_rel = _posix_rel(str(py), self.root)
            src_node = self.store.ensure_file_node(src_rel)
            counts: Dict[str, int] = defaultdict(int)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        target = resolve_module(alias.name, src_rel, level=0)
                        if target:
                            counts[target] += 1
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    target = resolve_module(mod, src_rel, level=node.level or 0)
                    if target:
                        counts[target] += 1
            for dst_rel, cnt in counts.items():
                dst_node = self.store.ensure_file_node(dst_rel)
                w = max(0.0, min(1.0, 0.2 + 0.3 * math.log(1.0 + cnt)))
                self.store.upsert_edge(Edge(src_node, "import_dep", dst_node, w, cnt, now, f"imports={cnt}"))
        self.last_import_build = now

    def _tokenize_file(self, rel: str) -> Set[str]:
        # only small text files
        p = (self.root / rel)
        try:
            if not p.exists() or p.stat().st_size > self.max_file_kb * 1024:
                return set()
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return set()
        import re
        toks = set(t.lower() for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]+", text))
        # filter very short/common tokens
        toks = {t for t in toks if len(t) >= 3 and t not in {"the", "and", "for", "from", "with", "self", "this", "that", "class", "def"}}
        return toks

    def _ensure_file_tokens(self, rel: str) -> None:
        if rel in self._file_tokens:
            return
        toks = self._tokenize_file(rel)
        self._file_tokens[rel] = toks
        for t in toks:
            self._token_index.setdefault(t, set()).add(rel)
        if self._have_datasketch and toks:
            # build MinHash signature
            from datasketch import MinHash
            mh = MinHash(num_perm=128)
            for t in toks:
                mh.update(t.encode("utf-8"))
            self._file_minhash[rel] = mh

    def _build_shared_token_edges(self, rel: str) -> None:
        if not self.shared_tokens_enabled:
            return
        self._ensure_file_tokens(rel)
        toks = self._file_tokens.get(rel, set())
        if not toks:
            return
        # candidate files based on token overlap
        candidates: Set[str] = set()
        for t in list(toks)[:200]:  # cap per-file tokens considered
            candidates |= self._token_index.get(t, set())
        candidates.discard(rel)
        if not candidates:
            return
        src = self.store.ensure_file_node(rel)
        now = time.time()
        if self._have_datasketch:
            anchor = self._file_minhash.get(rel)
            for other in list(candidates)[:500]:  # cap comparisons
                try:
                    mh = self._file_minhash.get(other)
                    if not mh:
                        self._ensure_file_tokens(other)
                        mh = self._file_minhash.get(other)
                    if not mh or not anchor:
                        continue
                    j = anchor.jaccard(mh)
                    if j <= 0.0:
                        continue
                    w = min(0.9, float(j))
                    dst = self.store.ensure_file_node(other)
                    self.store.upsert_edge_undirected(src, "shared_tokens", dst, w, int(1000 * w), now, f"minhash j={round(w,3)}")
                except Exception:
                    continue
        else:
            for other in list(candidates)[:300]:
                try:
                    otoks = self._file_tokens.get(other)
                    if otoks is None:
                        self._ensure_file_tokens(other)
                        otoks = self._file_tokens.get(other) or set()
                    if not otoks:
                        continue
                    inter = len(toks & otoks)
                    if inter == 0:
                        continue
                    uni = len(toks | otoks)
                    j = inter / max(1, uni)
                    if j <= 0:
                        continue
                    w = min(0.9, float(j))
                    dst = self.store.ensure_file_node(other)
                    self.store.upsert_edge_undirected(src, "shared_tokens", dst, w, inter, now, f"overlap={inter} j={round(w,3)}")
                except Exception:
                    continue

    def _term_refs_for_file(self, rel: str) -> None:
        if not self.terms:
            return
        p = (self.root / rel)
        try:
            if not p.exists() or p.stat().st_size > self.max_file_kb * 1024:
                return
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return
        low = text.lower()
        src = self.store.ensure_file_node(rel)
        now = time.time()
        for term in list(self.terms)[:200]:
            t = term.lower().strip()
            if not t:
                continue
            cnt = low.count(t)
            if cnt > 0:
                dst = self.store.ensure_term_node(t)
                # simple tf-like weight
                w = min(0.8, 0.2 + 0.1 * math.log(1.0 + cnt))
                self.store.upsert_edge(Edge(src, "term_ref", dst, w, cnt, now, f"refs={cnt}"))

    # ---- Public API ----
    def on_file_event(self, path: str, ts: Optional[float] = None) -> None:
        ts = ts or time.time()
        rel = _posix_rel(path, self.root)
        a = self.store.ensure_file_node(rel)
        # slide window
        self.recent.append((rel, ts))
        cutoff = ts - self.window_sec
        while self.recent and self.recent[0][1] < cutoff:
            self.recent.popleft()
        # co-activity with others inside window
        # build a small counter for pairings
        seen: Dict[str, int] = defaultdict(int)
        for other_rel, t in self.recent:
            if other_rel == rel:
                continue
            if t >= cutoff:
                seen[other_rel] += 1
        for other_rel, cnt in seen.items():
            b = self.store.ensure_file_node(other_rel)
            # convert count in window to weight using 1-exp(-lambda*cnt)
            lam = 1.0 / max(1.0, (self.window_sec / 60.0))  # approx by minutes in window
            w = 1.0 - math.exp(-lam * cnt)
            self.store.upsert_edge_undirected(a, "co_activity", b, w, cnt, ts, f"co-changes {cnt} in last {self.window_sec}s")

    def ensure_background_edges(self, relpath: str, types: Iterable[str]) -> None:
        types = set(types)
        if "dir_sibling" in types:
            self._dir_sibling_edges(relpath)
        if "import_dep" in types:
            # rebuild imports at most every 60s
            if time.time() - self.last_import_build > 60.0:
                self._scan_imports()
        if "shared_tokens" in types:
            self._build_shared_token_edges(relpath)
        if "term_ref" in types:
            self._term_refs_for_file(relpath)

    def neighbors_for_path(self, path_or_rel: str, types: Optional[List[str]] = None, min_w: float = 0.0, limit: int = 20) -> List[Dict[str, object]]:
        rel = _posix_rel(path_or_rel, self.root)
        self.ensure_background_edges(rel, types or ["dir_sibling", "import_dep", "co_activity"])
        node_id = self.store.ensure_file_node(rel)
        edges = self.store.neighbors(node_id, types=types, min_w=min_w, limit=limit)
        out = []
        for e in edges:
            # map dst id back to file path
            if e.dst.startswith("file:"):
                dst_rel = e.dst.split(":", 1)[1]
            elif e.dst.startswith("term:"):
                dst_rel = e.dst.split(":", 1)[1]
            else:
                dst_rel = e.dst
            out.append({
                "src": rel,
                "dst": dst_rel,
                "type": e.etype,
                "weight": round(float(e.weight), 6),
                "count": int(e.count),
                "last_seen": float(e.last_seen),
                "explain": e.explain or "",
            })
        return out

    def node_info(self, path_or_rel: str) -> Dict[str, object]:
        rel = _posix_rel(path_or_rel, self.root)
        node_id = self.store.ensure_file_node(rel)
        return self.store.node_overview(node_id)

    def why(self, a_path: str, b_path: str) -> List[Dict[str, object]]:
        a_rel = _posix_rel(a_path, self.root)
        b_rel = _posix_rel(b_path, self.root)
        a = self.store.ensure_file_node(a_rel)
        b = self.store.ensure_file_node(b_rel)
        edges = self.store.edges_between(a, b)
        out = []
        for e in edges:
            out.append({
                "src": e.src.split(":", 1)[1],
                "dst": e.dst.split(":", 1)[1],
                "type": e.etype,
                "weight": round(float(e.weight), 6),
                "count": int(e.count),
                "last_seen": float(e.last_seen),
                "explain": e.explain or "",
            })
        return out

    @staticmethod
    def edge_types() -> List[Dict[str, str]]:
        return [
            {"type": "dir_sibling", "description": "Files in the same directory"},
            {"type": "import_dep", "description": "Python import dependency (A imports B)"},
            {"type": "co_activity", "description": "Files modified close in time"},
            {"type": "shared_tokens", "description": "Token similarity between files"},
            {"type": "term_ref", "description": "File references a term"},
        ]
