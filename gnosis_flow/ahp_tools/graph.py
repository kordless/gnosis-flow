from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from ..ahp_compat import tool, ValidationError


def _get_manager():
    try:
        from ..util import project_root_from_cwd, ensure_state_dir
        from ..graph.store import GraphManager
        state_dir_env = os.environ.get("GNOSIS_FLOW_STATE_DIR")
        if state_dir_env:
            state_dir = Path(state_dir_env)
            # best-effort root guess: parent of state dir
            root = state_dir.parent
        else:
            root = project_root_from_cwd()
            state_dir = ensure_state_dir(root)
        return GraphManager(root=root, state_dir=state_dir)
    except Exception as e:
        raise ValidationError(f"graph manager unavailable: {e}")


@tool(name="graph.neighbors", description="Get related files by graph edges")
def graph_neighbors(node: str, types: Optional[str] = None, limit: int = 20, min_w: float = 0.0):
    mgr = _get_manager()
    tlist = [t.strip() for t in types.split(",") if t.strip()] if types else None
    return mgr.neighbors_for_path(node, types=tlist, min_w=min_w, limit=limit)


@tool(name="graph.why", description="Explain relationship between two files")
def graph_why(src: str, dst: str):
    mgr = _get_manager()
    return mgr.why(src, dst)

