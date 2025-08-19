from pathlib import Path

from gnosis_flow.graph.store import GraphManager


def write(p: Path, txt: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")


def test_shared_tokens_and_terms(tmp_path: Path):
    root = tmp_path
    # Two similar files sharing tokens
    write(root / "a.py", "def alpha():\n    foo_var = 1\n    bar_count = 2\n    return foo_var + bar_count\n")
    write(root / "b.py", "def beta():\n    foo_var = 3\n    bar_count = 4\n    return foo_var - bar_count\n")
    # One file referencing a term
    write(root / "c.py", "# payment processing\nclass PaymentGateway:\n    pass\n")
    state = root / ".gnosis-flow"
    state.mkdir(exist_ok=True)

    gm = GraphManager(root=root, state_dir=state, shared_tokens_enabled=True, max_file_kb=64, terms=["payment"])

    # Build token similarities
    nbs_a = gm.neighbors_for_path(str(root / "a.py"), types=["shared_tokens"], limit=10)
    dsts = {n["dst"] for n in nbs_a}
    assert any(d.endswith("b.py") for d in dsts)

    # Build term refs
    nbs_c = gm.neighbors_for_path(str(root / "c.py"), types=["term_ref"], limit=10)
    kinds = {n["type"] for n in nbs_c}
    assert "term_ref" in kinds

