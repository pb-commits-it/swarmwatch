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

### v0.2 — *It comes alive* ✅
The hero.
- 2D **Living Graph** (react-force-graph): agents as nodes in a top-down DAG, particle-flow edges on handoffs, nodes pulsing on LLM/tool calls, dark canvas + glow — ✅
- React + Vite + TypeScript frontend, built into the package and served by FastAPI — ✅
- Replay + speed control over SSE — ✅
- A draggable **timeline scrubber** (scrub backward through a run) — deferred to v0.3

_Exit: the looping hero GIF exists._

### v0.3 — *It debugs* ✅
The "not a toy" proof.
- **DevTools** view: a span **flamegraph** (timeline waterfall) + a clickable handoffs list — ✅
- **Handoff Inspector**: click an edge → what one agent produced vs. what the next received, with the terms from the original request that didn't survive the handoff flagged — ✅
- Deep links (`?view=`, `?src=&dst=`, `?span=`) to share a specific handoff or span — ✅ (bonus)
- View switcher across Living Graph / DevTools — ✅
- Causal root-cause trace (click a bad output, walk backward to the break) — deferred; the dropped-term diff is the first cut of this

_Exit: you can find a real bug in the space between agents._ ✅

### v0.4 — *It's beautiful* ✅
The showpiece.
- 3D **Constellation** (react-force-graph-3d + three.js + UnrealBloomPass) — emissive nodes with bloom, particle handoffs, slow auto-rotation — ✅
- View-mode switcher across Living Graph / Constellation / DevTools — ✅
- Lazy-loaded so three.js only downloads when the 3D tab is opened (initial bundle stays ~350 KB) — ✅
- `?rotate=0` flag to capture a static frame — ✅
- Motion polish: spring entry, hover halos, edge-draw easing — _later (polish pass before v1.0)_

_Exit: the showpiece video exists._

### v1.0 — *Launch*
- Thin Python **decorator SDK** (`@swarmwatch.agent / .tool / .llm`) for a 10-second quickstart
- "Point your OTel exporter here" docs
- Worked examples: LangGraph, CrewAI, from-scratch loop
- **Hosted live demo** (replay mode — no backend needed for viewers)
- Tests + CI; `ARCHITECTURE.md` finalized

_Exit: anyone can `pip install`, see the demo in 10 seconds, and instrument their own swarm._
