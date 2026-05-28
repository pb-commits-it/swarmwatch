import { MutableRefObject, useEffect } from "react";
import ForceGraph2D from "react-force-graph-2d";

export interface Activity {
  at: number;
  kind: string;
}

interface GraphData {
  nodes: { id: string; role: string; color: string }[];
  links: { source: string; target: string }[];
}

interface Props {
  graphData: GraphData;
  width: number;
  height: number;
  activityRef: MutableRefObject<Map<string, Activity>>;
  fgRef: MutableRefObject<any>;
  onLinkClick?: (src: string, dst: string) => void;
  onNodeClick?: (id: string) => void;
}

function withAlpha(hex: string, a: number): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
}

export default function LivingGraph({
  graphData,
  width,
  height,
  activityRef,
  fgRef,
  onLinkClick,
  onNodeClick,
}: Props) {
  // Spread siblings (e.g. parallel workers) apart so their labels don't collide,
  // and give edges a bit more length for the top-down flow to breathe.
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.d3Force("charge")?.strength(-340);
    fg.d3Force("link")?.distance(70);
    fg.d3ReheatSimulation();
  }, [graphData, fgRef]);

  return (
    <ForceGraph2D
      ref={fgRef}
      graphData={graphData}
      width={width}
      height={height}
      backgroundColor="#070b12"
      dagMode="td"
      dagLevelDistance={64}
      cooldownTicks={140}
      d3VelocityDecay={0.28}
      linkColor={() => "rgba(120,140,170,0.28)"}
      linkWidth={2}
      onNodeClick={(node: any) => onNodeClick?.(node.id)}
      onLinkClick={(link: any) => {
        const s = typeof link.source === "object" ? link.source.id : link.source;
        const t = typeof link.target === "object" ? link.target.id : link.target;
        onLinkClick?.(s, t);
      }}
      linkDirectionalParticles={0}
      linkDirectionalParticleSpeed={0.012}
      linkDirectionalParticleWidth={3}
      linkDirectionalParticleColor={() => "#7dd3fc"}
      nodeCanvasObjectMode={() => "replace"}
      nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, scale: number) => {
        const now = performance.now();
        const act = activityRef.current.get(node.id);
        const since = act ? now - act.at : Infinity;
        const pulse = since < 1100 ? 1 - since / 1100 : 0;
        const r = 6 + pulse * 4;

        // outer glow halo while active
        if (pulse > 0) {
          ctx.beginPath();
          ctx.arc(node.x, node.y, r + 9 * pulse, 0, 2 * Math.PI);
          ctx.fillStyle = withAlpha(node.color, 0.18 * pulse);
          ctx.fill();
        }

        // node body with a soft bloom
        ctx.beginPath();
        ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
        ctx.fillStyle = node.color;
        ctx.shadowColor = node.color;
        ctx.shadowBlur = 10 + pulse * 16;
        ctx.fill();
        ctx.shadowBlur = 0;

        // dark core so the node reads as a ring
        ctx.beginPath();
        ctx.arc(node.x, node.y, r * 0.42, 0, 2 * Math.PI);
        ctx.fillStyle = "#070b12";
        ctx.fill();

        // label
        const fontSize = Math.max(3.2, 12 / scale);
        ctx.font = `600 ${fontSize}px ui-monospace, monospace`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = "#c9d6ee";
        ctx.fillText(node.id, node.x, node.y + r + 3);
      }}
    />
  );
}
