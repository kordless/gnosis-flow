<div align="center">
  <h1>Gnosis Flow</h1>
  <h3>Supercharge Your Development with AI-Powered Insights</h3>
</div>

<div align="center">

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/release/python-390/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

</div>

**Gnosis Flow is not just another file watcher. It's an intelligent, AI-powered development assistant that gives your LLM agents the tools they need to understand, analyze, and interact with your codebase in real-time.**

Imagine an AI that can not only see your code but also understand its structure, its dependencies, and its runtime behavior. An AI that can identify potential issues, suggest improvements, and even take action to fix problems before they happen. This is the power of Gnosis Flow.

![Flow Diagram](flow.png)

## The Vision: The Future of AI-Powered Development

Gnosis Flow is more than just a tool; it's a glimpse into the future of software development. A future where AI agents are not just code completion engines but active collaborators in the creative process. A future where your AI can:

*   **Proactively identify and fix bugs:** By monitoring your logs and file changes, Gnosis Flow can spot anomalies and trigger actions to fix them before they impact your users.
*   **Perform automated security audits:** Gnosis Flow can be taught to recognize security vulnerabilities and alert you to them in real-time.
*   **Ensure code quality and consistency:** By enforcing coding standards and best practices, Gnosis Flow can help you maintain a high-quality codebase.
*   **Onboard new developers in record time:** Gnosis Flow can provide new team members with a deep understanding of the codebase, its history, and its architecture.

## The AI Agent Tool System

The heart of Gnosis Flow is its powerful and extensible tool system. This system allows you to create custom tools that can be used by your AI agents to interact with your codebase in new and exciting ways. These tools can be used to:

*   **Read and write files:** Give your AI the ability to read and modify your code directly.
*   **Execute shell commands:** Allow your AI to run tests, build your project, and even deploy it to production.
*   **Interact with APIs:** Connect your AI to external services and APIs to extend its capabilities.
*   **Analyze your code:** Create custom tools to analyze your code for everything from performance bottlenecks to security vulnerabilities.

With Gnosis Flow, you are not just writing code; you are building an intelligent system that can help you write better code, faster.

## Key Features

*   **Real-time File and Log Monitoring:** Gnosis Flow watches your files and logs for changes and triggers actions in real-time.
*   **Live Browser and CLI Consoles:** Get a live view of your project's activity through a web browser or your command line.
*   **In-Process Tools:** Create custom tools that can be used by your AI agents to interact with your codebase.
*   **Code Relationship Graph:** Understand the relationships between your files and modules with a powerful graph visualization tool.
*   **Extensible Rule Engine:** Define custom rules to trigger actions based on specific file changes or log messages.

## Getting Started

Ready to unlock the power of AI-powered development? Here's how to get started with Gnosis Flow:

### Installation

```bash
pip install gnosis-flow
```

### Running Gnosis Flow

```bash
gnosis-flow start --dir . --http
```

This will start the Gnosis Flow monitor and the HTTP console. You can then access the live console at `http://127.0.0.1:8766/console`.

CLI reference: see `CLI_COMMANDS.md` in this folder for all commands and options.

### Ports and Endpoints

```
           CLI (TCP)                          Web (HTTP)
   +------------------------+        +--------------------------+
   |  Control Server        |        |  HTTP Server             |
   |  --control-host:port   |        |  --http-host:port        |
   |  default: 127.0.0.1:8765|       |  default: 127.0.0.1:8766 |
   +-----------+------------+        +-------------+------------+
               ^                                 ^
               |                                 |
   gnosis-flow status/add-watch/...    Browser: http://127.0.0.1:8766/console
                                       API:     http://127.0.0.1:8766/graph/...
```

Tip: If you bind to `0.0.0.0`, use `127.0.0.1` in URLs.

### Graph Panel (in the console)
- Enter a file path, choose edge types (imports, siblings, similarity, co-activity, terms), set a min weight and limit, then Query.
- Results list shows related files with type chips, weights, and an explanation.

### Indexing (pre‑warm the graph)
- Windows PowerShell with progress/ETA:
  - `PowerShell -ExecutionPolicy Bypass -File .\scripts\index-graph.ps1`
- Notes: co-activity is live only; siblings are on-demand; you can rerun after large edits.

### HTTP examples
- PowerShell:
  - `Invoke-WebRequest "http://127.0.0.1:8766/graph/neighbors?path=gnosis_flow/cli.py&types=import_dep&min_w=0.1&limit=10" | Select-Object -Expand Content`
- curl:
  - `curl -s "http://127.0.0.1:8766/graph/edge-types"`

### MCP tools (optional)
- Use `gnosis-evolve/tools/flow_graph.py` as an MCP server; then call:
  - `graph_set_base(base_url)` once per session
  - `graph_neighbors`, `graph_why`, `graph_node`, `graph_edge_types`, `graph_search`

## The Gnosis Flow Ecosystem

Gnosis Flow is part of a larger ecosystem of tools designed to help you build better software with AI. Check out our other projects:

*   **Gnosis Evolve:** A powerful tool for evolving your codebase with the help of AI.
*   **Gnosis AHP:** A framework for building and running AI-powered tools.

## Contributing

We welcome contributions from the community! If you have an idea for a new feature or a bug fix, please open an issue or submit a pull request on our [GitHub repository](https://github.com/kordless/gnosis-flow).

## License

Gnosis Flow is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
### Customizing the Console (Templating)

You can override the built‑in console by placing files under `.gnosis-flow/console/`:

- `.gnosis-flow/console/index.html`  (HTML template)
- `.gnosis-flow/console/console.css` (styles)
- `.gnosis-flow/console/console.js`  (scripts)

The server will serve these instead of the defaults. The HTML supports a minimal placeholder:

- `{{TITLE}}` → replaced with `Gnosis Flow · Live Console`

Restart the server after changing files. This lets you theme or extend the console without modifying the package.
