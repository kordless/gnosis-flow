from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict


def _state_dir() -> Path:
    p = os.environ.get("GNOSIS_FLOW_STATE_DIR")
    if p:
        return Path(p)
    # fallback: current project
    return Path.cwd() / ".gnosis-flow"


def _usage_path() -> Path:
    return _state_dir() / "tools_usage.json"


def increment_tool_usage(name: str, success: bool = True) -> None:
    path = _usage_path()
    try:
        data: Dict[str, Dict[str, int]] = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        entry = data.get(name, {"success": 0, "error": 0})
        if success:
            entry["success"] = entry.get("success", 0) + 1
        else:
            entry["error"] = entry.get("error", 0) + 1
        data[name] = entry
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        # ignore metrics failures
        pass


def get_tool_usage() -> Dict[str, Dict[str, int]]:
    path = _usage_path()
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

