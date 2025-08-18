Gnosis-Flow Monitor (Python, async)

Purpose
- Watch directories for file changes and tail log files.
- Trigger pluggable actions (including AI tool calls) on events.
- Allow adding log files and watches at runtime via a local control server.

Installation
- From PyPI (main):
  - `pip install gnosis-flow`
- From this directory (development):
  - `cd gnosis-flow`
  - `pip install -e .`

Quick Start
- Install: `pip install -r requirements.txt`
- Start (single-project mode): `python -m gnosis_flow.cli start --dir .`
  - Creates `.gnosis-flow/` under the project; offers to add it to `.gitignore`.
  - Control server on `127.0.0.1:8765` by default.
  - Add logs at runtime: `python -m gnosis_flow.cli add-log ./app.log`
- While running, in another terminal:
  - Add log: `python -m gnosis_flow.cli add-log ./other.log`
  - Add watch: `python -m gnosis_flow.cli add-watch ./another/dir`
  - Status: `python -m gnosis_flow.cli status`
  - Stop: `python -m gnosis_flow.cli stop`

After pip install (entry point)
- `gnosis-flow start --dir .`
- Add: `gnosis-flow add-log ./app.log`
- Status: `gnosis-flow status`
- Stop: `gnosis-flow stop`

Daemon mode
- `python -m gnosis_flow.cli start --daemon --yes`
- Logs to `.gnosis-flow/monitor.log` and runs in the background (UNIX).

Design
- Async poll-based watchers to avoid external dependencies.
- Control server: simple JSON over TCP (`127.0.0.1:8765`) for runtime commands.
- Hooks: `on_file_event` and `on_log_line` are where you route to actions.
- Rules: YAML-based matching in `.gnosis-flow/rules.yaml` (auto-created) with regex and fuzzy terms.
- Fuzzy matching uses RapidFuzz when available (falls back to difflib).

Config (planned)
- YAML/JSON config for rules like:
  - `on: file.modified` with `glob: "**/*.py"` → action `ai_lint`/`shell`.
  - `on: log.line` with `match: "ERROR"` → action `notify`.

Notes
- This is a foundation; it runs without extra deps and can be extended with FastAPI or watchfiles.
