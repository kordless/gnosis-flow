# EPIC: Code Relationship Graph

A lightweight, live-updating graph of code relationships for gnosis-flow that powers discovery, navigation, and automation.

## Summary
- Build a file-level graph that captures proximity and influence between files using multiple signals: directory siblings, imports, shared tokens, term references, and co-activity from recent edits/logs.
- Serve graph queries via HTTP and expose them through AHP/MCP tools; render a compact graph panel in the live console.
- Keep implementation incremental, dependency-light, and aligned with gnosis-flow’s async runtime and events model.

## Goals
- Provide fast neighbors and explanations for any file or symbol path.
- Continuously ingest activity (file changes, log lines) to adjust edge weights with recency/decay.
- Offer simple, documented HTTP endpoints and AHP/MCP tools for programmatic access.
- Ship a minimal, usable UI panel in `/console` for exploration and debugging.

## Non-Goals
- Full semantic embeddings, vector stores, or LLM-based code understanding.
- Cross-repo graphs or remote/cluster storage.
- Language-agnostic static analysis beyond basic Python imports in the first phases.

## Personas & Use Cases
- Developer: “What else is related to this file I’m editing?”
- Automations/Tools: “Find nearby files to patch/test when this file changes.”
- Monitoring: “Explain why these files co-change during recent activity.”
- Search: “Which modules reference this term or import this module?”

---

## Concepts & Data Model

### Node Types
- File: canonical repo-relative path (e.g., `src/pkg/mod.py`).
- Term (Phase 2 optional): normalized identifier/keyword.
- Symbol (Phase 3 optional): language-aware symbol (function/class), emitted later.

### Edge Types (directed unless noted)
- dir_sibling (undirected): files in the same directory; weight favors small, cohesive folders.
- import_dep (directed): `A -> B` if A imports B (Python AST-based initially).
- shared_tokens (undirected, Phase 2 optional): similarity by token shingles/minhash.
- term_ref (directed, Phase 2): file references a term (file -> term).
- co_activity (undirected): files modified close in time within sliding windows.

### Node/Edge Identifiers
- Node key: `file:<relpath>` | `term:<value>` | `sym:<path>#<symbol>` (future).
- Edge key: `(src, type, dst)` with attributes.

### Edge Attributes
- weight: float in [0, 1], normalized per edge type then combined.
- last_seen: timestamp of most recent evidence.
- count: integer occurrences (e.g., import frequency, co-change count).
- explain: compact provenance summary (e.g., “3 imports + 2 co-activity events, last 10m”).

### Weighting (initial formulas)
- dir_sibling: `w = 1 / (1 + ln(1 + siblings)) * depth_factor`, where `depth_factor = 1 / (1 + depth)`.
- import_dep: `w = clamp(0.2 + 0.3 * ln(1 + count), 0, 1)`.
- shared_tokens: Jaccard (or MinHash estimate) capped at 0.9.
- co_activity: `w = 1 - exp(-lambda * count_windowed)`, lambda tuned by window size.
- term_ref: `w = min(0.8, tfidf_like_score)`.
- Recency decay: multiply each edge’s `w` by `exp(-(now - last_seen)/tau)` per type.

---

## Data Sources
- Filesystem snapshots from DirWatcher (existing) for directory context.
- Python import graph via AST parse for `.py` files.
- Events stream (`events.ndjson`) for co-activity edges (create/modify/delete).
- Optional: tokenization of files for `shared_tokens` (Phase 2; configurable include patterns and size limits).

## Storage Strategy
- Phase 1: SQLite (stdlib `sqlite3`) file `.gnosis-flow/graph.db` with simple tables; in-memory cache for hot queries.
  - tables
    - nodes(id TEXT PRIMARY KEY, type TEXT, label TEXT, meta JSON)
    - edges(src TEXT, type TEXT, dst TEXT, weight REAL, count INTEGER, last_seen REAL, explain TEXT,
            PRIMARY KEY(src, type, dst))
    - ix_file_paths(path TEXT PRIMARY KEY, node_id TEXT)
    - meta(key TEXT PRIMARY KEY, value TEXT)
  - rationale: transactional, simple, no extra deps, good enough for tens of thousands of edges.
- Phase 2+: Optional on-disk indices for tokens, MinHash tables when enabled.

## Services & APIs
- HTTP (served by gnosis-flow runtime, optional auth same as existing console):
  - GET `/graph/neighbors?node=<id|path>&types=dir_sibling,import_dep&limit=20&min_w=0.1` → neighbors sorted by score with explanations.
  - GET `/graph/node?path=<relpath>` → node metadata, degree, top edges by type.
  - GET `/graph/edge-types` → list of types with descriptions.
  - GET `/graph/search?q=<term>&kind=file|term` (Phase 2) → fuzzy path or term lookup.
  - GET `/graph/why?src=<path>&dst=<path>` → edge breakdown and provenance.
- SSE (Phase 2): `/graph/stream` emits incremental edge updates.

## CLI / AHP / MCP Tools
- AHP (in-process) tools (exposed in `/tools`):
  - `graph.neighbors(node, types?, limit?, min_w?)` → list of neighbors with scores/explanations.
  - `graph.why(src, dst)` → edge provenance.
- MCP connector: extend `gnosis_flow/mcp/gnosis_flow_mcp.py` with:
  - `gf_graph_neighbors`, `gf_graph_why`, and optionally `gf_graph_node`.
- CLI (Typer):
  - `gnosis-flow graph neighbors <path> [--types ... --limit ...]`
  - `gnosis-flow graph why <src> <dst>`

## UI (Console)
- New collapsible panel “Graph” in `/console` with:
  - Input: path picker (current selection from events table), edge-type checkboxes, min weight slider.
  - Results: ranked neighbors with chips showing type and weight; hover for explanation.
  - Link-outs: open file in editor (if integration) or copy path.
  - Small sparkline showing recent co-activity per neighbor (optional).

## Configuration
- `.gnosis-flow/config.yaml` additions:
  - `graph.enabled: true`
  - `graph.edge_types: [dir_sibling, import_dep, co_activity]` (default)
  - `graph.shared_tokens.enabled: false`
  - `graph.shared_tokens.max_file_kb: 256`
  - `graph.co_activity.window_sec: 900`
  - `graph.decay.tau_sec: 86400` (per-type override allowed)
  - `graph.excludes: ['**/.git/**', '**/__pycache__/**', ...]`

## Performance & Limits
- Cap edges per node per type (e.g., top 200 by weight) with LRU trimming.
- Batch updates on timers (e.g., every 2s) rather than per-event writes.
- Lazy recompute: only update edges for touched files (event-driven) and nearby nodes.
- Optional background compaction to apply decay and trim stale edges.

## Security & Privacy
- Local-only by default (bind `127.0.0.1` like other services).
- No file contents exposed via HTTP except derived metadata and paths.
- Honor excludes; never tokenize or read files over size cap.

## Testing Strategy
- Unit tests:
  - Import graph extraction from Python files (fixtures with various import styles).
  - Dir sibling weighting across depths and folder sizes.
  - Co-activity windowing and decay math.
- Integration:
  - Populate small temp repo; simulate edits; assert neighbors evolve as expected.
  - HTTP endpoint tests for neighbors and why.
- UI:
  - Snapshot/smoke tests for panel rendering and filters.

## Telemetry & Metrics
- Count queries per endpoint/tool; average latency; cache hit ratio.
- Edge churn rate; total nodes/edges; distribution by type.
- Persist minimal metrics to `.gnosis-flow/graph_meta.json` or SQLite `meta` table.

## Rollout Plan
- Phase 0 (Scaffold):
  - Create SQLite schema, adapters, and minimal DAO layer.
  - Implement dir_sibling edges computation on-demand + cache.
  - Implement Python `import_dep` extraction and initial ingest.
  - HTTP: `/graph/neighbors`, `/graph/node`, `/graph/edge-types`.
  - AHP tool `graph.neighbors` and MCP `gf_graph_neighbors`.
  - Console panel MVP listing neighbors (no stream, no sparklines).
- Phase 1 (Live updates):
  - Co-activity ingestion from `events.ndjson` with window & decay.
  - `/graph/why` with explanations.
  - CLI commands for neighbors/why.
  - Basic SSE `/graph/stream` for UI to reflect changes.
- Phase 2 (Similarity & Terms):
  - Optional `shared_tokens` using MinHash. If `datasketch` is installed, use it; else fallback to simple token overlap for small files.
  - Term nodes from rules/keywords; `term_ref` edges.
  - UI filters by edge type; min weight slider; hover explanations.
- Phase 3 (Refinement):
  - Symbol-level nodes (Python functions/classes) when practical.
  - Ranking improvements, per-type tau, smarter decay.
  - Caching, compaction, and performance polish.

## Risks & Mitigations
- Performance on large repos → cap edges per node; batch writes; optional disabling of `shared_tokens`.
- Path normalization across OSes → centralize in a `paths` utility; store POSIX-style.
- Noisy folders (e.g., vendored code) → rely on existing excludes; allow graph-specific excludes.
- Poor import coverage outside Python → declare as non-goal initially; design pluggable extractors.

## Open Questions / Decisions Needed
1. Dependencies:
   - Approve optional `datasketch` for MinHash? If not, stick to fallback token overlap (slower/naive) only on small files.
   - Allow optional `networkx` for ad-hoc analysis in tests/dev only?
2. Storage:
   - SQLite acceptable for `.gnosis-flow/graph.db`? Any preference for DuckDB?
3. API Shape:
   - Any additional endpoints needed (e.g., `/graph/components`, `/graph/suggest-tests`)?
   - Response size limits and truncation defaults?
4. Tools Exposure:
   - Confirm AHP names: `graph.neighbors`, `graph.why`. Any others (e.g., `graph.touch_related`)?
   - MCP tool namespace and parameter schema OK? Prefer streaming responses?
5. UI:
   - Where to place the panel in `/console` layout? Default open or closed?
   - Do we want a mini-force layout preview, or keep to list for now?

## Definition of Done (Epic)
- Phase 1 completed and documented:
  - SQLite-backed graph with `dir_sibling`, `import_dep`, `co_activity` edges.
  - HTTP: `/graph/neighbors`, `/graph/node`, `/graph/edge-types`, `/graph/why`.
  - AHP tool and MCP endpoints for neighbors/why available and documented.
  - Console panel MVP usable with filters and explanations.
  - Tests for extractors, weights, endpoints pass in CI.
  - README and `/console` help updated; config options documented.

## Implementation Notes
- Keep code in `gnosis_flow/graph/` module with submodules:
  - `store.py` (SQLite), `builder.py` (extractors, weighting), `service.py` (HTTP/SSE), `tools.py` (AHP), `mcp.py` (MCP handlers), `ui/` (panel assets if needed).
- Extend existing runtime (`runtime.py`) router to mount `/graph/*` endpoints with minimal coupling.
- Reuse existing events ingestion; add a small co-activity index updated on file events.
- Avoid long-running scans; compute lazily and cache; respect excludes and size caps.

---

Appendix A: Minimal Import Extraction (Python)
- Parse `.py` using `ast.parse`; collect `import` and `from import` targets; resolve relative imports to file paths using `sys.path`-like resolver anchored to repo root; best-effort only.
- Store edges `file:A.py -> file:B.py` with count aggregated across occurrences.

Appendix B: Co-Activity Windowing
- Maintain per-file ring buffer of recent modification timestamps.
- For each event of file X at time t, for files Y modified within `[t - W, t]`, increment co-activity count for edge {X, Y} and set `last_seen=t`.
- Periodically apply decay and trim edges below threshold.

Appendix C: Shared Tokens (Optional)
- Tokenize source files with simple regex `[A-Za-z_][A-Za-z0-9_]+`, lowercase, drop stopwords.
- Shingle size `k=5` tokens; MinHash with 128 permutations if `datasketch` is present; else compute overlap ratio for small files only.
