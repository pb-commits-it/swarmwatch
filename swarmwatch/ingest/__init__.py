"""Span ingestion: normalize OTel GenAI / OpenInference into the internal model."""

from swarmwatch.ingest.normalize import normalize_span
from swarmwatch.ingest.otlp import parse_otlp_json, parse_otlp_proto

__all__ = ["normalize_span", "parse_otlp_json", "parse_otlp_proto"]
