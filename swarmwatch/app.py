"""The swarmwatch FastAPI app.

Wires ingest → store → stream and serves the web UI. Three ingest paths:
  - bundled sample replay (used by the demo by default)
  - file replay via `--trace path.jsonl`
  - **live**: POST /v1/traces (OTLP/HTTP, protobuf or JSON) from any
    OpenTelemetry-instrumented app — broadcast over SSE to /api/live
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from swarmwatch import __version__
from swarmwatch.ingest import parse_otlp_json, parse_otlp_proto
from swarmwatch.model import Trace
from swarmwatch.replay import load_trace, replay_events
from swarmwatch.store import SpanStore
from swarmwatch.stream import LiveHub, sse_message

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

    hub = LiveHub()
    # Live store is separate so the bundled sample doesn't pollute live topology.
    live_store = SpanStore()

    app = FastAPI(title="swarmwatch", version=__version__)
    app.state.trace = trace
    app.state.store = store
    app.state.live_store = live_store
    app.state.hub = hub
    app.state.trace_path = str(path)

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "trace_id": trace.trace_id,
            "spans": len(trace.spans),
            "live_spans": len(live_store.all_spans()),
            "live_subscribers": hub.subscriber_count(),
        }

    @app.get("/api/trace")
    def get_trace() -> JSONResponse:
        return JSONResponse(app.state.trace.to_dict())

    @app.get("/api/live-trace")
    def get_live_trace() -> JSONResponse:
        """The current accumulated live trace — what /api/live snapshots on connect."""
        spans = live_store.all_spans()
        if not spans:
            return JSONResponse({"trace_id": "live", "workflow": None, "agents": [], "edges": [], "spans": [], "total_spans": 0})
        return JSONResponse(Trace.from_spans(spans).to_dict())

    @app.get("/api/agents")
    def get_agents() -> JSONResponse:
        return JSONResponse(store.agent_stats(trace.trace_id))

    @app.get("/api/stream")
    async def stream(speed: float = Query(default=1.0, gt=0.0)) -> EventSourceResponse:
        async def events():
            yield sse_message("trace", app.state.trace.summary())
            async for event, data in replay_events(app.state.trace, speed=speed):
                yield sse_message(event, data)

        return EventSourceResponse(events())

    @app.get("/api/live")
    async def live() -> EventSourceResponse:
        """Subscribe to spans ingested via POST /v1/traces (or the SDK)."""

        async def events():
            # Send the current accumulated topology so a late subscriber sees
            # what's already arrived.
            spans = live_store.all_spans()
            current = Trace.from_spans(spans).summary() if spans else {
                "trace_id": "live", "workflow": None, "agents": [], "edges": [], "total_spans": 0,
            }
            yield sse_message("trace", current)

            queue = hub.subscribe()
            try:
                while True:
                    event, data = await queue.get()
                    yield sse_message(event, data)
            finally:
                hub.unsubscribe(queue)

        return EventSourceResponse(events())

    @app.post("/v1/traces")
    async def otlp_ingest(request: Request) -> Response:
        """Standard OTLP/HTTP trace ingest. Accepts protobuf or JSON."""
        body = await request.body()
        content_type = request.headers.get("content-type", "").lower()
        if "json" in content_type:
            import json
            new_spans = parse_otlp_json(json.loads(body or b"{}"))
        else:
            new_spans = parse_otlp_proto(body)

        if not new_spans:
            return Response(content=b"{}", media_type="application/json")

        for span in new_spans:
            live_store.add_span(span)

        # Rebuild + broadcast topology so the UI can grow new nodes/edges in,
        # then push each new span for the live animation.
        topology = Trace.from_spans(live_store.all_spans()).summary()
        await hub.publish("trace", topology)
        for span in new_spans:
            await hub.publish("span", span.model_dump(mode="json"))

        return Response(content=b"{}", media_type="application/json")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    assets_dir = WEB_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    return app


app = create_app()
