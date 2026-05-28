"""A trace: the spans of one agent run, plus the derived causal structure.

The interesting product here is the *causal DAG* — agents as nodes and handoffs
as edges — because that, not a flat span list, is what the bugs in multi-agent
systems live in.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from swarmwatch.model.spans import Span, SpanKind


class AgentNode(BaseModel):
    """One agent in the run, aggregated from its spans."""

    name: str
    llm_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    first_seen: datetime
    last_seen: datetime
    status: str = "ok"
    inputs_from: list[str] = Field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class HandoffEdge(BaseModel):
    """A directed handoff: src's output fed dst. Where context gets lost."""

    src: str
    dst: str


class Trace(BaseModel):
    trace_id: str
    workflow: str | None = None
    spans: list[Span] = Field(default_factory=list)

    @classmethod
    def from_spans(cls, spans: list[Span]) -> "Trace":
        spans = sorted(spans, key=lambda s: s.start_time)
        by_id = {s.span_id: s for s in spans}

        # Resolve the owning agent for non-agent spans by walking up to the
        # nearest enclosing agent span. Real OTel traces don't tag every LLM
        # call with its agent; the parent chain does.
        for span in spans:
            if span.agent:
                continue
            cursor = span.parent_span_id
            seen: set[str] = set()
            while cursor and cursor in by_id and cursor not in seen:
                seen.add(cursor)
                parent = by_id[cursor]
                if parent.agent:
                    span.agent = parent.agent
                    break
                cursor = parent.parent_span_id

        workflow = next(
            (s.name.replace("invoke_workflow", "").strip() or s.name
             for s in spans if s.kind is SpanKind.WORKFLOW),
            None,
        )
        trace_id = spans[0].trace_id if spans else ""
        return cls(trace_id=trace_id, workflow=workflow, spans=spans)

    def agents(self) -> list[AgentNode]:
        nodes: dict[str, AgentNode] = {}
        for span in self.spans:
            if not span.agent:
                continue
            node = nodes.get(span.agent)
            if node is None:
                node = AgentNode(
                    name=span.agent,
                    first_seen=span.start_time,
                    last_seen=span.end_time,
                )
                nodes[span.agent] = node
            node.first_seen = min(node.first_seen, span.start_time)
            node.last_seen = max(node.last_seen, span.end_time)
            node.input_tokens += span.usage.input_tokens
            node.output_tokens += span.usage.output_tokens
            if span.kind is SpanKind.LLM:
                node.llm_calls += 1
            elif span.kind is SpanKind.TOOL:
                node.tool_calls += 1
            if span.kind is SpanKind.AGENT and span.inputs_from:
                node.inputs_from = list(dict.fromkeys([*node.inputs_from, *span.inputs_from]))
            if span.status != "ok":
                node.status = span.status
        return sorted(nodes.values(), key=lambda n: n.first_seen)

    def edges(self) -> list[HandoffEdge]:
        seen: set[tuple[str, str]] = set()
        edges: list[HandoffEdge] = []
        for span in self.spans:
            if span.kind is not SpanKind.AGENT or not span.agent:
                continue
            for src in span.inputs_from:
                key = (src, span.agent)
                if key not in seen:
                    seen.add(key)
                    edges.append(HandoffEdge(src=src, dst=span.agent))
        return edges

    def summary(self) -> dict:
        """Metadata + topology, without the full span payloads. Sent first over
        the live stream so the UI can pre-draw the agent lanes."""
        agents = self.agents()
        return {
            "trace_id": self.trace_id,
            "workflow": self.workflow,
            "agents": [a.model_dump(mode="json") for a in agents],
            "edges": [e.model_dump(mode="json") for e in self.edges()],
            "total_spans": len(self.spans),
        }

    def to_dict(self) -> dict:
        data = self.summary()
        data["spans"] = [s.model_dump(mode="json") for s in self.spans]
        return data
