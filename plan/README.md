# 🌌 Gnosis-Flow

**Gnosis-Flow** is a **real AI orchestration framework** written in Python.  
It provides a secure, transparent way to coordinate multiple AI agents, manage tasks, persist state, and deploy locally or in the cloud.  

Unlike “theater props” masquerading as enterprise AI, Gnosis-Flow is designed to be:  
- **Truthful** – every tool backed by real functionality  
- **Modular** – agents, tasks, workflows, memory, integrations kept clean and composable  
- **Secure** – no `eval()`, no arbitrary shell exec, no hidden key collection  
- **Deployable** – runs on your laptop or as a service on Google Cloud Run  

---

## ✨ Features
- **Agent orchestration** – spawn, list, and coordinate async Python agents  
- **Task workflows** – run tasks directly or define DAG-style workflows  
- **Hooks system** – register pre/post hooks for tasks, edits, or workflows  
- **Memory persistence** – JSON-based storage by default (no SQL); pluggable backends (local files or Google Cloud Storage)  
- **Neural adapters** – integrate real models via Hugging Face, scikit-learn, or APIs  
- **CLI-first** – the command-line tool is `flow`  

---

## 🖥️ CLI Usage
```bash
# Initialize a project
flow init

# Spawn a swarm of agents
flow agents spawn --count 3 --role "developer"

# Run a task
flow task run "build a REST API"

# Query memory
flow memory query "last 10 completed tasks"

# Deploy to Google Cloud Run
flow deploy cloud
```

---

## 📂 Project Structure
```
gnosis_flow/
├── cli/             # CLI commands (typer)
├── core/            # Agents, tasks, workflows
├── memory/          # JSON store + GCS adapter
├── neural/          # Real ML/LLM integrations
├── hooks/           # Hook registry
├── integrations/    # External service adapters
└── docs/            # Documentation
```

---

## 📦 Storage
- **Local**: JSON files under `.gnosis/`  
- **Cloud**: Google Cloud Storage bucket for persistence when running on Cloud Run  

---

## 🚀 Deployment
- **Local**: run `flow start` to launch locally with JSON storage  
- **Cloud**: build and push Docker image → deploy to Google Cloud Run with `flow deploy cloud`  

---

## 🛠️ Development Tasks

### Phase 1 – Core Framework
- [ ] Agent class with async task loop  
- [ ] SwarmManager (spawn, list, terminate agents)  
- [ ] JSON memory store (read/write tasks, logs)  
- [ ] CLI scaffold with `typer`  

### Phase 2 – Workflows & Hooks
- [ ] Task object (status, metadata)  
- [ ] Workflow DAG executor (via `networkx`)  
- [ ] Hook system (pre/post task, pre/post edit)  

### Phase 3 – Neural Adapters
- [ ] Hugging Face integration (text inference)  
- [ ] Scikit-learn example models (classification/regression)  
- [ ] Optional API integrations (OpenAI/Anthropic)  

### Phase 4 – Cloud Integration
- [ ] Google Cloud Storage adapter for memory  
- [ ] Google Cloud Run deploy commands in CLI  

### Phase 5 – Production Hardening
- [ ] Auth & config management  
- [ ] Logging & metrics  
- [ ] Documentation & examples  

---

## ⚖️ License
MIT License.  
