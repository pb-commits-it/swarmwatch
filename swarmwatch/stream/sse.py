"""Server-Sent Events helpers.

The live feed is one-way server→client (span events, then a terminal done
event), which is exactly SSE's shape. Bidirectional control — pause/step/scrub —
will arrive over WebSocket in a later release.
"""

from __future__ import annotations

import json


def sse_message(event: str, data: dict) -> dict:
    """Shape a payload for sse-starlette's EventSourceResponse."""
    return {"event": event, "data": json.dumps(data)}
