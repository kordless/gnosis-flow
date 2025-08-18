# Gnosis Flow

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/release/python-390/)
[![PyPI version](https://badge.fury.io/py/gnosis-flow.svg)](https://badge.fury.io/py/gnosis-flow)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Build Status](https://travis-ci.org/kordless/gnosis-flow.svg?branch=main)](https://travis-ci.org/kordless/gnosis-flow)

Gnosis Flow is a powerful, asynchronous file and log watcher that triggers actions based on configurable rules. It's designed to be a flexible and extensible tool for developers to automate tasks and workflows.

## Features

*   **Asynchronous Monitoring:** Lightweight and efficient, using an async poll-based approach.
*   **File and Log Watching:** Monitor directories for file changes and tail log files for new lines.
*   **Pluggable Actions:** Trigger custom actions, including AI tool calls, shell commands, and notifications.
*   **Runtime Control:** Add new files and directories to watch at runtime via a local control server.
*   **Configurable Rules:** Define rules in YAML to match file events and log lines with specific actions.
*   **CLI Interface:** A simple and intuitive command-line interface for starting, stopping, and managing the monitor.
*   **Daemon Mode:** Run the monitor as a background process.

## Installation

You can install Gnosis Flow from PyPI:

```bash
pip install gnosis-flow
```

Or, for development, you can install it from the source directory:

```bash
git clone https://github.com/kordless/gnosis-flow.git
cd gnosis-flow
pip install -e .
```

## Quick Start

1.  **Install the dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

2.  **Start the monitor in the current directory:**

    ```bash
    gnosis-flow start --dir .
    ```

    This will create a `.gnosis-flow/` directory in your project and start the control server on `127.0.0.1:8765`.

3.  **In another terminal, you can now interact with the monitor:**

    *   **Add a log file to watch:**

        ```bash
        gnosis-flow add-log ./app.log
        ```

    *   **Add a directory to watch:**

        ```bash
        gnosis-flow add-watch ./another/dir
        ```

    *   **Check the status of the monitor:**

        ```bash
        gnosis-flow status
        ```

    *   **Stop the monitor:**

        ```bash
        gnosis-flow stop
        ```

## Usage

The `gnosis-flow` command-line interface provides the following commands:

*   `start`: Start the monitor.
*   `stop`: Stop the monitor.
*   `status`: Get the status of the monitor.
*   `add-log`: Add a log file to watch.
*   `add-watch`: Add a directory to watch.

For more information on each command, you can use the `--help` flag:

```bash
gnosis-flow start --help
```

## Configuration

Gnosis Flow is configured using a `rules.yaml` file located in the `.gnosis-flow/` directory. This file is automatically created when you start the monitor for the first time.

The `rules.yaml` file allows you to define rules that match file events and log lines with specific actions. Here's an example of a rule that triggers a shell command when a Python file is modified:

```yaml
- on: file.modified
  glob: "**/*.py"
  action:
    type: shell
    command: "echo 'File modified: {{ file_path }}'"
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
