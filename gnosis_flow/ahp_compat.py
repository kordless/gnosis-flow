from __future__ import annotations

import importlib.util
import inspect
import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union


logger = logging.getLogger("gnosis_flow.tools")


class ToolError(Exception):
    pass


class ValidationError(Exception):
    pass


class BaseTool:
    name: str
    description: str
    parameters: Dict[str, Dict[str, Any]]  # name -> {type, required, default}

    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def run(self, **kwargs):  # override as needed
        raise NotImplementedError


class FunctionTool(BaseTool):
    def __init__(self, func: Callable, name: Optional[str] = None, description: Optional[str] = None,
                 parameters: Optional[Dict[str, Dict[str, Any]]] = None):
        self.func = func
        self.name = name or func.__name__
        self.description = description or inspect.getdoc(func) or ""
        if parameters is not None:
            self.parameters = parameters
        else:
            # Infer simple schema from signature
            self.parameters = {}
            sig = inspect.signature(func)
            for pname, param in sig.parameters.items():
                if pname == "self":
                    continue
                ann = param.annotation if param.annotation is not inspect._empty else str
                ptype = getattr(ann, "__name__", str(ann)) if not isinstance(ann, str) else ann
                required = (param.default is inspect._empty)
                default = None if required else param.default
                self.parameters[pname] = {"type": str(ptype), "required": required, "default": default}

    def run(self, **kwargs):
        return self.func(**kwargs)


RESERVED_NAMES: Set[str] = {
    "auth", "openapi", "schema", "session", "human_home",
    "robots.txt", "health", "static", "docs", "redoc"
}
RESERVED_PATTERN = re.compile(r"^(auth|openapi|schema|session|docs|redoc|health)(\/.*)?$")


class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Dict[str, Any]] = {}  # name -> {instance, schema, category}
        self.categories: Dict[str, Set[str]] = {}

    def is_reserved(self, name: str) -> bool:
        return name in RESERVED_NAMES or RESERVED_PATTERN.match(name) is not None

    def register(self, tool_obj: Union[BaseTool, Callable, type], category: Optional[str] = None,
                 override: bool = False) -> None:
        if callable(tool_obj) and not isinstance(tool_obj, BaseTool):
            tool_instance = FunctionTool(tool_obj) if not (inspect.isclass(tool_obj) and issubclass(tool_obj, BaseTool)) else tool_obj()
        else:
            tool_instance = tool_obj

        if not isinstance(tool_instance, BaseTool):
            raise ToolError(f"Invalid tool type: {type(tool_instance)}")

        if self.is_reserved(tool_instance.name):
            raise ToolError(f"Tool name '{tool_instance.name}' is reserved.")

        if tool_instance.name in self.tools and not override:
            raise ToolError(f"Tool '{tool_instance.name}' already registered.")

        # validate schema
        schema = tool_instance.get_schema()
        if not schema.get("name") or not schema.get("description"):
            raise ValidationError("Tool must have name and description.")

        self.tools[tool_instance.name] = {
            "instance": tool_instance,
            "schema": schema,
            "category": category or "general",
        }
        self.categories.setdefault(category or "general", set()).add(tool_instance.name)
        logger.info(f"Registered tool: {tool_instance.name} (category: {category or 'general'})")

    def get_tool(self, name: str) -> BaseTool:
        if name not in self.tools:
            raise ToolError(f"Tool '{name}' not found")
        return self.tools[name]["instance"]

    def get_schemas(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        if category:
            names = self.categories.get(category, set())
            return [self.tools[n]["schema"] for n in names if n in self.tools]
        return [v["schema"] for v in self.tools.values()]

    def get_categories(self) -> List[str]:
        return sorted(self.categories.keys())

    def discover_tools(self, path: Union[str, Path], strict: bool = False) -> List[Dict[str, Any]]:
        path = Path(path)
        discovered: List[Dict[str, Any]] = []
        files = [path] if path.is_file() else list(path.glob("**/*.py"))
        for py in files:
            if py.name in ("__init__.py", "base.py", "tool_registry.py") or py.name.startswith("test_"):
                continue
            # track pre-existing tools
            before = set(self.tools.keys())
            try:
                # If this is our built-in package path, prefer package import to preserve relative imports
                pkg_ahp_tools = (Path(__file__).parent / "ahp_tools").resolve()
                if py.parent.resolve() == pkg_ahp_tools:
                    mod_name = f"gnosis_flow.ahp_tools.{py.stem}"
                    importlib.import_module(mod_name)
                else:
                    spec = importlib.util.spec_from_file_location(f"local_tools.{py.stem}", py)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)  # type: ignore
                # any tools registered by decorator are now present; set category for new ones
                after = set(self.tools.keys())
                newly = after - before
                for name in newly:
                    self.tools[name]["category"] = py.stem
                    self.categories.setdefault(py.stem, set()).add(name)
                    discovered.append(self.tools[name]["schema"])
            except Exception as e:
                msg = f"Could not load tools from {py}: {e}"
                if strict:
                    raise ToolError(msg)
                logger.error(msg, exc_info=True)
        return discovered


_GLOBAL_REGISTRY: Optional[ToolRegistry] = None


def get_global_registry() -> ToolRegistry:
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = ToolRegistry()
        # discover built-ins
        try:
            builtin_dir = Path(__file__).parent / "ahp_tools"
            _GLOBAL_REGISTRY.discover_tools(builtin_dir, strict=False)
        except Exception:
            pass
    return _GLOBAL_REGISTRY


def tool(name: Optional[str] = None, description: Optional[str] = None, parameters: Optional[Dict[str, Dict[str, Any]]] = None):
    def deco(func: Callable):
        t = FunctionTool(func, name=name, description=description, parameters=parameters)
        get_global_registry().register(t)
        return func
    return deco


def validate_args(schema: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """Validate/coerce args based on tool schema. Raises ValidationError on mismatch."""
    params = schema.get("parameters", {}) or {}
    out: Dict[str, Any] = {}
    for pname, meta in params.items():
        required = bool(meta.get("required"))
        ptype = (meta.get("type") or "str").lower()
        if pname in args:
            val = args[pname]
        else:
            if required and "default" not in meta:
                raise ValidationError(f"Missing required parameter: {pname}")
            val = meta.get("default")
        # simple coercion
        try:
            if val is None:
                coerced = None
            elif ptype in ("str", "string"):
                coerced = str(val)
            elif ptype in ("int", "integer"):
                coerced = int(val)
            elif ptype in ("float", "number"):
                coerced = float(val)
            elif ptype in ("bool", "boolean"):
                if isinstance(val, bool):
                    coerced = val
                elif str(val).lower() in ("1", "true", "yes", "y"): coerced = True
                elif str(val).lower() in ("0", "false", "no", "n"): coerced = False
                else:
                    raise ValueError("invalid boolean")
            else:
                coerced = val
        except Exception as e:
            raise ValidationError(f"Parameter '{pname}' expected {ptype}: {e}")
        out[pname] = coerced
    # Keep passthrough extras
    for k, v in args.items():
        if k not in out:
            out[k] = v
    return out
