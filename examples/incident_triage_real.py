"""Run a *real* multi-agent incident-triage swarm against OpenRouter, instrumented
end to end with the swarmwatch SDK. Spans land live in /api/live.

This is the "this isn't a fake demo" example — every LLM call is a real model
call (defaults to claude-3.5-haiku via OpenRouter). Tool calls are mocked
strings (we don't have a real Prometheus or runbook store), but each is
emitted as its own span so the flamegraph + token counts look authentic.

Usage:
    # in one terminal
    swarmwatch up --trace swarmwatch/samples/incident_triage.jsonl

    # in another (with .venv active and OPENROUTER_API_KEY in env or .env)
    python examples/incident_triage_real.py
    open 'http://127.0.0.1:8000/?mode=live'

The dispatcher's routing line for the runbook-finder deliberately drops the
"payments-api / gateway / transaction" qualifiers, so the runbook-finder is
asked to find a runbook for "the 5xx spike" and matches the wrong service.
Click the dispatcher→runbook-finder edge in the Inspector to see it.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from openai import AsyncOpenAI

from swarmwatch.sdk import SwarmWatch


# ── env loading (no python-dotenv dependency) ────────────────────────────────
def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_env_file(Path(__file__).resolve().parent.parent / ".env")

OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY") or os.environ.get(
    "OPENROUTER_PERSONAL_KEY"
)
MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-3.5-haiku")
SWARMWATCH_ENDPOINT = os.environ.get("SWARMWATCH_ENDPOINT", "http://127.0.0.1:8000")

if not OPENROUTER_KEY:
    raise SystemExit(
        "OPENROUTER_API_KEY not set. Put it in swarmwatch/.env or export it."
    )


# ── alert + planted-bug dispatcher routing ────────────────────────────────────
ALERT = (
    "ALERT: payments-api 5xx spike — error rate 4.2%, sustained 6 minutes. "
    "Gateway p99 latency 1.8 seconds. Affects POST /v1/charge transaction "
    "endpoints. Started ~03:42 UTC."
)

# The dispatcher's routing — the runbook-finder line deliberately drops the
# "payments-api / gateway / transaction" qualifiers. THIS IS THE BUG.
DISPATCHER_ROUTING: dict[str, str] = {
    "log-analyzer":     "Grep payments-api logs in 03:42–03:48 UTC and report error patterns.",
    "deploy-checker":   "List recent deploys to payments-api and gateway; flag any near the alert time.",
    "runbook-finder":   "Find the runbook for the 5xx spike.",  # ← DEGRADED
    "db-checker":       "Inspect postgres-main pool, locks, and active queries on payments tables.",
    "config-diff":      "Diff payments-api current config vs last known good. Highlight anything changed.",
}

# Mocked "tool" results the model gets to reason over. (We don't run real
# Prometheus / log greps — that would need real infra.)
TOOL_RESULTS: dict[str, list[tuple[str, str]]] = {
    "log-analyzer": [
        ("grep_logs",
         "247 5xx errors clustered on /v1/charge. Recurring: 'ConnectionPoolFull: payments_main pool size=20 inUse=20'."),
    ],
    "deploy-checker": [
        ("list_deploys",
         "payments-api v2.34.1 (03:38 UTC, 4 min before incident); gateway v1.12.3 (yesterday); catalog-service v3.8 (3 days ago)."),
    ],
    "runbook-finder": [
        ("search_runbooks",
         "Top match: 'catalog-service-5xx-spike.md' (similarity 0.81). Other candidates: 'gateway-5xx.md' (0.74), 'rate-limit-5xx.md' (0.69)."),
    ],
    "db-checker": [
        ("query_postgres_stats",
         "Connection pool exhausted (20/20 since 03:42:05); 47 slow queries on payments_main; locks on transactions; p99 query 2.1s."),
    ],
    "config-diff": [
        ("diff_config",
         "payments-api v2.34.1 changed max_db_connections: 30 → 20 (-33%) vs v2.34.0."),
    ],
}


# ── llm helper ────────────────────────────────────────────────────────────────
client = AsyncOpenAI(api_key=OPENROUTER_KEY, base_url="https://openrouter.ai/api/v1")


async def call_llm(sw: SwarmWatch, *, system: str, user: str) -> tuple[str, int, int]:
    """One real LLM call wrapped in a swarmwatch chat span."""
    with sw.chat(MODEL, provider="openrouter", input=user) as h:
        resp = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=400,
        )
        content = resp.choices[0].message.content or ""
        in_tok = resp.usage.prompt_tokens if resp.usage else 0
        out_tok = resp.usage.completion_tokens if resp.usage else 0
        h.set_output(content)
        h.set_tokens(input_tokens=in_tok, output_tokens=out_tok)
        return content, in_tok, out_tok


# ── one investigator agent ───────────────────────────────────────────────────
async def run_investigator(
    sw: SwarmWatch, name: str, subtask: str,
) -> tuple[str, str]:
    """Open the agent span, emit its tool spans, make a real LLM call, return (name, finding)."""
    with sw.agent(name, inputs_from=["dispatcher"], input=subtask):
        tool_findings: list[str] = []
        for tool_name, tool_output in TOOL_RESULTS.get(name, []):
            with sw.tool(tool_name, output=tool_output):
                await asyncio.sleep(0.2)  # mock the tool latency
            tool_findings.append(f"[{tool_name}] {tool_output}")

        system = (
            f"You are the '{name}' agent in a production incident-triage swarm. "
            "You receive a focused subtask and a set of tool outputs. Produce a "
            "concise 2–3 sentence finding. Do not invent facts beyond the tools."
        )
        user = (
            f"Subtask: {subtask}\n\n"
            f"Tool outputs:\n" + "\n".join(tool_findings)
        )
        finding, _, _ = await call_llm(sw, system=system, user=user)
    return name, finding


# ── main ─────────────────────────────────────────────────────────────────────
async def main() -> None:
    sw = SwarmWatch(endpoint=SWARMWATCH_ENDPOINT, service="incident-triage-demo")
    print(f"posting to swarmwatch at {SWARMWATCH_ENDPOINT}")
    print(f"using model: {MODEL}\n")

    with sw.workflow("incident-triage", input=ALERT, conversation_id="conv-incident-real"):
        # 1. Dispatcher reads the alert and writes the routing plan (with the
        #    planted bug in the runbook-finder line).
        with sw.agent("dispatcher", inputs_from=[], input=ALERT,
                      conversation_id="conv-incident-real"):
            routing_text = "\n".join(f"- {a}: {sub}" for a, sub in DISPATCHER_ROUTING.items())
            with sw.chat(MODEL, provider="openrouter", input=ALERT) as h:
                resp = await client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system",
                         "content": "You are the dispatcher in an on-call swarm. "
                                    "Given a pager alert, write a short routing plan "
                                    "for the available investigators."},
                        {"role": "user",
                         "content": f"Alert: {ALERT}\n\nWrite routing for: "
                                    + ", ".join(DISPATCHER_ROUTING.keys())},
                    ],
                    max_tokens=400,
                )
                h.set_output(routing_text)  # use the planted-bug version for the swarm
                if resp.usage:
                    h.set_tokens(input_tokens=resp.usage.prompt_tokens,
                                 output_tokens=resp.usage.completion_tokens)
            print(f"dispatcher → routed to {len(DISPATCHER_ROUTING)} investigators")

        # 2. Fan-out: every investigator runs concurrently as a child of the
        #    workflow span (OTel context propagates through asyncio.gather).
        print("running investigators in parallel...")
        findings = await asyncio.gather(*[
            run_investigator(sw, name, subtask)
            for name, subtask in DISPATCHER_ROUTING.items()
        ])
        for name, finding in findings:
            short = finding.replace("\n", " ")[:90]
            print(f"  {name:<16}  {short}…")

        # 3. Synthesizer aggregates everything. It receives the runbook-finder's
        #    confident-but-wrong recommendation alongside the correct config-diff
        #    signal; the model decides what to weight.
        synth_input = "Investigator findings:\n" + "\n".join(
            f"[{n}] {f}" for n, f in findings
        )
        with sw.agent("synthesizer", inputs_from=list(DISPATCHER_ROUTING.keys()),
                      conversation_id="conv-incident-real"):
            synth_text, _, _ = await call_llm(
                sw,
                system=("You are the synthesizer in an on-call swarm. Given the "
                        "investigators' findings, identify the root cause and "
                        "recommend an action. Be decisive."),
                user=synth_input,
            )
            print(f"\nsynthesizer:\n{synth_text}\n")

        # 4. Incident summary — what the on-call human actually reads.
        with sw.agent("incident-summary", inputs_from=["synthesizer"],
                      conversation_id="conv-incident-real"):
            summary, _, _ = await call_llm(
                sw,
                system=("You are the incident-summary agent. Write the final "
                        "concise report for the on-call engineer: root cause, "
                        "recommended action, severity, impact."),
                user=synth_text,
            )
            print(f"incident summary:\n{summary}\n")

    sw.shutdown()
    print(f"done — open {SWARMWATCH_ENDPOINT}/?mode=live")


if __name__ == "__main__":
    asyncio.run(main())
