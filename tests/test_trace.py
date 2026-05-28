"""The causal DAG: agent aggregation, owning-agent resolution, handoff edges."""

from datetime import datetime, timedelta

from swarmwatch.model import Span, SpanKind, Trace

T0 = datetime(2026, 5, 27, 17, 0, 0)


def _span(span_id, kind, parent=None, agent=None, offset=0, **kw):
    return Span(
        trace_id="t",
        span_id=span_id,
        parent_span_id=parent,
        name=span_id,
        kind=kind,
        start_time=T0 + timedelta(seconds=offset),
        end_time=T0 + timedelta(seconds=offset + 1),
        agent=agent,
        **kw,
    )


def _sample_trace():
    return Trace.from_spans([
        _span("w", SpanKind.WORKFLOW, offset=0),
        _span("a", SpanKind.AGENT, parent="w", agent="A", offset=1, inputs_from=[]),
        _span("a-llm", SpanKind.LLM, parent="a", offset=2),  # no agent set → inherit A
        _span("b", SpanKind.AGENT, parent="w", agent="B", offset=3, inputs_from=["A"]),
        _span("b-tool", SpanKind.TOOL, parent="b", offset=4),  # inherit B
    ])


def test_owning_agent_resolution():
    trace = _sample_trace()
    by_id = {s.span_id: s for s in trace.spans}
    assert by_id["a-llm"].agent == "A"   # resolved by walking up the parent chain
    assert by_id["b-tool"].agent == "B"


def test_agent_aggregation():
    agents = {a.name: a for a in _sample_trace().agents()}
    assert set(agents) == {"A", "B"}
    assert agents["A"].llm_calls == 1
    assert agents["B"].tool_calls == 1


def test_handoff_edges():
    edges = {(e.src, e.dst) for e in _sample_trace().edges()}
    assert edges == {("A", "B")}


def test_workflow_name_stripped():
    trace = Trace.from_spans([
        _span("w", SpanKind.WORKFLOW, offset=0),
    ])
    # span name "w" has no "invoke_workflow" prefix, so it is used as-is.
    assert trace.workflow == "w"
