from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any, Dict

from .templating import render_args


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


def _get_ahp_registry():
    # Try gnosis-ahp first
    try:
        from gnosis_ahp.tools.tool_registry import get_global_tool_registry  # type: ignore

        return get_global_tool_registry()
    except Exception:
        pass
    # Fallback to internal lightweight registry
    try:
        from .ahp_compat import get_global_tool_registry  # type: ignore

        return get_global_tool_registry()
    except Exception as e:
        raise RuntimeError("No AHP-compatible tool registry available") from e


def action_ahp_tool(payload: Dict[str, Any]) -> None:
    act = payload.get("action", {}) or {}
    name = act.get("name")
    raw_args = act.get("args", {}) or {}
    if not name:
        print("[ahp_tool] missing 'name' in action")
        return
    try:
        # Render args from context
        args = render_args(raw_args, payload)
        reg = _get_ahp_registry()
        tool = reg.get_tool(name)
        if tool is None:
            print(f"[ahp_tool] tool not found: {name}")
            return
        fn = getattr(tool, "run", None) or getattr(tool, "__call__", None)
        if fn is None:
            print(f"[ahp_tool] tool has no callable interface: {name}")
            return
        if inspect.iscoroutinefunction(fn):
            # Run async tool
            try:
                loop = asyncio.get_running_loop()
                fut = loop.create_task(fn(**args))
                fut.add_done_callback(lambda f: print(f"[ahp_tool] {name} -> {str(f.result())[:500]}"))
            except RuntimeError:
                # No loop: run synchronously
                res = asyncio.run(fn(**args))
                print(f"[ahp_tool] {name} -> {str(res)[:500]}")
        else:
            res = fn(**args)
            print(f"[ahp_tool] {name} -> {str(res)[:500]}")
    except Exception as e:
        print(f"[ahp_tool] error: {e}")


def dispatch(action: Dict[str, Any], context: Dict[str, Any]) -> None:
    typ = (action or {}).get("type", "notify")
    payload = {"action": action, **context}
    if typ == "notify":
        action_notify(payload)
    elif typ == "shell":
        action_shell(payload)
    elif typ == "ai_tool":
        action_ai_tool(payload)
    elif typ == "ahp_tool":
        action_ahp_tool(payload)
    else:
        action_notify({"action": {"type": "unknown"}, **context})
