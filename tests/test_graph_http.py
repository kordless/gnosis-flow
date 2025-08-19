import asyncio
from pathlib import Path

from gnosis_flow.graph.store import GraphManager
from gnosis_flow.runtime import HttpStatusServer, MonitorState


def write(p: Path, txt: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(txt, encoding="utf-8")


def _http_get(host: str, port: int, path: str) -> bytes:
    async def _run():
        reader, writer = await asyncio.open_connection(host, port)
        req = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode()
        writer.write(req)
        await writer.drain()
        data = await reader.read(-1)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return data

    return asyncio.run(_run())


def test_http_graph_endpoints(tmp_path: Path):
    root = tmp_path
    write(root / "pkg/__init__.py", "")
    write(root / "pkg/b.py", "def bb():\n    return 1\n")
    write(root / "pkg/a.py", "import pkg.b\n\n def aa():\n    return pkg.b.bb()\n")

    state_dir = root / ".gnosis-flow"
    state_dir.mkdir(exist_ok=True)

    state = MonitorState(poll_interval=1.0, state_dir=str(state_dir))
    # Initialize graph manually
    state.graph = GraphManager(root=root, state_dir=state_dir)

    srv = HttpStatusServer("127.0.0.1", 0, state)

    async def _start_server():
        await srv.start()
        # small sleep to ensure bind completes
        await asyncio.sleep(0.05)

    asyncio.run(_start_server())
    try:
        port = srv.server.sockets[0].getsockname()[1]
        # edge-types
        res = _http_get("127.0.0.1", port, "/graph/edge-types")
        assert b"200 OK" in res and b"dir_sibling" in res
        # neighbors for a.py (import dep)
        res2 = _http_get("127.0.0.1", port, f"/graph/neighbors?path={str(root / 'pkg/a.py')}\x26types=import_dep")
        assert b"200 OK" in res2 and b"pkg/b.py" in res2
        # why
        res3 = _http_get("127.0.0.1", port, f"/graph/why?src={str(root / 'pkg/a.py')}\x26dst={str(root / 'pkg/b.py')}")
        assert b"200 OK" in res3 and b"import_dep" in res3
    finally:
        # no explicit shutdown API; rely on garbage collection
        pass

