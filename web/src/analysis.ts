import { Message, Span } from "./types";

export function textOf(msgs: Message[]): string {
  return msgs.map((m) => m.content).join("\n");
}

/** The user's original request — the workflow span's input, or the earliest agent input. */
export function originalRequest(spans: Span[]): string {
  const wf = spans.find((s) => s.kind === "workflow" && s.input_messages.length > 0);
  if (wf) return textOf(wf.input_messages);
  const agent = [...spans]
    .sort((a, b) => a.start_time.localeCompare(b.start_time))
    .find((s) => s.kind === "agent" && s.input_messages.length > 0);
  return agent ? textOf(agent.input_messages) : "";
}

export interface AgentIO {
  input: Message[];
  output: Message[];
}

/** What each agent received (its invoke input) and produced (its last LLM output). */
export function buildAgentIO(spans: Span[]): Record<string, AgentIO> {
  const io: Record<string, AgentIO> = {};
  const sorted = [...spans].sort((a, b) => a.start_time.localeCompare(b.start_time));
  for (const s of sorted) {
    if (!s.agent) continue;
    if (!io[s.agent]) io[s.agent] = { input: [], output: [] };
    if (s.kind === "agent" && s.input_messages.length > 0) io[s.agent].input = s.input_messages;
    if (s.kind === "llm" && s.output_messages.length > 0) io[s.agent].output = s.output_messages;
  }
  return io;
}

const STOP = new Set([
  "the", "and", "for", "our", "with", "into", "over", "need", "from", "that",
  "this", "what", "best", "find", "your", "you", "are", "was", "will", "then",
  "than", "them", "they", "its", "use", "using", "also", "store", "storing",
]);

function terms(text: string): string[] {
  return text
    .toLowerCase()
    .split(/\s+/)
    .map((w) => w.replace(/^[^a-z0-9-]+|[^a-z0-9-]+$/g, ""))
    .filter((w) => w.length >= 4 && !STOP.has(w));
}

/** Significant terms in `original` that don't appear in `received` — context lost in the handoff. */
export function droppedTerms(original: string, received: string): string[] {
  const recv = new Set(terms(received));
  const seen = new Set<string>();
  const out: string[] = [];
  for (const t of terms(original)) {
    if (!recv.has(t) && !seen.has(t)) {
      seen.add(t);
      out.push(t);
    }
  }
  return out;
}

export function spanById(spans: Span[], id: string): Span | undefined {
  return spans.find((s) => s.span_id === id);
}

export function agentSpan(spans: Span[], agent: string): Span | undefined {
  return spans.find((s) => s.kind === "agent" && s.agent === agent);
}
