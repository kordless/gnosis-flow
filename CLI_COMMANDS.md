# Gnosis Flow CLI Commands

This is a concise reference for all `gnosis-flow` commands and common options. Examples use Windows PowerShell; replace paths as needed.

## Monitor Commands

- start: Run the monitor in a project directory (with optional HTTP console)
  - `gnosis-flow start --dir . --http --host 0.0.0.0 --http-port 8766`
  - Options:
    - `--dir PATH` project root (creates `.gnosis-flow/` there)
    - `--host HOST` control/HTTP bind address
    - `--port N` control server port (default 8765)
    - `--http` enable HTTP console
    - `--http-port N` HTTP port (default 8766)
    - `--poll SECONDS` file polling interval (default 1.0)
    - `--daemon` run as a background process (POSIX only)

- add-log: Tail a log file in the running monitor
  - `gnosis-flow add-log .\\app.log`

- add-watch: Add a directory to watch for file changes
  - `gnosis-flow add-watch .\\src`

- status: Show current watched dirs/logs and counters
  - `gnosis-flow status`

- stop: Ask the running monitor to stop
  - `gnosis-flow stop`

## Tools Introspection

- tools list: List available in-process tools (name, description, category)
  - `gnosis-flow tools list`

- tools info: Show schema for a specific tool
  - `gnosis-flow tools info echo.text`

## Graph Commands

- graph neighbors: List related files by edge type(s)
  - `gnosis-flow graph neighbors .\\path\\to\\file.py --types import_dep --limit 20`
  - Options:
    - `--types` comma-separated edge types (e.g., `import_dep,shared_tokens,dir_sibling,co_activity,term_ref`)
    - `--min-w` minimum weight filter (e.g., `0.2`)
    - `--limit` max results (default 20)

- graph why: Explain edges between two files
  - `gnosis-flow graph why .\\path\\to\\a.py .\\path\\to\\b.py`

- graph node: Show node metadata and degree by edge type
  - `gnosis-flow graph node .\\path\\to\\file.py`

## Indexing (Pre‑warm)

You can quickly materialize graph edges across a repo (imports, tokens, terms):

- PowerShell script with progress/ETA (recommended on Windows)
  - `PowerShell -ExecutionPolicy Bypass -File .\\scripts\\index-graph.ps1`
  - Options: `-Types "import_dep,shared_tokens,term_ref" -Limit 1 -Include "*.py" -Dir "."`

## HTTP Endpoints (for scripts)

- `/graph/neighbors?path=<rel|abs>&types=...&min_w=...&limit=...`
- `/graph/why?src=<path>&dst=<path>`
- `/graph/node?path=<path>`
- `/graph/edge-types`
- `/graph/search?q=<substring>&limit=20`
- `/graph/metrics`

## Tips

- Excludes: set extra excludes in `.gnosis-flow/config.yaml` (`exclude_names:`) and graph settings under `graph:`.
- Multi-repo: run a separate `gnosis-flow start --dir <repo>` per repository on distinct ports.
- MCP users: use the `gnosis-evolve/tools/flow_graph.py` MCP server and call `graph_set_base` once per session.
