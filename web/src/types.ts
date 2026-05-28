export type Kind = "agent" | "llm" | "tool" | "workflow" | "other";

export interface AgentSummary {
  name: string;
  llm_calls: number;
  tool_calls: number;
  input_tokens: number;
  output_tokens: number;
  inputs_from: string[];
  status: string;
}

export interface Edge {
  src: string;
  dst: string;
}

export interface TraceSummary {
  trace_id: string;
  workflow: string | null;
  agents: AgentSummary[];
  edges: Edge[];
  total_spans: number;
}

export interface SpanEvent {
  span_id: string;
  kind: Kind;
  agent: string | null;
  model: string | null;
  tool: string | null;
  name: string;
  start_time: string;
  end_time: string;
  usage: { input_tokens: number; output_tokens: number };
  inputs_from: string[];
}

export const ROLE_COLORS: Record<string, string> = {
  planner: "#a78bfa",
  worker: "#38bdf8",
  judge: "#34d399",
  agent: "#94a3b8",
};

export function roleOf(name: string): string {
  const n = name.toLowerCase();
  if (n.includes("planner")) return "planner";
  if (n.includes("judge")) return "judge";
  if (n.includes("worker")) return "worker";
  return "agent";
}
