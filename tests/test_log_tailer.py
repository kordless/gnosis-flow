import asyncio
from pathlib import Path

from gnosis_flow.runtime import LogTailer


def test_log_tailer_reads_appended_lines(tmp_path: Path):
    async def run_case():
        lines = []

        async def collect(p: Path):
            tail = LogTailer(str(p), poll_interval=0.05)
            async for item in tail.run():
                lines.append(item.get("line"))
                if len(lines) >= 3:
                    tail.stop()
                    break

        f = tmp_path / "app.log"
        f.write_text("", encoding="utf-8")
        task = asyncio.create_task(collect(f))
        await asyncio.sleep(0.1)
        # Append lines
        with f.open("a", encoding="utf-8") as h:
            h.write("first\n")
            h.flush()
        await asyncio.sleep(0.2)
        with f.open("a", encoding="utf-8") as h:
            h.write("second\nthird\n")
            h.flush()
        await asyncio.sleep(0.3)
        try:
            task.cancel()
        except Exception:
            pass
        return lines

    lines = asyncio.run(run_case())
    assert lines[:3] == ["first", "second", "third"]

