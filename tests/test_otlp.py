"""OTLP/HTTP ingest in both wire formats lands as the same internal spans."""

from swarmwatch.ingest import parse_otlp_json, parse_otlp_proto
from swarmwatch.model import SpanKind

JSON_PAYLOAD = {
    "resourceSpans": [
        {
            "resource": {
                "attributes": [{"key": "service.name", "value": {"stringValue": "demo"}}],
            },
            "scopeSpans": [
                {
                    "scope": {"name": "swarmwatch.sdk"},
                    "spans": [
                        {
                            "traceId": "a1b2",
                            "spanId": "s1",
                            "parentSpanId": "",
                            "name": "invoke_agent planner",
                            "startTimeUnixNano": "1716835200000000000",
                            "endTimeUnixNano": "1716835201000000000",
                            "attributes": [
                                {"key": "gen_ai.operation.name", "value": {"stringValue": "invoke_agent"}},
                                {"key": "gen_ai.agent.name", "value": {"stringValue": "planner"}},
                                {"key": "swarmwatch.inputs_from", "value": {"arrayValue": {"values": []}}},
                            ],
                            "status": {"code": 1},
                        },
                        {
                            "traceId": "a1b2",
                            "spanId": "s2",
                            "parentSpanId": "s1",
                            "name": "chat grok",
                            "startTimeUnixNano": "1716835200200000000",
                            "endTimeUnixNano": "1716835200800000000",
                            "attributes": [
                                {"key": "gen_ai.operation.name", "value": {"stringValue": "chat"}},
                                {"key": "gen_ai.request.model", "value": {"stringValue": "grok-4.20"}},
                                {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "123"}},
                                {"key": "gen_ai.usage.output_tokens", "value": {"intValue": "45"}},
                                # SDK serializes messages as JSON strings since OTel attributes
                                # can't hold complex objects directly.
                                {"key": "gen_ai.output.messages",
                                 "value": {"stringValue": '[{"role":"assistant","content":"hi"}]'}},
                            ],
                            "status": {"code": 1},
                        },
                    ],
                }
            ],
        }
    ]
}


def test_parse_otlp_json():
    spans = parse_otlp_json(JSON_PAYLOAD)
    assert len(spans) == 2
    by_id = {s.span_id: s for s in spans}
    assert by_id["s1"].kind is SpanKind.AGENT
    assert by_id["s1"].agent == "planner"
    assert by_id["s1"].inputs_from == []
    assert by_id["s2"].kind is SpanKind.LLM
    assert by_id["s2"].model == "grok-4.20"
    assert by_id["s2"].usage.input_tokens == 123
    assert by_id["s2"].usage.output_tokens == 45
    # JSON-string messages get parsed back into Message objects.
    assert by_id["s2"].output_messages[0].content == "hi"


def test_parse_otlp_proto_roundtrip():
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
        ExportTraceServiceRequest,
    )

    req = ExportTraceServiceRequest()
    rs = req.resource_spans.add()
    ss = rs.scope_spans.add()
    sp = ss.spans.add()
    sp.trace_id = b"\xa1" * 16
    sp.span_id = b"\xb1" * 8
    sp.name = "invoke_agent planner"
    sp.start_time_unix_nano = 1716835200_000_000_000
    sp.end_time_unix_nano = 1716835201_000_000_000

    op = sp.attributes.add()
    op.key = "gen_ai.operation.name"
    op.value.string_value = "invoke_agent"
    ag = sp.attributes.add()
    ag.key = "gen_ai.agent.name"
    ag.value.string_value = "planner"
    sp.status.code = 1

    spans = parse_otlp_proto(req.SerializeToString())
    assert len(spans) == 1
    assert spans[0].kind is SpanKind.AGENT
    assert spans[0].agent == "planner"
    # binary trace/span ids surface as hex strings
    assert spans[0].trace_id == "a1" * 16
    assert spans[0].span_id == "b1" * 8
