"""The DuckDB store round-trips spans, and replay drives the bundled sample."""

import asyncio

from swarmwatch.app import bundled_trace_path
from swarmwatch.replay import load_trace, replay_events
from swarmwatch.store import SpanStore


def test_bundled_sample_loads():
    trace = load_trace(bundled_trace_path())
    assert trace.workflow == "research-swarm"
    assert len(trace.spans) == 12
    assert [a.name for a in trace.agents()] == ["planner", "worker-1", "worker-2", "judge"]
    assert {(e.src, e.dst) for e in trace.edges()} == {
        ("planner", "worker-1"),
        ("planner", "worker-2"),
        ("worker-1", "judge"),
        ("worker-2", "judge"),
    }


def test_store_roundtrip_and_stats():
    trace = load_trace(bundled_trace_path())
    store = SpanStore()
    for span in trace.spans:
        store.add_span(span)

    assert len(store.get_spans(trace.trace_id)) == 12
    # adding the same spans again must not duplicate (span_id is the primary key)
    for span in trace.spans:
        store.add_span(span)
    assert len(store.get_spans(trace.trace_id)) == 12

    stats = {row["agent"]: row for row in store.agent_stats(trace.trace_id)}
    assert stats["worker-1"]["tool_calls"] == 2
    assert stats["judge"]["input_tokens"] == 1900


def test_replay_emits_every_span_then_done():
    trace = load_trace(bundled_trace_path())

    async def collect():
        events = []
        async for event, data in replay_events(trace, speed=100):
            events.append((event, data))
        return events

    events = asyncio.run(collect())
    spans = [d for kind, d in events if kind == "span"]
    assert len(spans) == 12
    assert events[-1][0] == "done"
    assert events[-1][1]["total_spans"] == 12
