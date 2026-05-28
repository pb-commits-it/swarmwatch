import { MutableRefObject, useEffect } from "react";
import ForceGraph3D from "react-force-graph-3d";
import SpriteText from "three-spritetext";
import * as THREE from "three";
// @ts-ignore - three example module ships no bundled type declarations
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";

interface GraphData {
  nodes: { id: string; role: string; color: string }[];
  links: { source: string; target: string }[];
}

interface Props {
  graphData: GraphData;
  width: number;
  height: number;
  fgRef: MutableRefObject<any>;
  onLinkClick?: (src: string, dst: string) => void;
  onNodeClick?: (id: string) => void;
}

export default function Constellation({ graphData, width, height, fgRef, onLinkClick, onNodeClick }: Props) {
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.d3Force("charge")?.strength(-200);
    // Bloom gives the emissive "constellation" glow on a near-black scene.
    // Kept restrained (low strength, higher threshold) so only the node cores
    // bloom rather than washing the whole scene out.
    try {
      const bloom = new UnrealBloomPass(new THREE.Vector2(width || 1200, height || 800), 0.7, 0.4, 0.2);
      fg.postProcessingComposer().addPass(bloom);
    } catch {
      /* composer not ready in this environment */
    }
    // Slow auto-rotation for the showpiece (orbit controls expose autoRotate).
    // Disable with ?rotate=0 (e.g. for static screenshots).
    const wantRotate = new URLSearchParams(window.location.search).get("rotate") !== "0";
    const controls = fg.controls?.();
    if (controls) {
      controls.autoRotate = wantRotate;
      controls.autoRotateSpeed = 0.85;
    }
    setTimeout(() => fg.zoomToFit?.(800, 90), 500);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData]);

  return (
    <ForceGraph3D
      ref={fgRef}
      graphData={graphData}
      width={width}
      height={height}
      backgroundColor="#04070d"
      controlType="orbit"
      showNavInfo={false}
      dagMode="td"
      dagLevelDistance={72}
      nodeColor={(n: any) => n.color}
      nodeOpacity={0.95}
      nodeResolution={20}
      nodeRelSize={4}
      linkColor={() => "rgba(125,145,175,0.35)"}
      linkWidth={0.6}
      linkOpacity={0.55}
      linkDirectionalParticles={0}
      linkDirectionalParticleSpeed={0.012}
      linkDirectionalParticleWidth={2.4}
      linkDirectionalParticleColor={() => "#7dd3fc"}
      nodeThreeObjectExtend={true}
      nodeThreeObject={(node: any) => {
        const label = new SpriteText(node.id);
        label.color = "#d7e2f5";
        label.textHeight = 4;
        label.position.set(0, -9, 0);
        return label;
      }}
      onNodeClick={(node: any) => onNodeClick?.(node.id)}
      onLinkClick={(link: any) => {
        const s = typeof link.source === "object" ? link.source.id : link.source;
        const t = typeof link.target === "object" ? link.target.id : link.target;
        onLinkClick?.(s, t);
      }}
    />
  );
}
