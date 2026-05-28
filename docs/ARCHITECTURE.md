# Architecture & design rationale

This document explains *why* swarmwatch is built the way it is. The short version: adopt the emerging standard for the boring part (trace capture) so all the effort goes into the part nobody else does well (a live, legible view of a swarm).

## Design principles

1. **Don't invent a trace schema.** swarmwatch ingests the **OpenTelemetry GenAI semantic conventions** as its primary wire format, and also normalizes **OpenInference** spans. Consuming a standard means it works with any instrumented framework instead of becoming yet another silo — and it means the hardest, most thankless part of agent observability (instrumenting N frameworks) is already solved upstream.
2. **Causality is not timestamps.** In a parallel swarm, wall-clock order misleads. swarmwatch builds an explicit causal DAG from span parentage plus `gen_ai.conversation.id` and workflow spans, so "what caused what" is a first-class structure rather than a sort order.
3. **Edges are first-class.** The bugs in multi-agent systems live in the handoffs. The data model treats agent-to-agent context transfer as an inspectable, diffable object — not an implicit gap between two spans.
4. **Local-first.** `pip install`, run, open a browser. No account, no hosted dependency. This is the deliberate difference from the SaaS incumbents.

## Span model

The OpenTelemetry GenAI conventions map cleanly onto a swarm topology:

| Span | Role in swarmwatch |
|------|--------------------|
| `invoke_agent {name}` | an agent node / turn |
| `chat {model}` | an LLM call (child of an agent) |
| `execute_tool {name}` | a tool invocation (child of an agent) |
| `invoke_workflow {name}` | an orchestrator — source of agent-to-agent edges |
| `gen_ai.conversation.id` | ties spans into a single collaboration |

Key attributes captured for node/edge metadata and the token panel: `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens` / `output_tokens`, `gen_ai.response.finish_reasons`, `gen_ai.input.messages` / `output.messages`, `gen_ai.tool.definitions`, `gen_ai.agent.id` / `name`.

OTel-GenAI and OpenInference are normalized into one internal model **on ingest** (the translate-on-ingest pattern Phoenix and Langfuse use). The two schemas are never mixed on a single span — that would duplicate attributes and bloat span size.

## Components

```
ingest/   OTLP/HTTP receiver + normalizers (genai, openinference) → internal spans
model/    span + trace + causal-DAG types
store/    DuckDB: persistence + aggregation queries (per-agent tokens/cost/latency)
stream/   SSE feed (span events · token deltas · layout deltas)  +  WS control
replay/   load a recorded trace file → the same pipeline as live ingest
sdk/      thin decorator wrapper over OTel for a zero-config quickstart
app.py    FastAPI wiring
```

### Transport

- **SSE** is the default for the live feed: three logical channels — span events (build the graph + flamegraph incrementally), token deltas (the typing effect in the detail pane), and layout deltas. SSE is proxy-friendly, trivial on FastAPI, and one-way server→client is exactly the shape of this data.
- **WebSocket** is used *only* where bidirectional control is needed: pause / step / scrub of a running agent, and (later) interrupts.

### Storage

**DuckDB** — file-based, zero-ops, fast analytical queries over span trees, and it keeps the project solo-maintainable. SQLite is acceptable for the earliest cut.

## Frontend

Three view modes over one shared trace model and one shared timeline scrubber:

- **Living Graph (2D)** — `cosmos.gl` / `react-force-graph-2d`. GPU force-directed; directional particle flow on edges when a handoff/tool-call is in flight; nodes pulse on tool calls. The highest-ROI "this is alive" effect.
- **Constellation (3D)** — `react-three-fiber` + `3d-force-graph` with an `UnrealBloomPass`. Emissive nodes on black.
- **DevTools** — `React Flow (xyflow)` node-cards with animated edges + a custom span flamegraph + the **Handoff Inspector**.

Shared chrome: a timeline scrubber (scrub backward, the graph replays) and a detail panel (click a node → that agent's spans/tokens/cost; click an edge → the prompt→response that crossed, diffed).

Stack: React + Vite + TypeScript, Zustand for state, Tailwind + shadcn/ui for chrome, Framer Motion for transitions, ELKjs for auto-layout of the structured graph.

## Why these libraries

The "living graph" and the "workflow diagram" are different visual problems, so swarmwatch uses a renderer per scale tier rather than forcing one library to do both: **React Flow** for the structured, node-card workflow view (rich HTML nodes, animated edges); **cosmos.gl / react-force-graph** for the force-directed living graph that has to stay smooth as a swarm grows; **react-three-fiber** for the 3D showpiece. This is the pragmatic way to get both "premium diagram" and "thousands-of-nodes alive" without compromising either.
