from __future__ import annotations

from typing import Any, Dict


def _render_value(val: Any, ctx: Dict[str, Any]) -> Any:
    if isinstance(val, str):
        out = val
        for k, v in ctx.items():
            if isinstance(v, (str, int, float)):
                out = out.replace("{{" + k + "}}", str(v))
        # Also expose nested known keys
        hit = ctx.get("hit") or {}
        for k, v in (hit.items() if isinstance(hit, dict) else []):
            if isinstance(v, (str, int, float)):
                out = out.replace("{{" + k + "}}", str(v))
        return out
    elif isinstance(val, dict):
        return {k: _render_value(v, ctx) for k, v in val.items()}
    elif isinstance(val, list):
        return [_render_value(x, ctx) for x in val]
    return val


def render_args(args: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Render {{placeholders}} in action args using context fields.

    Context exposes top-level keys like path, line, rule, and nested hit.* keys from rule hits.
    """
    return _render_value(args, context)  # type: ignore

