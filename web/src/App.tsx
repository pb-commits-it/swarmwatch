import { useEffect, useRef, useState } from "react";
import LivingGraph, { Activity } from "./LivingGraph";
import { AgentSummary, ROLE_COLORS, roleOf, SpanEvent, TraceSummary } from "./types";

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

export default function App() {
  const [status, setStatus] = useState("connecting");
  const [workflow, setWorkflow] = useState<string | null>(null);
  const [counters, setCounters] = useState<Counters>(ZERO);
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [live, setLive] = useState<Record<string, Live>>({});
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [speed, setSpeed] = useState("1");

  const fgRef = useRef<any>(undefined);
  const activityRef = useRef<Map<string, Activity>>(new Map());
  const graphDataRef = useRef<GraphData | null>(null);
  const esRef = useRef<EventSource | null>(null);

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

  function connect(spd: string = speed) {
    esRef.current?.close();
    activityRef.current.clear();
    setCounters(ZERO);
    setLive({});
    setStatus("replaying");

    const es = new EventSource(`/api/stream?speed=${spd}`);
    esRef.current = es;

    es.addEventListener("trace", (e: MessageEvent) => {
      const d: TraceSummary = JSON.parse(e.data);
      setWorkflow(d.workflow);
      setAgents(d.agents);
      const nodes = d.agents.map((a) => {
        const role = roleOf(a.name);
        return { id: a.name, role, color: ROLE_COLORS[role] };
      });
      const links = d.edges.map((ed) => ({ source: ed.src, target: ed.dst }));
      const gd: GraphData = { nodes, links };
      graphDataRef.current = gd;
      setGraphData(gd);
      const init: Record<string, Live> = {};
      d.agents.forEach((a) => (init[a.name] = { llm: 0, tool: 0, tokens: 0, activeAt: 0 }));
      setLive(init);
      setTimeout(() => fgRef.current?.zoomToFit(500, 70), 450);
    });
    es.addEventListener("span", (e: MessageEvent) => onSpan(JSON.parse(e.data)));
    es.addEventListener("done", () => {
      es.close();
      setStatus("done");
    });
    es.onerror = () => {
      setStatus("disconnected");
      es.close();
    };
  }

  useEffect(() => {
    connect();
    return () => esRef.current?.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const statusLabel =
    status === "replaying" ? "replaying" : status === "done" ? "replay complete" : status;
  const pillClass = status === "replaying" ? "live" : status === "done" ? "done" : "";

  return (
    <div className="app">
      <header>
        <div className="brand">
          <span className="dot" /> swarmwatch
        </div>
        <span className="workflow">{workflow ? `workflow: ${workflow}` : "—"}</span>
        <span className="spacer" />
        <span className={`pill ${pillClass}`}>{statusLabel}</span>
        <select
          value={speed}
          title="Replay speed"
          onChange={(e) => {
            setSpeed(e.target.value);
            connect(e.target.value);
          }}
        >
          <option value="1">1×</option>
          <option value="2">2×</option>
          <option value="4">4×</option>
          <option value="0.5">0.5×</option>
        </select>
        <button onClick={() => connect()}>↻ Replay</button>
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
        {graphData && (
          <LivingGraph
            graphData={graphData}
            width={dim.width}
            height={dim.height}
            activityRef={activityRef}
            fgRef={fgRef}
          />
        )}

        <div className="float agents">
          <h2>Agents</h2>
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
            <span className="key" style={{ borderColor: "#7dd3fc" }} /> handoff — particles are context flowing
          </div>
          <div className="note">
            Watch the <b>planner</b> drop the “time-series” qualifier when it hands off to{" "}
            <b>worker-1</b> — the swarm then recommends the wrong database. The bug lives in the
            edge, not the node.
          </div>
        </div>
      </div>
    </div>
  );
}
