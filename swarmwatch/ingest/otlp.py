"""Parse incoming OTLP/HTTP payloads into the internal span model.

Supports both wire formats:
- application/x-protobuf — the OTel SDK default, decoded via opentelemetry-proto
- application/json       — the OTLP/JSON variant (use with `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`)

Either way, the output is a list of `Span` ready to land in the store.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from swarmwatch.ingest.normalize import normalize_span
from swarmwatch.model import Span


def _nanos_to_iso(nanos: int | str) -> str:
    n = int(nanos)
    return datetime.fromtimestamp(n / 1_000_000_000, tz=timezone.utc).isoformat()


def _status_str(code: int) -> str:
    # OTel Status: 0 UNSET, 1 OK, 2 ERROR
    return "error" if code == 2 else "ok"


# ──────────────── OTLP/HTTP JSON ──────────────────────────────────────────────


def _json_value(v: dict) -> Any:
    if v is None:
        return None
    if "stringValue" in v:
        return v["stringValue"]
    if "intValue" in v:
        # JSON ints over 2^53 are emitted as strings, mirroring proto int64.
        return int(v["intValue"])
    if "doubleValue" in v:
        return v["doubleValue"]
    if "boolValue" in v:
        return v["boolValue"]
    if "arrayValue" in v:
        return [_json_value(x) for x in v["arrayValue"].get("values", [])]
    if "kvlistValue" in v:
        return {kv["key"]: _json_value(kv["value"]) for kv in v["kvlistValue"].get("values", [])}
    return None


def _json_attrs(attrs: list[dict]) -> dict:
    return {a["key"]: _json_value(a.get("value", {})) for a in attrs or []}


def parse_otlp_json(payload: dict) -> list[Span]:
    spans: list[Span] = []
    for rs in payload.get("resourceSpans", []) or []:
        resource_attrs = _json_attrs(rs.get("resource", {}).get("attributes", []))
        for ss in rs.get("scopeSpans", []) or []:
            for s in ss.get("spans", []) or []:
                raw = {
                    "trace_id": s.get("traceId", ""),
                    "span_id": s.get("spanId", ""),
                    "parent_span_id": s.get("parentSpanId") or None,
                    "name": s.get("name", ""),
                    "start_time": _nanos_to_iso(s.get("startTimeUnixNano", 0)),
                    "end_time": _nanos_to_iso(s.get("endTimeUnixNano", 0)),
                    "attributes": {**resource_attrs, **_json_attrs(s.get("attributes", []))},
                    "status": _status_str(int(s.get("status", {}).get("code", 0))),
                }
                spans.append(normalize_span(raw))
    return spans


# ──────────────── OTLP/HTTP protobuf ──────────────────────────────────────────


def _proto_value(v: Any) -> Any:
    if v.HasField("string_value"):
        return v.string_value
    if v.HasField("int_value"):
        return v.int_value
    if v.HasField("double_value"):
        return v.double_value
    if v.HasField("bool_value"):
        return v.bool_value
    if v.HasField("array_value"):
        return [_proto_value(x) for x in v.array_value.values]
    if v.HasField("kvlist_value"):
        return {kv.key: _proto_value(kv.value) for kv in v.kvlist_value.values}
    if v.HasField("bytes_value"):
        return v.bytes_value
    return None


def _proto_attrs(attrs: Any) -> dict:
    return {a.key: _proto_value(a.value) for a in attrs}


def parse_otlp_proto(body: bytes) -> list[Span]:
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
        ExportTraceServiceRequest,
    )

    req = ExportTraceServiceRequest()
    req.ParseFromString(body)
    spans: list[Span] = []
    for rs in req.resource_spans:
        resource_attrs = _proto_attrs(rs.resource.attributes)
        for ss in rs.scope_spans:
            for s in ss.spans:
                raw = {
                    "trace_id": s.trace_id.hex(),
                    "span_id": s.span_id.hex(),
                    "parent_span_id": s.parent_span_id.hex() if s.parent_span_id else None,
                    "name": s.name,
                    "start_time": _nanos_to_iso(s.start_time_unix_nano),
                    "end_time": _nanos_to_iso(s.end_time_unix_nano),
                    "attributes": {**resource_attrs, **_proto_attrs(s.attributes)},
                    "status": _status_str(int(s.status.code)),
                }
                spans.append(normalize_span(raw))
    return spans
