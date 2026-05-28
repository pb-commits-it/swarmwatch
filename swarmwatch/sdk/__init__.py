"""swarmwatch SDK — emit traces to a running swarmwatch server with no ceremony.

Built on OpenTelemetry, so anything you instrument with this SDK is also
instrumented with OTel — point a different exporter at it and it works there
too. swarmwatch's edge is what you see on the other end of the wire.

Quickstart::

    pip install 'swarmwatch[sdk]'
    swarmwatch up &

    from swarmwatch.sdk import SwarmWatch

    sw = SwarmWatch()  # POSTs to http://127.0.0.1:8000/v1/traces

    with sw.workflow("research-swarm", input="recommend a database..."):
        with sw.agent("planner", inputs_from=[], input="..."):
            with sw.chat("grok-4.20", input="...", output="...",
                          input_tokens=850, output_tokens=280):
                ...
        with sw.agent("worker-1", inputs_from=["planner"], input="..."):
            with sw.tool("web_search", output="results"):
                ...

    sw.shutdown()

Open http://127.0.0.1:8000/?mode=live to watch it land.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from typing import Iterator, Optional


class SpanHandle:
    """Returned by `chat()` / `tool()` so you can attach results computed inside the span."""

    def __init__(self, span) -> None:
        self._span = span

    def set_input(self, text: str, role: str = "user") -> None:
        self._span.set_attribute(
            "gen_ai.input.messages", json.dumps([{"role": role, "content": text}])
        )

    def set_output(self, text: str, role: str = "assistant") -> None:
        self._span.set_attribute(
            "gen_ai.output.messages", json.dumps([{"role": role, "content": text}])
        )

    def set_tokens(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        if input_tokens:
            self._span.set_attribute("gen_ai.usage.input_tokens", int(input_tokens))
        if output_tokens:
            self._span.set_attribute("gen_ai.usage.output_tokens", int(output_tokens))


class SwarmWatch:
    """Send OTel-GenAI traces to a swarmwatch server.

    Args:
        endpoint: base URL of the swarmwatch server. `/v1/traces` is appended
            if not already present. Defaults to ``$SWARMWATCH_ENDPOINT`` or
            ``http://127.0.0.1:8000``.
        service: ``service.name`` resource attribute for the exporter.
        batch: if True use BatchSpanProcessor (lower overhead, slight delay);
            default False uses SimpleSpanProcessor so the live UI sees spans
            arrive immediately.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        service: str = "swarmwatch-app",
        batch: bool = False,
    ) -> None:
        endpoint = endpoint or os.environ.get("SWARMWATCH_ENDPOINT", "http://127.0.0.1:8000")
        if not endpoint.endswith("/v1/traces"):
            endpoint = endpoint.rstrip("/") + "/v1/traces"

        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import (
                BatchSpanProcessor,
                SimpleSpanProcessor,
            )
        except ImportError as exc:  # pragma: no cover - install-time hint
            raise ImportError(
                "swarmwatch SDK requires opentelemetry; install with: "
                "pip install 'swarmwatch[sdk]'"
            ) from exc

        provider = TracerProvider(resource=Resource.create({"service.name": service}))
        exporter = OTLPSpanExporter(endpoint=endpoint)
        processor = BatchSpanProcessor(exporter) if batch else SimpleSpanProcessor(exporter)
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

        self._provider = provider
        self._tracer = trace.get_tracer("swarmwatch.sdk")
        self.endpoint = endpoint

    @contextmanager
    def workflow(
        self,
        name: str,
        *,
        input: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Iterator[SpanHandle]:
        attrs: dict = {"gen_ai.operation.name": "invoke_workflow"}
        if conversation_id:
            attrs["gen_ai.conversation.id"] = conversation_id
        if input is not None:
            attrs["gen_ai.input.messages"] = json.dumps([{"role": "user", "content": input}])
        with self._tracer.start_as_current_span(
            f"invoke_workflow {name}", attributes=attrs
        ) as span:
            yield SpanHandle(span)

    @contextmanager
    def agent(
        self,
        name: str,
        *,
        inputs_from: Optional[list[str]] = None,
        input: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Iterator[SpanHandle]:
        attrs: dict = {
            "gen_ai.operation.name": "invoke_agent",
            "gen_ai.agent.name": name,
        }
        if inputs_from is not None:
            attrs["swarmwatch.inputs_from"] = list(inputs_from)
        if input is not None:
            attrs["gen_ai.input.messages"] = json.dumps([{"role": "user", "content": input}])
        if conversation_id:
            attrs["gen_ai.conversation.id"] = conversation_id
        with self._tracer.start_as_current_span(
            f"invoke_agent {name}", attributes=attrs
        ) as span:
            yield SpanHandle(span)

    @contextmanager
    def chat(
        self,
        model: str,
        *,
        provider: Optional[str] = None,
        input: Optional[str] = None,
        output: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> Iterator[SpanHandle]:
        attrs: dict = {
            "gen_ai.operation.name": "chat",
            "gen_ai.request.model": model,
        }
        if provider:
            attrs["gen_ai.provider.name"] = provider
        if input_tokens:
            attrs["gen_ai.usage.input_tokens"] = int(input_tokens)
        if output_tokens:
            attrs["gen_ai.usage.output_tokens"] = int(output_tokens)
        if input is not None:
            attrs["gen_ai.input.messages"] = json.dumps([{"role": "user", "content": input}])
        if output is not None:
            attrs["gen_ai.output.messages"] = json.dumps(
                [{"role": "assistant", "content": output}]
            )
        with self._tracer.start_as_current_span(f"chat {model}", attributes=attrs) as span:
            yield SpanHandle(span)

    @contextmanager
    def tool(
        self,
        name: str,
        *,
        output: Optional[str] = None,
    ) -> Iterator[SpanHandle]:
        attrs: dict = {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": name,
        }
        if output is not None:
            attrs["gen_ai.output.messages"] = json.dumps([{"role": "tool", "content": output}])
        with self._tracer.start_as_current_span(
            f"execute_tool {name}", attributes=attrs
        ) as span:
            yield SpanHandle(span)

    def shutdown(self) -> None:
        """Flush and close the exporter. Call before the process exits."""
        self._provider.shutdown()


__all__ = ["SpanHandle", "SwarmWatch"]
