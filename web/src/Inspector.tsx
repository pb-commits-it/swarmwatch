import { ReactNode } from "react";
import { agentSpan, buildAgentIO, droppedTerms, originalRequest, spanById, textOf } from "./analysis";
import { FullTrace, ROLE_COLORS, roleOf } from "./types";

export type InspectorState =
  | { type: "handoff"; src: string; dst: string }
  | { type: "span"; spanId: string }
  | null;

const roleColor = (n: string) => ROLE_COLORS[roleOf(n)];

function Section({ label, children, muted }: { label: string; children: ReactNode; muted?: boolean }) {
  return (
    <div className={`insp-section ${muted ? "muted" : ""}`}>
      <div className="insp-label">{label}</div>
      <div className="insp-text">{children}</div>
    </div>
  );
}

function Handoff({ trace, src, dst }: { trace: FullTrace; src: string; dst: string }) {
  const io = buildAgentIO(trace.spans);
  const orig = originalRequest(trace.spans);
  const sent = io[src]?.output?.length
    ? textOf(io[src].output)
    : io[src]?.input?.length
      ? textOf(io[src].input)
      : "—";
  const received = io[dst]?.input?.length ? textOf(io[dst].input) : "—";
  const dropped = droppedTerms(orig, received);

  return (
    <>
      <div className="edge-title">
        <b style={{ color: roleColor(src) }}>{src}</b> → <b style={{ color: roleColor(dst) }}>{dst}</b>
      </div>
      {dropped.length > 0 && (
        <div className="warn">
          ⚠ {dropped.length} term{dropped.length > 1 ? "s" : ""} from the original request didn’t
          survive this handoff:
          <div className="terms">
            {dropped.slice(0, 14).map((t) => (
              <span className="term" key={t}>
                {t}
              </span>
            ))}
          </div>
        </div>
      )}
      <Section label={`What ${src} produced`}>{sent}</Section>
      <Section label={`What ${dst} received`}>{received}</Section>
      <Section label="Original request" muted>
        {orig}
      </Section>
    </>
  );
}

function SpanDetail({ trace, spanId }: { trace: FullTrace; spanId: string }) {
  const s = spanById(trace.spans, spanId);
  if (!s) return <div className="insp-text">span not found</div>;
  const dur = Math.round(new Date(s.end_time).getTime() - new Date(s.start_time).getTime());
  return (
    <>
      <div className="edge-title">
        <span className={`chip ${s.kind}`}>{s.kind}</span> {s.name}
      </div>
      <div className="kv"><span>agent</span><b>{s.agent || "—"}</b></div>
      {s.model && <div className="kv"><span>model</span><b>{s.model}</b></div>}
      {s.tool && <div className="kv"><span>tool</span><b>{s.tool}</b></div>}
      <div className="kv"><span>tokens</span><b>{s.usage.input_tokens} + {s.usage.output_tokens}</b></div>
      <div className="kv"><span>duration</span><b>{dur}ms</b></div>
      <div className="kv"><span>status</span><b>{s.status}</b></div>
      {s.input_messages.length > 0 && <Section label="input">{textOf(s.input_messages)}</Section>}
      {s.output_messages.length > 0 && <Section label="output">{textOf(s.output_messages)}</Section>}
    </>
  );
}

interface Props {
  state: InspectorState;
  trace: FullTrace;
  onClose: () => void;
}

export default function Inspector({ state, trace, onClose }: Props) {
  if (!state) return null;
  return (
    <aside className="inspector">
      <div className="insp-head">
        <span>{state.type === "handoff" ? "Handoff inspector" : "Span detail"}</span>
        <button className="x" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>
      <div className="insp-body">
        {state.type === "handoff" ? (
          <Handoff trace={trace} src={state.src} dst={state.dst} />
        ) : (
          <SpanDetail trace={trace} spanId={state.spanId} />
        )}
      </div>
    </aside>
  );
}

export { agentSpan };
