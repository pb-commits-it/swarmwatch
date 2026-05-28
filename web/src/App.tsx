import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { agentSpan } from "./analysis";
import DevTools from "./DevTools";
import Inspector, { InspectorState } from "./Inspector";
import LivingGraph, { Activity } from "./LivingGraph";
import { AgentSummary, FullTrace, ROLE_COLORS, roleOf, Span, SpanEvent } from "./types";

// three.js is heavy — only load the 3D view (and three) when it's opened.
const Constellation = lazy(() => import("./Constellation"));

type View = "graph" | "constellation" | "devtools";
type Mode = "replay" | "live";

interface Counters {
  spans: number;
  llm: number;
  tools: number;
  tokens: number;
}
interface Live {
  llm: number;
  tool: number;
  tokens: number;
  activeAt: number;
}
interface GraphData {
  nodes: { id: string; role: string; color: string }[];
  links: { source: string; target: string }[];
}

const ZERO: Counters = { spans: 0, llm: 0, tools: 0, tokens: 0 };

function useDimensions() {
  const ref = useRef<HTMLDivElement>(null);
  const [dim, setDim] = useState({ width: 900, height: 600 });
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      setDim({ width: r.width, height: r.height });
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, dim] as const;
}

function buildGraphData(agents: AgentSummary[], edges: { src: string; dst: string }[]): GraphData {
  const nodes = agents.map((a) => {
    const role = roleOf(a.name);
    return { id: a.name, role, color: ROLE_COLORS[role] };
  });
  const links = edges.map((e) => ({ source: e.src, target: e.dst }));
  return { nodes, links };
}

export default function App() {
  const [status, setStatus] = useState("connecting");
  const [view, setView] = useState<View>("graph");
  const [mode, setMode] = useState<Mode>("replay");
  const [workflow, setWorkflow] = useState<string | null>(null);
  const [counters, setCounters] = useState<Counters>(ZERO);
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [live, setLive] = useState<Record<string, Live>>({});
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [fullTrace, setFullTrace] = useState<FullTrace | null>(null);
  const [inspector, setInspector] = useState<InspectorState>(null);
  const [speed, setSpeed] = useState("1");

  const fgRef = useRef<any>(undefined);
  const activityRef = useRef<Map<string, Activity>>(new Map());
  const graphDataRef = useRef<GraphData | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const seenSpansRef = useRef<Set<string>>(new Set());

  const [stageRef, dim] = useDimensions();

  function emitHandoff(src: string, dst: string) {
    const gd = graphDataRef.current;
    if (!gd || !fgRef.current) return;
    const link = gd.links.find((l: any) => {
      const s = typeof l.source === "object" ? l.source.id : l.source;
      const t = typeof l.target === "object" ? l.target.id : l.target;
      return s === src && t === dst;
    });
    if (!link) return;
    let n = 0;
    const fire = () => {
      fgRef.current?.emitParticle(link);
      if (++n < 4) setTimeout(fire, 120);
    };
    fire();
  }

  function applyTopology(d: { workflow: string | null; agents: AgentSummary[]; edges: { src: string; dst: string }[] }) {
    setWorkflow(d.workflow);
    setAgents(d.agents);
    const gd = buildGraphData(d.agents, d.edges);
    graphDataRef.current = gd;
    setGraphData(gd);
    // Initialize / preserve live tallies for the agent set.
    setLive((prev) => {
      const next: Record<string, Live> = {};
      d.agents.forEach((a) => {
        next[a.name] = prev[a.name] || { llm: 0, tool: 0, tokens: 0, activeAt: 0 };
      });
      return next;
    });
  }

  function appendSpan(s: Span) {
    if (seenSpansRef.current.has(s.span_id)) return;
    seenSpansRef.current.add(s.span_id);
    setFullTrace((prev) =>
      prev ? { ...prev, spans: [...prev.spans, s], total_spans: prev.spans.length + 1 } : prev,
    );
  }

  function onSpan(s: SpanEvent) {
    const tok = (s.usage?.input_tokens || 0) + (s.usage?.output_tokens || 0);
    setCounters((c) => ({
      spans: c.spans + 1,
      llm: c.llm + (s.kind === "llm" ? 1 : 0),
      tools: c.tools + (s.kind === "tool" ? 1 : 0),
      tokens: c.tokens + (s.kind === "llm" ? tok : 0),
    }));

    if (s.agent) {
      const agent = s.agent;
      activityRef.current.set(agent, { at: performance.now(), kind: s.kind });
      setLive((prev) => {
        const cur = prev[agent] || { llm: 0, tool: 0, tokens: 0, activeAt: 0 };
        return {
          ...prev,
          [agent]: {
            llm: cur.llm + (s.kind === "llm" ? 1 : 0),
            tool: cur.tool + (s.kind === "tool" ? 1 : 0),
            tokens: cur.tokens + tok,
            activeAt: Date.now(),
          },
        };
      });
    }

    if (s.kind === "agent" && s.agent && s.inputs_from?.length) {
      for (const src of s.inputs_from) emitHandoff(src, s.agent);
    }
  }

  function resetTallies() {
    activityRef.current.clear();
    setCounters(ZERO);
    setLive((prev) => {
      const z: Record<string, Live> = {};
      Object.keys(prev).forEach((k) => (z[k] = { llm: 0, tool: 0, tokens: 0, activeAt: 0 }));
      return z;
    });
  }

  function connect(m: Mode, spd: string = speed) {
    esRef.current?.close();
    resetTallies();
    seenSpansRef.current = new Set();
    setStatus("replaying");

    const url = m === "live" ? "/api/live" : `/api/stream?speed=${spd}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.addEventListener("trace", (e: MessageEvent) => {
      try {
        const d = JSON.parse(e.data);
        if (m === "live") {
          applyTopology(d);
          setFullTrace((prev) => ({
            trace_id: d.trace_id,
            workflow: d.workflow,
            agents: d.agents,
            edges: d.edges,
            total_spans: prev?.spans.length ?? 0,
            spans: prev?.spans ?? [],
          }));
        }
      } catch {
        /* noop */
      }
      setTimeout(() => fgRef.current?.zoomToFit?.(500, 70), 300);
    });
    es.addEventListener("span", (e: MessageEvent) => {
      const s: SpanEvent = JSON.parse(e.data);
      onSpan(s);
      if (m === "live") appendSpan(s);
    });
    es.addEventListener("done", () => {
      es.close();
      setStatus("done");
    });
    es.onerror = () => {
      setStatus("disconnected");
      es.close();
    };
  }

  // First-load orchestration: figure out the initial mode from the URL, load
  // the matching topology + spans, then start streaming.
  useEffect(() => {
    let alive = true;
    const p = new URLSearchParams(window.location.search);
    const startMode: Mode = p.get("mode") === "live" ? "live" : "replay";
    setMode(startMode);

    const endpoint = startMode === "live" ? "/api/live-trace" : "/api/trace";
    fetch(endpoint)
      .then((r) => r.json())
      .then((d: FullTrace) => {
        if (!alive) return;
        setFullTrace(d);
        applyTopology({ workflow: d.workflow, agents: d.agents, edges: d.edges });
        if (startMode === "live") {
          d.spans.forEach((s) => seenSpansRef.current.add(s.span_id));
        }

        const v = p.get("view");
        if (v === "devtools" || v === "graph" || v === "constellation") setView(v);
        const src = p.get("src");
        const dst = p.get("dst");
        const span = p.get("span");
        if (src && dst) setInspector({ type: "handoff", src, dst });
        else if (span) setInspector({ type: "span", spanId: span });

        connect(startMode);
      });
    return () => {
      alive = false;
      esRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function switchMode(m: Mode) {
    if (m === mode) return;
    setMode(m);
    const endpoint = m === "live" ? "/api/live-trace" : "/api/trace";
    fetch(endpoint)
      .then((r) => r.json())
      .then((d: FullTrace) => {
        setFullTrace(d);
        applyTopology({ workflow: d.workflow, agents: d.agents, edges: d.edges });
        seenSpansRef.current = new Set();
        if (m === "live") d.spans.forEach((s) => seenSpansRef.current.add(s.span_id));
        connect(m);
      });
  }

  function inspectSpan(id: string) {
    setInspector({ type: "span", spanId: id });
  }
  function inspectHandoff(src: string, dst: string) {
    setInspector({ type: "handoff", src, dst });
  }
  function inspectNode(name: string) {
    if (!fullTrace) return;
    const s = agentSpan(fullTrace.spans, name);
    if (s) setInspector({ type: "span", spanId: s.span_id });
  }

  const statusLabel =
    status === "replaying"
      ? mode === "live"
        ? "listening"
        : "replaying"
      : status === "done"
        ? "replay complete"
        : status;
  const pillClass = status === "replaying" ? "live" : status === "done" ? "done" : "";
  const showPanels = view === "graph" || view === "constellation";
  const liveEmpty = mode === "live" && counters.spans === 0;

  return (
    <div className="app">
      <header>
        <div className="brand">
          <span className="dot" /> swarmwatch
        </div>
        <div className="tabs">
          {(
            [
              ["graph", "Living Graph"],
              ["constellation", "Constellation"],
              ["devtools", "DevTools"],
            ] as const
          ).map(([v, label]) => (
            <button
              key={v}
              className={`tab ${view === v ? "active" : ""}`}
              onClick={() => setView(v)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="tabs">
          {(
            [
              ["replay", "Sample"],
              ["live", "Live"],
            ] as const
          ).map(([m, label]) => (
            <button
              key={m}
              className={`tab ${mode === m ? "active" : ""}`}
              onClick={() => switchMode(m)}
              title={m === "live" ? "Spans pushed via POST /v1/traces" : "Bundled sample replay"}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="workflow">{workflow ? `workflow: ${workflow}` : "—"}</span>
        <span className="spacer" />
        <span className={`pill ${pillClass}`}>{statusLabel}</span>
        {mode === "replay" && (
          <>
            <select
              value={speed}
              title="Replay speed"
              onChange={(e) => {
                setSpeed(e.target.value);
                connect("replay", e.target.value);
              }}
            >
              <option value="1">1×</option>
              <option value="2">2×</option>
              <option value="4">4×</option>
              <option value="0.5">0.5×</option>
            </select>
            <button onClick={() => connect("replay")}>↻ Replay</button>
          </>
        )}
        {mode === "live" && <button onClick={() => connect("live")}>↻ Reconnect</button>}
      </header>

      <div className="counters">
        {([
          ["spans", counters.spans],
          ["agents", agents.length],
          ["llm calls", counters.llm],
          ["tool calls", counters.tools],
          ["tokens", counters.tokens],
        ] as const).map(([label, n]) => (
          <div className="counter" key={label}>
            <div className="n">{n.toLocaleString()}</div>
            <div className="l">{label}</div>
          </div>
        ))}
      </div>

      <div className="stage" ref={stageRef}>
        {view === "graph" && graphData && (
          <LivingGraph
            graphData={graphData}
            width={dim.width}
            height={dim.height}
            activityRef={activityRef}
            fgRef={fgRef}
            onLinkClick={inspectHandoff}
            onNodeClick={inspectNode}
          />
        )}

        {view === "constellation" && graphData && (
          <Suspense fallback={<div className="loading3d">loading 3D…</div>}>
            <Constellation
              graphData={graphData}
              width={dim.width}
              height={dim.height}
              fgRef={fgRef}
              onLinkClick={inspectHandoff}
              onNodeClick={inspectNode}
            />
          </Suspense>
        )}

        {showPanels && graphData && (
          <>
            <div className="float agents">
              <h2>Agents</h2>
              {agents.length === 0 && <div className="empty">no agents yet</div>}
              {agents.map((a) => {
                const l = live[a.name] || { llm: 0, tool: 0, tokens: 0, activeAt: 0 };
                const active = l.activeAt > 0 && Date.now() - l.activeAt < 1100;
                const color = ROLE_COLORS[roleOf(a.name)];
                return (
                  <div className={`agent ${active ? "active" : ""}`} key={a.name} style={{ color }}>
                    <span className="swatch" style={{ background: color }} />
                    <span className="nm">{a.name}</span>
                    <span className="ct">
                      {l.llm}·{l.tool} · {l.tokens.toLocaleString()}t
                    </span>
                  </div>
                );
              })}
            </div>
            <div className="float legend">
              <h2>Legend</h2>
              <div className="row">
                <span className="key" style={{ borderColor: "#7dd3fc" }} /> handoff — particles are
                context flowing
              </div>
              {mode === "replay" && (
                <div className="note">
                  <b>Click any edge</b> to inspect the handoff — see what one agent sent vs. what the
                  next received. Watch the planner drop “time-series” into <b>worker-1</b>; the swarm
                  then picks the wrong database. The bug lives in the edge.
                </div>
              )}
              {mode === "live" && (
                <div className="note">
                  <b>Live mode.</b> Spans posted to <code>POST&nbsp;/v1/traces</code> from any
                  OpenTelemetry-instrumented app. Try the bundled SDK:
                  <br />
                  <code>pip install 'swarmwatch[sdk]'</code>
                  <br />
                  <code>python&nbsp;examples/from_scratch_loop.py</code>
                </div>
              )}
            </div>
          </>
        )}

        {liveEmpty && view !== "devtools" && (
          <div className="live-empty">
            waiting for traces — point your OTel exporter at <code>/v1/traces</code>
          </div>
        )}

        {view === "devtools" && fullTrace && (
          <DevTools trace={fullTrace} onSpan={inspectSpan} onHandoff={inspectHandoff} />
        )}

        {fullTrace && (
          <Inspector state={inspector} trace={fullTrace} onClose={() => setInspector(null)} />
        )}
      </div>
    </div>
  );
}
