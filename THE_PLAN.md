# 🧭 Gnosis-Flow Development Plan

## 1. Core Principles
- **Truthful**: every tool has real functionality, no mocks-as-theater.
- **Modular**: small, composable Python modules (agents, tasks, memory, orchestration).
- **Secure**: no `eval()`, no hidden API key collection, sandboxed subprocess handling.
- **Deployable**: designed for both local use and Google Cloud Run deployments.

---

## 2. Architecture Overview
```
gnosis_flow/
├── cli/                # CLI (`flow`) commands
├── core/               # Agents, tasks, workflows, orchestration
├── memory/             # JSON local store + Google Cloud Storage adapter
├── neural/             # Real ML integrations (HF, sklearn, APIs)
├── hooks/              # Pre/post execution hooks
├── integrations/       # External services (GitHub, Slack, etc.)
└── docs/               # Documentation
```

---

## 3. Subsystems

### Agent Orchestration
- `Agent` class with unique ID, role, and async task loop.
- `SwarmManager` for spawning, listing, and terminating agents.
- Communication via `asyncio` events.

### Tasks & Workflows
- `Task` object with state machine (pending, running, complete, failed).
- `Workflow` as DAG of tasks with dependencies.
- Execution engine powered by `networkx` or custom DAG runner.

### Memory System
- Default: JSON files stored locally in `.gnosis/`.
- Cloud: Google Cloud Storage adapter (read/write JSON blobs).
- API: `MemoryStore.save()`, `MemoryStore.query()`, `MemoryStore.delete()`.

### Neural Tools
- Hugging Face transformer inference.
- Simple scikit-learn models for quick classification/regression demos.
- Optional adapters for OpenAI/Anthropic APIs (configurable).

### Hook System
- Pre/post task, pre/post edit hooks.
- Decorator-based registration: `@hook("pre_task")`.

### CLI (flow)
- Built with `typer` for ergonomic command-line usage.
- Commands:
  - `flow init`
  - `flow agents spawn`
  - `flow task run`
  - `flow memory query`
  - `flow deploy cloud`

### Integrations
- GitHub (via PyGithub).
- Slack (via slack_sdk).
- Others pluggable via `integrations/`.

---

## 4. Security Model
- Explicit `.env` config for API keys.
- No implicit network calls.
- Subprocess calls sandboxed with `subprocess.run(..., check=True, shell=False)`.

---

## 5. Development Roadmap

### Phase 1 – Core Framework
- Implement Agent, SwarmManager.
- JSON-based memory store.
- CLI scaffold.

### Phase 2 – Workflows & Hooks
- Task object with metadata and status.
- Workflow executor (DAG).
- Hook registry.

### Phase 3 – Neural Adapters
- Hugging Face model inference.
- scikit-learn model demos.
- Optional LLM API integration.

### Phase 4 – Cloud Integration
- Google Cloud Storage adapter.
- CLI deployment command to Cloud Run.

### Phase 5 – Production Hardening
- Config management.
- Logging and metrics.
- Documentation and usage examples.

---

## 6. Recommended Libraries
- CLI: `typer`
- Async: `asyncio`
- Storage: `json`, `google-cloud-storage`
- Workflows: `networkx`
- ML: `transformers`, `torch`, `scikit-learn`
- Integrations: `requests`, `slack_sdk`, `PyGithub`

---

## ✅ Bottom Line
Gnosis-Flow is a **real orchestration framework**:  
- Async agents and swarms.  
- JSON persistence locally or in Google Cloud Storage.  
- Real ML integrations.  
- CLI-first experience.  
- Secure and deployable both locally and in the cloud.
