import asyncio
import os
import time
from pathlib import Path

from gnosis_flow.runtime import DirWatcher


def test_dir_watcher_create_modify_delete(tmp_path: Path):
    async def run_case():
        events = []
        got = {"created": False, "modified": False, "deleted": False, "dir_created": False}

        async def collect():
            watcher = DirWatcher(str(tmp_path), poll_interval=0.05)
            async for ev in watcher.run():
                events.append((ev.kind, ev.path))
                if ev.kind in got:
                    got[ev.kind] = True
                if all(got.values()):
                    watcher.stop()
                    break

        task = asyncio.create_task(collect())
        await asyncio.sleep(0.1)

        # Create file
        f = tmp_path / "a.txt"
        f.write_text("hello\n", encoding="utf-8")
        await asyncio.sleep(0.15)

        # Modify file
        f.write_text("hello\nworld\n", encoding="utf-8")
        await asyncio.sleep(0.15)

        # Create directory (not excluded name)
        d = tmp_path / "testdir"
        d.mkdir()
        await asyncio.sleep(0.15)

        # Delete file
        f.unlink()
        await asyncio.sleep(0.15)

        # Give time to collect then stop if still running
        await asyncio.sleep(0.1)
        if not all(got.values()):
            try:
                task.cancel()
            except Exception:
                pass
        return events, got

    events, got = asyncio.run(run_case())
    assert all(got.values()), f"Missing events, got flags: {got}, events: {events}"
