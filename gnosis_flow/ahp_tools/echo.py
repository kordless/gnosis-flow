from __future__ import annotations

from ..ahp_compat import tool


@tool(name="echo.text", description="Echo back provided text with optional prefix")
def echo_text(text: str, prefix: str = "") -> str:
    return f"{prefix}{text}"


@tool(name="file.append_line", description="Append a line to a file (UTF-8)")
def append_line(path: str, line: str) -> str:
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return f"appended to {path}"

