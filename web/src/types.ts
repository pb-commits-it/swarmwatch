export type Kind = "agent" | "llm" | "tool" | "workflow" | "other";

export interface Message {
  role: string;
  content: string;
}

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

/** A full span as returned by /api/trace (includes messages + parentage). */
export interface Span {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
  name: string;
  kind: Kind;
  start_time: string;
  end_time: string;
  agent: string | null;
  model: string | null;
  provider: string | null;
  tool: string | null;
  usage: { input_tokens: number; output_tokens: number };
  conversation_id: string | null;
  status: string;
  inputs_from: string[];
  input_messages: Message[];
  output_messages: Message[];
  attributes: Record<string, unknown>;
}

export interface FullTrace {
  trace_id: string;
  workflow: string | null;
  agents: AgentSummary[];
  edges: Edge[];
  spans: Span[];
  total_spans: number;
}

/** A span as it arrives over the live SSE stream (same shape as Span). */
export type SpanEvent = Span;

export const ROLE_COLORS: Record<string, string> = {
  planner: "#a78bfa",
  worker: "#38bdf8",
  judge: "#34d399",
  agent: "#94a3b8",
};

export const KIND_COLORS: Record<Kind, string> = {
  agent: "#a78bfa",
  llm: "#38bdf8",
  tool: "#fbbf24",
  workflow: "#64748b",
  other: "#64748b",
};

export function roleOf(name: string): string {
  const n = name.toLowerCase();
  if (n.includes("planner")) return "planner";
  if (n.includes("judge")) return "judge";
  if (n.includes("worker")) return "worker";
  return "agent";
}
