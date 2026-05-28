"""Load and replay recorded traces.

Replay drives the same pipeline as live ingest, so the demo runs offline and
deterministically — and so the live renderer and the replay renderer are the
same code fed from different sources.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

from swarmwatch.ingest import normalize_span
from swarmwatch.model import Trace


def load_trace(path: str | Path) -> Trace:
    """Read a `.jsonl` trace (one raw span per line) into a Trace."""
    spans = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        spans.append(normalize_span(json.loads(line)))
    if not spans:
        raise ValueError(f"no spans found in {path}")
    return Trace.from_spans(spans)


async def replay_events(
    trace: Trace,
    speed: float = 1.0,
    min_delay: float = 0.18,
    max_delay: float = 1.4,
) -> AsyncIterator[tuple[str, dict]]:
    """Yield spans in start-time order, paced to mimic the original run.

    Inter-span gaps are scaled by `speed` and clamped so a 30s run replays in
    a watchable window without collapsing into an instant dump.
    """
    spans = sorted(trace.spans, key=lambda s: s.start_time)
    previous = None
    for span in spans:
        if previous is None:
            await asyncio.sleep(min_delay)
        else:
            gap = (span.start_time - previous).total_seconds() / max(speed, 0.01)
            await asyncio.sleep(min(max(gap, min_delay), max_delay))
        previous = span.start_time
        yield "span", span.model_dump(mode="json")
    yield "done", {"total_spans": len(spans)}
