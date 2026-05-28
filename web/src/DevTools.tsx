import { FullTrace, KIND_COLORS } from "./types";

interface Props {
  trace: FullTrace;
  onSpan: (id: string) => void;
  onHandoff: (src: string, dst: string) => void;
}

export default function DevTools({ trace, onSpan, onHandoff }: Props) {
  const spans = [...trace.spans].sort((a, b) => a.start_time.localeCompare(b.start_time));
  const starts = spans.map((s) => new Date(s.start_time).getTime());
  const ends = spans.map((s) => new Date(s.end_time).getTime());
  const t0 = Math.min(...starts);
  const t1 = Math.max(...ends);
  const total = Math.max(1, t1 - t0);

  return (
    <div className="devtools">
      <section className="dt-handoffs">
        <h3>
          Handoffs <span className="hint">— click to inspect the context that crossed</span>
        </h3>
        <div className="chips">
          {trace.edges.map((e) => (
            <button className="handoff-chip" key={`${e.src}-${e.dst}`} onClick={() => onHandoff(e.src, e.dst)}>
              {e.src} <span className="arrow">→</span> {e.dst}
            </button>
          ))}
        </div>
      </section>

      <section className="dt-flame">
        <h3>
          Span timeline <span className="hint">— {Math.round(total)}ms total · click a span for detail</span>
        </h3>
        <div className="flame">
          {spans.map((s) => {
            const left = ((new Date(s.start_time).getTime() - t0) / total) * 100;
            const width = Math.max(0.8, ((new Date(s.end_time).getTime() - new Date(s.start_time).getTime()) / total) * 100);
            const dur = Math.round(new Date(s.end_time).getTime() - new Date(s.start_time).getTime());
            const detail = s.kind === "llm" ? s.model : s.kind === "tool" ? s.tool : s.name;
            return (
              <div className="frow" key={s.span_id} onClick={() => onSpan(s.span_id)}>
                <div className="flabel">
                  <span className="fchip" style={{ background: KIND_COLORS[s.kind] }} />
                  <span className="fagent">{s.agent || "—"}</span>
                  <span className="fname">{detail}</span>
                </div>
                <div className="ftrack">
                  <div
                    className="fbar"
                    style={{ left: `${left}%`, width: `${width}%`, background: KIND_COLORS[s.kind] }}
                    title={`${dur}ms`}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
