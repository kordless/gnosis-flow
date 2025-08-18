from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict


def action_notify(payload: Dict[str, Any]) -> None:
    print("[notify]", json.dumps(payload, ensure_ascii=False)[:2000])


def action_shell(payload: Dict[str, Any]) -> None:
    # Stub: intentionally disabled by default for safety
    print("[shell-disabled]", json.dumps(payload)[:500])


def action_ai_tool(payload: Dict[str, Any]) -> None:
    # Placeholder: wire to real provider later
    # Expect keys: provider, model, prompt; plus match context
    act = payload.get("action", {})
    print(f"[ai_tool] provider={act.get('provider')} model={act.get('model')} prompt={len(act.get('prompt',''))} chars")


def dispatch(action: Dict[str, Any], context: Dict[str, Any]) -> None:
    typ = (action or {}).get("type", "notify")
    payload = {"action": action, **context}
    if typ == "notify":
        action_notify(payload)
    elif typ == "shell":
        action_shell(payload)
    elif typ == "ai_tool":
        action_ai_tool(payload)
    else:
        action_notify({"action": {"type": "unknown"}, **context})

