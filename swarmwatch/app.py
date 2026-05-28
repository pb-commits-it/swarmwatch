"""The swarmwatch FastAPI app.

Wires ingest → store → stream and serves the web UI. On startup it loads a
trace (the bundled sample by default) into the store; the UI replays it over
SSE so you can watch the run unfold.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from swarmwatch import __version__
from swarmwatch.replay import load_trace, replay_events
from swarmwatch.store import SpanStore
from swarmwatch.stream import sse_message

_PKG = Path(__file__).parent
WEB_DIR = _PKG / "web"


def bundled_trace_path() -> Path:
    return _PKG / "samples" / "planner_worker_judge.jsonl"


def create_app(trace_path: str | Path | None = None) -> FastAPI:
    path = Path(trace_path) if trace_path else bundled_trace_path()
    trace = load_trace(path)

    store = SpanStore()
    for span in trace.spans:
        store.add_span(span)

    app = FastAPI(title="swarmwatch", version=__version__)
    app.state.trace = trace
    app.state.store = store
    app.state.trace_path = str(path)

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "trace_id": trace.trace_id,
            "spans": len(trace.spans),
        }

    @app.get("/api/trace")
    def get_trace() -> JSONResponse:
        return JSONResponse(app.state.trace.to_dict())

    @app.get("/api/agents")
    def get_agents() -> JSONResponse:
        """Per-agent rollup, computed in DuckDB."""
        return JSONResponse(store.agent_stats(trace.trace_id))

    @app.get("/api/stream")
    async def stream(speed: float = Query(default=1.0, gt=0.0)) -> EventSourceResponse:
        async def events():
            # Topology first, so the UI can pre-draw the agent lanes...
            yield sse_message("trace", app.state.trace.summary())
            # ...then the spans land one by one.
            async for event, data in replay_events(app.state.trace, speed=speed):
                yield sse_message(event, data)

        return EventSourceResponse(events())

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    # The built frontend (Vite output) ships inside the package.
    assets_dir = WEB_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    return app


app = create_app()
