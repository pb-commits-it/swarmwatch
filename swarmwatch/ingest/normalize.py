"""Normalize incoming spans into the internal model.

swarmwatch ingests two schemas and maps both onto one model, so a trace from
LangGraph (OpenInference auto-instrumentation) and a trace from a hand-rolled
loop (raw OTel GenAI) render identically. The two schemas are never mixed on a
single span — we read whichever one is present.
"""

from __future__ import annotations

import json
from typing import Any

from swarmwatch.model.spans import Message, Span, SpanKind, Usage

# OpenTelemetry GenAI: gen_ai.operation.name → kind
_OTEL_OP_TO_KIND = {
    "invoke_agent": SpanKind.AGENT,
    "create_agent": SpanKind.AGENT,
    "chat": SpanKind.LLM,
    "text_completion": SpanKind.LLM,
    "generate_content": SpanKind.LLM,
    "execute_tool": SpanKind.TOOL,
    "invoke_workflow": SpanKind.WORKFLOW,
}

# OpenInference: openinference.span.kind → kind
_OI_KIND_TO_KIND = {
    "AGENT": SpanKind.AGENT,
    "LLM": SpanKind.LLM,
    "TOOL": SpanKind.TOOL,
    "CHAIN": SpanKind.WORKFLOW,
    "RETRIEVER": SpanKind.TOOL,
    "RERANKER": SpanKind.TOOL,
    "EMBEDDING": SpanKind.LLM,
}

# Attribute keys we promote to typed fields, so `attributes` keeps only extras.
_KNOWN_KEYS = {
    "gen_ai.operation.name", "gen_ai.agent.name", "gen_ai.request.model",
    "gen_ai.response.model", "gen_ai.provider.name", "gen_ai.tool.name",
    "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
    "gen_ai.conversation.id", "gen_ai.input.messages", "gen_ai.output.messages",
    "swarmwatch.inputs_from", "openinference.span.kind", "agent.name",
    "llm.model_name", "llm.provider", "tool.name", "llm.token_count.prompt",
    "llm.token_count.completion", "input.value", "output.value",
}


def _first(attrs: dict, *keys: str) -> Any:
    for key in keys:
        if key in attrs and attrs[key] not in (None, ""):
            return attrs[key]
    return None


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _messages(value: Any) -> list[Message]:
    if value is None:
        return []
    if isinstance(value, str):
        # OTel attributes can't hold complex objects directly, so messages often
        # arrive JSON-encoded; try to parse, fall back to plain text.
        stripped = value.strip()
        if stripped.startswith(("[", "{")):
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError:
                return [Message(role="text", content=value)]
        else:
            return [Message(role="text", content=value)]
    if isinstance(value, dict):
        value = [value]
    messages: list[Message] = []
    for item in value:
        if isinstance(item, str):
            messages.append(Message(role="text", content=item))
            continue
        role = item.get("role", "text")
        content = item.get("content", item.get("text", ""))
        if isinstance(content, list):
            # OTel allows content parts; flatten the text of each.
            parts = [p.get("text", "") if isinstance(p, dict) else str(p) for p in content]
            content = "".join(parts)
        messages.append(Message(role=str(role), content=str(content)))
    return messages


def normalize_span(raw: dict) -> Span:
    """Turn a raw span dict (OTel GenAI or OpenInference flavored) into a Span."""
    attrs: dict = raw.get("attributes", {}) or {}

    op = attrs.get("gen_ai.operation.name")
    oi_kind = attrs.get("openinference.span.kind")
    if op:
        kind = _OTEL_OP_TO_KIND.get(op, SpanKind.OTHER)
    elif oi_kind:
        kind = _OI_KIND_TO_KIND.get(str(oi_kind).upper(), SpanKind.OTHER)
    else:
        kind = SpanKind.OTHER

    agent = _first(attrs, "gen_ai.agent.name", "agent.name")
    model = _first(attrs, "gen_ai.request.model", "gen_ai.response.model", "llm.model_name")
    provider = _first(attrs, "gen_ai.provider.name", "llm.provider")
    tool = _first(attrs, "gen_ai.tool.name", "tool.name")
    usage = Usage(
        input_tokens=_int(_first(attrs, "gen_ai.usage.input_tokens", "llm.token_count.prompt")),
        output_tokens=_int(_first(attrs, "gen_ai.usage.output_tokens", "llm.token_count.completion")),
    )
    inputs_from = attrs.get("swarmwatch.inputs_from") or []
    in_msgs = _messages(_first(attrs, "gen_ai.input.messages", "input.value"))
    out_msgs = _messages(_first(attrs, "gen_ai.output.messages", "output.value"))

    name = raw.get("name") or " ".join(
        part for part in [op or (str(oi_kind).lower() if oi_kind else None), agent or tool] if part
    ) or "span"

    extras = {k: v for k, v in attrs.items() if k not in _KNOWN_KEYS}

    return Span(
        trace_id=raw["trace_id"],
        span_id=raw["span_id"],
        parent_span_id=raw.get("parent_span_id"),
        name=name,
        kind=kind,
        start_time=raw["start_time"],
        end_time=raw["end_time"],
        agent=agent,
        model=model,
        provider=provider,
        tool=tool,
        usage=usage,
        conversation_id=attrs.get("gen_ai.conversation.id"),
        status=raw.get("status", "ok"),
        inputs_from=list(inputs_from),
        input_messages=in_msgs,
        output_messages=out_msgs,
        attributes=extras,
    )
