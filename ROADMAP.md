# Roadmap

swarmwatch ships in public, in stages. Each release is a self-contained, *working* slice — no half-built stubs. Tags below map to GitHub releases.

---

### v0.1 — *It records*
The pipe, end to end.
- Internal span model + causal-DAG builder
- OTLP/HTTP receiver; normalize **OpenTelemetry GenAI** and **OpenInference** spans into one model
- File **replay** (`.jsonl` / OTLP dump → same pipeline) so the demo runs offline and deterministically
- DuckDB-backed trace store
- A bundled **planner→worker→judge** sample trace
- Minimal web view: spans landing live over SSE

_Exit: a recorded trace flows from ingest to browser._

### v0.2 — *It comes alive*
The hero.
- 2D **Living Graph** (cosmos.gl / react-force-graph): agents as nodes, particle-flow edges on handoffs, nodes pulsing on tool calls, dark canvas + glow
- Live mode (SSE) + replay mode with a **timeline scrubber**

_Exit: the looping hero GIF exists._

### v0.3 — *It debugs*
The "not a toy" proof.
- **DevTools** view: React Flow structured workflow graph + custom span **flamegraph**
- **Handoff Inspector**: click an edge → the literal prompt/response that crossed between agents, diffed to surface lossy summarization
- Causal root-cause trace: click a bad output, walk backward to where it broke

_Exit: you can find a real bug in the space between agents._

### v0.4 — *It's beautiful*
The showpiece.
- 3D **Constellation** (react-three-fiber + bloom)
- View-mode switcher across Living Graph / Constellation / DevTools
- Motion polish: spring entry, hover halos, edge-draw easing

_Exit: the showpiece video exists._

### v1.0 — *Launch*
- Thin Python **decorator SDK** (`@swarmwatch.agent / .tool / .llm`) for a 10-second quickstart
- "Point your OTel exporter here" docs
- Worked examples: LangGraph, CrewAI, from-scratch loop
- **Hosted live demo** (replay mode — no backend needed for viewers)
- Tests + CI; `ARCHITECTURE.md` finalized

_Exit: anyone can `pip install`, see the demo in 10 seconds, and instrument their own swarm._
