import os
from pathlib import Path

from gnosis_flow.graph.store import GraphManager


def write(p: Path, txt: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")


def test_graph_neighbors_import_and_siblings(tmp_path: Path):
    # layout
    # proj/
    #   pkg/__init__.py
    #   pkg/a.py (imports pkg.b)
    #   pkg/b.py
    #   pkg/c.py
    root = tmp_path
    write(root / "pkg/__init__.py", "")
    write(root / "pkg/b.py", "def bb():\n    return 1\n")
    write(root / "pkg/a.py", "import pkg.b\n\n def aa():\n    return pkg.b.bb()\n")
    write(root / "pkg/c.py", "# sibling test\n")

    state = root / ".gnosis-flow"
    state.mkdir(exist_ok=True)
    gm = GraphManager(root=root, state_dir=state)

    # ensure import scan and sibling edges
    nbs = gm.neighbors_for_path(str(root / "pkg/a.py"), types=["import_dep", "dir_sibling"], limit=10)
    kinds = {n["type"] for n in nbs}
    assert "import_dep" in kinds
    assert "dir_sibling" in kinds
    # Ensure b.py is present as import neighbor
    dsts = {n["dst"] for n in nbs}
    assert any(d.endswith("pkg/b.py") for d in dsts)

    # co-activity: touch a.py then c.py
    gm.on_file_event(str(root / "pkg/a.py"))
    gm.on_file_event(str(root / "pkg/c.py"))
    nbs2 = gm.neighbors_for_path(str(root / "pkg/c.py"), types=["co_activity"], limit=10)
    dsts2 = {n["dst"] for n in nbs2}
    assert any(d.endswith("pkg/a.py") for d in dsts2)

