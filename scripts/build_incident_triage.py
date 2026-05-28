"""Generate the bundled `incident_triage.jsonl` sample trace.

A 18-agent production-incident-triage swarm: a dispatcher receives a pager
alert, fans out to 12 investigators (some of which spawn sub-agents), then a
synthesizer aggregates and an incident-summary writes the final recommendation.

The planted bug: the dispatcher's routing subtask for the *runbook-finder*
drops the "payments-api / gateway / transaction" qualifiers, so the runbook-
finder retrieves a runbook for the wrong service and the synthesizer — trusting
runbook authority — recommends rolling back `catalog-service` when the real
root cause is a `payments-api` DB-pool config change.

Run this once; it writes the sample into the package.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "swarmwatch" / "samples" / "incident_triage.jsonl"

TRACE_ID = "trace-incident-2412"
CONV_ID = "conv-incident-2412"
T0 = datetime(2026, 5, 27, 3, 42, 0, tzinfo=timezone.utc)


def ts(secs: float) -> str:
    t = T0 + timedelta(seconds=secs)
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


spans: list[dict] = []


def emit(span: dict) -> None:
    spans.append(span)


def workflow_span(span_id: str, name: str, start: float, end: float, input_text: str) -> None:
    emit({
        "trace_id": TRACE_ID, "span_id": span_id, "parent_span_id": None,
        "name": f"invoke_workflow {name}",
        "start_time": ts(start), "end_time": ts(end),
        "attributes": {
            "gen_ai.operation.name": "invoke_workflow",
            "gen_ai.conversation.id": CONV_ID,
            "gen_ai.input.messages": [{"role": "user", "content": input_text}],
        },
    })


def agent_span(span_id: str, parent: str | None, name: str, start: float, end: float,
               inputs_from: list[str], input_text: str | None = None) -> None:
    attrs: dict = {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": name,
        "gen_ai.conversation.id": CONV_ID,
        "swarmwatch.inputs_from": list(inputs_from),
    }
    if input_text is not None:
        attrs["gen_ai.input.messages"] = [{"role": "user", "content": input_text}]
    emit({
        "trace_id": TRACE_ID, "span_id": span_id, "parent_span_id": parent,
        "name": f"invoke_agent {name}",
        "start_time": ts(start), "end_time": ts(end),
        "attributes": attrs,
    })


def llm_span(span_id: str, parent: str, start: float, end: float,
             input_tokens: int = 0, output_tokens: int = 0,
             output: str | None = None, input_text: str | None = None,
             model: str = "grok-4.20-beta", provider: str = "xai") -> None:
    attrs: dict = {
        "gen_ai.operation.name": "chat",
        "gen_ai.request.model": model,
        "gen_ai.provider.name": provider,
        "gen_ai.usage.input_tokens": input_tokens,
        "gen_ai.usage.output_tokens": output_tokens,
    }
    if input_text is not None:
        attrs["gen_ai.input.messages"] = [{"role": "user", "content": input_text}]
    if output is not None:
        attrs["gen_ai.output.messages"] = [{"role": "assistant", "content": output}]
    emit({
        "trace_id": TRACE_ID, "span_id": span_id, "parent_span_id": parent,
        "name": f"chat {model}",
        "start_time": ts(start), "end_time": ts(end),
        "attributes": attrs,
    })


def tool_span(span_id: str, parent: str, name: str, start: float, end: float,
              output: str | None = None) -> None:
    attrs: dict = {
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": name,
    }
    if output is not None:
        attrs["gen_ai.output.messages"] = [{"role": "tool", "content": output}]
    emit({
        "trace_id": TRACE_ID, "span_id": span_id, "parent_span_id": parent,
        "name": f"execute_tool {name}",
        "start_time": ts(start), "end_time": ts(end),
        "attributes": attrs,
    })


# ───────────────────────────────────────────────────────────────────────────────
# Topology
# ───────────────────────────────────────────────────────────────────────────────

ALERT = (
    "ALERT: payments-api 5xx spike — error rate 4.2%, sustained 6 minutes. "
    "Gateway p99 latency 1.8 seconds. Affects POST /v1/charge transaction "
    "endpoints. Started ~03:42 UTC."
)

# 0. workflow root
workflow_span("wf", "incident-triage", 0.0, 14.5, ALERT)

# 1. dispatcher reads the alert and writes a routing plan
agent_span("a-disp", "wf", "dispatcher", 0.10, 1.00, inputs_from=[], input_text=ALERT)
llm_span(
    "l-disp", "a-disp", 0.20, 0.90,
    input_tokens=620, output_tokens=340,
    output=(
        "Routing plan:\n"
        "- log-analyzer: grep payments-api logs in the alert window\n"
        "- metric-correlator: correlate metrics across involved services\n"
        "- deploy-checker: enumerate recent deploys to payments-api and gateway\n"
        "- dependency-health: check payments-api downstream services\n"
        "- error-budget: compute SLO burn\n"
        "- runbook-finder: find the runbook for the 5xx spike\n"
        "- customer-impact / traffic-source / cache-checker / db-checker / "
        "config-diff / on-call-history: parallel investigation"
    ),
)

# ── Layer 2: investigators ─────────────────────────────────────────────────────
#   (name, start, end, subtask, [(tool_name, t_offset, t_dur, output)], llm_out,
#    in_tok, out_tok)
INVESTIGATORS: list[tuple] = [
    (
        "log-analyzer", 1.10, 4.00,
        "Grep payments-api logs in window 03:42–03:48 UTC. Find error patterns.",
        [
            ("grep_logs", 0.20, 0.65,
             "247 5xx errors clustered on /v1/charge endpoint. Recurring: "
             "'ConnectionPoolFull: payments_main pool size=20 inUse=20'."),
            ("fetch_log_excerpt", 1.00, 0.55,
             "Sample: 03:43:11Z payments-api ERR ConnectionPoolFull "
             "request_id=7af9 endpoint=/v1/charge"),
        ],
        "Logs show DB connection-pool exhaustion in payments-api during the "
        "window; failures concentrated on POST /v1/charge.",
        1240, 380,
    ),
    (
        "metric-correlator", 1.20, 3.80,
        "Correlate metrics across services for the alert window.",
        [
            ("query_prometheus", 0.30, 0.70,
             "payments-api CPU 92%, postgres-main connections 100%, gateway 504s "
             "correlated (r=0.94)."),
            ("query_grafana", 1.20, 0.60,
             "Anomaly score 9.4/10 for payments-api.cpu and postgres.pool_used; "
             "onset at 03:42:08 UTC."),
        ],
        "Strong correlation between payments-api saturation and the gateway "
        "5xx spike. Onset matches the alert.",
        1120, 360,
    ),
    (
        "deploy-checker", 1.10, 2.50,
        "List recent deploys to payments-api and gateway.",
        [
            ("list_deploys", 0.20, 0.55,
             "payments-api v2.34.1 (03:38 UTC, 4 min before incident); "
             "gateway v1.12.3 (yesterday); catalog-service v3.8 (3 days ago)."),
        ],
        "Recent payments-api deploy (T-4 min) is a strong suspect.",
        860, 240,
    ),
    (
        "dependency-health", 1.30, 4.50,
        "Check payments-api downstream services.",
        [
            ("check_downstream", 0.30, 0.65,
             "ledger-service: healthy; fraud-check: healthy; postgres-main: "
             "connection pool 98% saturated."),
        ],
        "Postgres pool saturation is the proximate constraint; upstream "
        "dependencies otherwise healthy.",
        960, 310,
    ),
    (
        "error-budget", 1.40, 2.60,
        "Compute SLO burn rate and remaining error budget.",
        [
            ("fetch_slo", 0.20, 0.55,
             "Monthly SLO 99.95%; current 30-day burn rate 8.2x; remaining "
             "error budget: 11 minutes."),
        ],
        "Critical: error budget exhausts in ~11 minutes at current rate.",
        720, 210,
    ),
    # ⚠ THE PLANTED BUG ⚠
    # The dispatcher's routing line for this agent stripped the "payments-api /
    # gateway / transaction" qualifiers. The runbook-finder receives a generic
    # "5xx spike" query and matches the wrong runbook (catalog-service).
    (
        "runbook-finder", 1.50, 3.90,
        "Find the runbook for the 5xx spike.",
        [
            ("search_runbooks", 0.30, 0.85,
             "Top match: 'catalog-service-5xx-spike.md' (similarity 0.81). "
             "Other candidates: 'gateway-5xx.md' (0.74), "
             "'rate-limit-5xx.md' (0.69)."),
        ],
        "Runbook matched: catalog-service-5xx-spike. Recommended action: "
        "roll back catalog-service to the previous stable version (v2.34.1). "
        "Confidence: high — runbook explicitly covers this 5xx pattern.",
        940, 320,
    ),
    (
        "customer-impact", 1.60, 3.00,
        "Estimate user impact and revenue effect.",
        [
            ("query_user_metrics", 0.20, 0.50,
             "12,400 affected users; 8.2% checkout failure rate; revenue "
             "impact ~$48k / minute."),
        ],
        "High customer impact — checkout flow degraded for ~8% of users.",
        790, 240,
    ),
    (
        "traffic-source", 1.70, 3.40,
        "Identify which routes / clients are hit hardest.",
        [
            ("query_traffic", 0.20, 0.70,
             "POST /v1/charge accounts for 85% of 5xx; iOS app 70% of "
             "failures; web checkout 22%."),
        ],
        "Failures concentrated on POST /v1/charge from mobile clients.",
        830, 250,
    ),
    (
        "cache-checker", 1.80, 2.90,
        "Check upstream cache health.",
        [
            ("check_redis", 0.20, 0.55,
             "Hit rate dropped 94%→71% at 03:40 UTC; eviction rate 4× normal."),
        ],
        "Cache degradation correlated but secondary to the DB pool issue.",
        710, 220,
    ),
    (
        "db-checker", 1.90, 4.60,
        "Inspect database health and active queries.",
        [
            ("query_postgres_stats", 0.20, 0.70,
             "Connection pool exhausted; locks on transactions table; p99 "
             "query latency 2.1s."),
            ("check_active_queries", 1.20, 0.95,
             "47 slow queries on payments_main; lock waits up 12×; pool "
             "used/total = 20/20 since 03:42:05 UTC."),
        ],
        "Database connection pool exhausted on payments_main. Proximate cause "
        "is at the pool layer — investigate why the pool can no longer absorb "
        "load.",
        1470, 420,
    ),
    (
        "config-diff", 2.00, 3.40,
        "Compare current config to last known good across involved services.",
        [
            ("diff_config", 0.30, 0.60,
             "payments-api v2.34.1 changed `max_db_connections`: 30 → 20 "
             "(-33%) vs v2.34.0."),
        ],
        "v2.34.1 reduced max_db_connections from 30 to 20. Under current "
        "request volume the new ceiling can't accommodate peak concurrency — "
        "**this is the likely root cause.**",
        890, 290,
    ),
    (
        "on-call-history", 2.10, 3.50,
        "Search recent similar incidents.",
        [
            ("search_incidents", 0.20, 0.60,
             "INC-2261 (14 days ago): similar 5xx on payments-api, resolved "
             "by reverting a db-pool config change."),
        ],
        "Strong precedent: INC-2261 was resolved by reverting a payments-api "
        "DB-pool config change.",
        770, 230,
    ),
]


def _emit_investigator(
    name: str, start: float, end: float, subtask: str,
    tools: list[tuple[str, float, float, str]],
    llm_out: str, in_tok: int, out_tok: int,
) -> None:
    aid = f"a-{name}"
    agent_span(aid, "wf", name, start, end, inputs_from=["dispatcher"], input_text=subtask)
    for j, (tname, toff, tdur, tout) in enumerate(tools):
        tool_span(f"t-{name}-{j}", aid, tname, start + toff, start + toff + tdur, output=tout)
    llm_start = start + max((toff + tdur for _, toff, tdur, _ in tools), default=0.2) + 0.10
    llm_end = end - 0.05
    llm_span(f"l-{name}", aid, llm_start, llm_end, input_tokens=in_tok, output_tokens=out_tok, output=llm_out)


for cfg in INVESTIGATORS:
    _emit_investigator(*cfg)

# ── Sub-agents spawned by investigators ───────────────────────────────────────
# error-pattern-clusterer (spawned by log-analyzer)
agent_span("a-epc", "a-log-analyzer", "error-pattern-clusterer", 2.00, 3.20,
           inputs_from=["log-analyzer"])
llm_span("l-epc", "a-epc", 2.10, 3.15, input_tokens=480, output_tokens=180,
         output="Clusters: (1) connection-pool exhaustion 87%, (2) lock waits 10%, (3) misc 3%.")

# security-checker (spawned by log-analyzer)
agent_span("a-sec", "a-log-analyzer", "security-checker", 2.50, 3.65,
           inputs_from=["log-analyzer"])
tool_span("t-sec-0", "a-sec", "scan_for_anomaly", 2.60, 3.00,
          output="No suspicious patterns; no auth anomalies; no injection vectors.")
llm_span("l-sec", "a-sec", 3.10, 3.60, input_tokens=430, output_tokens=110,
         output="Not security-related. Pattern is consistent with capacity exhaustion.")

# health-prober (spawned by dependency-health)
agent_span("a-hp", "a-dependency-health", "health-prober", 2.80, 4.20,
           inputs_from=["dependency-health"])
tool_span("t-hp-0", "a-hp", "probe_endpoints", 2.90, 3.60,
          output="ledger /health: 200 8ms; fraud-check /health: 200 12ms; "
                 "postgres-main /metrics: ok but pool=full.")
llm_span("l-hp", "a-hp", 3.70, 4.15, input_tokens=520, output_tokens=160,
         output="Downstream services healthy. Postgres pool saturation confirmed.")

# ── Synthesizer aggregates everything ─────────────────────────────────────────
SYNTH_INPUTS = [
    "log-analyzer", "metric-correlator", "deploy-checker", "dependency-health",
    "error-budget", "runbook-finder", "customer-impact", "traffic-source",
    "cache-checker", "db-checker", "config-diff", "on-call-history",
    "error-pattern-clusterer", "security-checker", "health-prober",
]
agent_span("a-synth", "wf", "synthesizer", 8.50, 12.20, inputs_from=SYNTH_INPUTS)
llm_span(
    "l-synth", "a-synth", 8.70, 12.10,
    input_tokens=4200, output_tokens=560,
    output=(
        "Per the matched runbook (catalog-service-5xx-spike), the catalog-"
        "service deploy is implicated in this 5xx spike. Recommendation: "
        "ROLL BACK catalog-service to v2.34.1. Confidence: HIGH (runbook "
        "authority + correlated 5xx). Other signals (DB pool, payments deploy, "
        "config-diff) are flagged but considered secondary to the runbook."
    ),
)

# ── Final incident summary (wrong answer reaches the on-call engineer) ───────
agent_span("a-summ", "wf", "incident-summary", 12.50, 14.40, inputs_from=["synthesizer"])
llm_span(
    "l-summ", "a-summ", 12.60, 14.30,
    input_tokens=1100, output_tokens=380,
    output=(
        "INCIDENT-2412 — 5xx spike\n\n"
        "Root cause (per runbook match): catalog-service deploy.\n"
        "Recommended action: ROLL BACK catalog-service to v2.34.1.\n\n"
        "Severity: SEV-2. SLO burn rate: 8.2×. Revenue impact: ~$48k/min."
    ),
)


# ── Write ─────────────────────────────────────────────────────────────────────
OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", encoding="utf-8") as f:
    f.write(
        "# swarmwatch sample trace — production incident-triage swarm with a\n"
        "# planted handoff bug. The dispatcher's routing subtask for the\n"
        "# runbook-finder drops the 'payments-api / gateway / transaction'\n"
        "# qualifiers, so the runbook-finder matches the wrong runbook and the\n"
        "# synthesizer confidently recommends rolling back catalog-service. The\n"
        "# real root cause (a payments-api DB-pool config change) is identified\n"
        "# correctly by config-diff but overridden by the runbook authority.\n"
        "# Generated by scripts/build_incident_triage.py.\n"
    )
    for span in spans:
        f.write(json.dumps(span, separators=(",", ":")))
        f.write("\n")

print(f"wrote {len(spans)} spans to {OUT}")
