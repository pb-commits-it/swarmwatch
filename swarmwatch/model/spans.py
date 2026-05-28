"""The internal span model.

swarmwatch normalizes OpenTelemetry GenAI and OpenInference spans into these
types on ingest, so the rest of the system speaks one vocabulary regardless of
which framework produced the trace.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SpanKind(str, Enum):
    """What a span represents in an agent run."""

    AGENT = "agent"
    LLM = "llm"
    TOOL = "tool"
    WORKFLOW = "workflow"
    OTHER = "other"


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


class Message(BaseModel):
    role: str
    content: str


class Span(BaseModel):
    """One node in an agent run — an agent turn, an LLM call, or a tool call."""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str
    kind: SpanKind
    start_time: datetime
    end_time: datetime

    # Who owns this span. For LLM/tool spans this is resolved to the enclosing
    # agent (see Trace.from_spans).
    agent: str | None = None

    model: str | None = None
    provider: str | None = None
    tool: str | None = None
    usage: Usage = Field(default_factory=Usage)
    conversation_id: str | None = None
    status: str = "ok"

    # Agents whose output fed this agent. The source of handoff edges in the
    # causal DAG. Only meaningful on agent spans.
    inputs_from: list[str] = Field(default_factory=list)

    # The context that crossed into and out of this span. Used by the Handoff
    # Inspector to diff what one agent sent vs. what the next received.
    input_messages: list[Message] = Field(default_factory=list)
    output_messages: list[Message] = Field(default_factory=list)

    # Anything not promoted to a typed field, kept for the detail panel.
    attributes: dict = Field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time).total_seconds() * 1000.0
