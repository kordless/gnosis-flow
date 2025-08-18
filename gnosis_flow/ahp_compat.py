from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, Optional


class BaseTool:
    name: str
    description: str

    def run(self, **kwargs):  # override as needed
        raise NotImplementedError


class FunctionTool(BaseTool):
    def __init__(self, func: Callable, name: Optional[str] = None, description: Optional[str] = None):
        self.func = func
        self.name = name or func.__name__
        self.description = description or inspect.getdoc(func) or ""

    def run(self, **kwargs):
        return self.func(**kwargs)


class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self.tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self.tools.get(name)


_GLOBAL_REGISTRY: Optional[ToolRegistry] = None


def get_global_tool_registry() -> ToolRegistry:
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = ToolRegistry()
        # auto-register built-ins
        try:
            from .ahp_tools import echo  # noqa: F401
        except Exception:
            pass
    return _GLOBAL_REGISTRY


def tool(name: Optional[str] = None, description: Optional[str] = None):
    def deco(func: Callable):
        t = FunctionTool(func, name=name, description=description)
        get_global_tool_registry().register(t)
        return func
    return deco

