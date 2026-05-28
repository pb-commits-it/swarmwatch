"""Both supported wire schemas normalize onto the same internal model."""

from swarmwatch.ingest import normalize_span
from swarmwatch.model import SpanKind

BASE = {
    "trace_id": "t",
    "span_id": "s1",
    "parent_span_id": None,
    "start_time": "2026-05-27T17:00:00Z",
    "end_time": "2026-05-27T17:00:01Z",
}


def test_otel_genai_llm_span():
    span = normalize_span({
        **BASE,
        "attributes": {
            "gen_ai.operation.name": "chat",
            "gen_ai.agent.name": "planner",
            "gen_ai.request.model": "grok-4.20",
            "gen_ai.provider.name": "xai",
            "gen_ai.usage.input_tokens": 10,
            "gen_ai.usage.output_tokens": 5,
            "gen_ai.output.messages": [{"role": "assistant", "content": "hi"}],
        },
    })
    assert span.kind is SpanKind.LLM
    assert span.agent == "planner"
    assert span.model == "grok-4.20"
    assert span.usage.input_tokens == 10
    assert span.usage.total == 15
    assert span.output_messages[0].content == "hi"


def test_openinference_llm_span():
    span = normalize_span({
        **BASE,
        "attributes": {
            "openinference.span.kind": "LLM",
            "llm.model_name": "gpt-x",
            "llm.token_count.prompt": 7,
            "llm.token_count.completion": 3,
            "output.value": "hello",
        },
    })
    assert span.kind is SpanKind.LLM
    assert span.model == "gpt-x"
    assert span.usage.input_tokens == 7
    assert span.usage.output_tokens == 3
    assert span.output_messages[0].content == "hello"


def test_tool_and_handoff_attributes():
    span = normalize_span({
        **BASE,
        "attributes": {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "web_search",
        },
    })
    assert span.kind is SpanKind.TOOL
    assert span.tool == "web_search"

    agent = normalize_span({
        **BASE,
        "attributes": {
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.agent.name": "judge",
            "swarmwatch.inputs_from": ["worker-1", "worker-2"],
        },
    })
    assert agent.kind is SpanKind.AGENT
    assert agent.inputs_from == ["worker-1", "worker-2"]


def test_unknown_attributes_kept_as_extras():
    span = normalize_span({
        **BASE,
        "attributes": {"gen_ai.operation.name": "chat", "custom.tag": "x"},
    })
    assert span.attributes == {"custom.tag": "x"}
