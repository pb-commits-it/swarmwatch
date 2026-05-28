"""A minimal worked example: instrument a planner→worker→judge swarm with
the swarmwatch SDK and watch it land in the live UI.

Usage:
    # in one terminal
    pip install -e '.[sdk]'   # or: pip install 'swarmwatch[sdk]'
    swarmwatch up

    # in another terminal, with the same env
    python examples/from_scratch_loop.py

    # open the UI in live mode
    open 'http://127.0.0.1:8000/?mode=live'

This is the same planner→worker→judge scenario as the bundled sample trace,
but generated live so you can watch the swarm light up in real time. The
planner deliberately drops "time-series" when handing off to worker-1; the
Handoff Inspector will surface the dropped context.
"""

from __future__ import annotations

import time

from swarmwatch.sdk import SwarmWatch

USER_REQUEST = (
    "Recommend a database for our platform. We ingest ~2 million IoT sensor "
    "readings per minute and need fast time-range queries over months of telemetry."
)


def main() -> None:
    sw = SwarmWatch()  # POSTs to http://127.0.0.1:8000/v1/traces by default

    with sw.workflow("research-swarm", input=USER_REQUEST, conversation_id="conv-001"):
        # PLANNER — note the planted bug: subtask 1 drops "time-series".
        with sw.agent("planner", inputs_from=[], input=USER_REQUEST, conversation_id="conv-001"):
            with sw.chat(
                "grok-4.20-beta",
                provider="xai",
                input=USER_REQUEST,
                output=(
                    "Plan: (1) worker-1 -> Find the best general-purpose database "
                    "for storing our application data. (2) worker-2 -> Estimate "
                    "ingestion throughput and data-retention requirements."
                ),
                input_tokens=850,
                output_tokens=280,
            ):
                time.sleep(0.6)

        # WORKER-1 — receives the degraded subtask.
        with sw.agent(
            "worker-1",
            inputs_from=["planner"],
            input="Find the best general-purpose database for storing our application data.",
            conversation_id="conv-001",
        ):
            with sw.tool(
                "web_search",
                output="Top general-purpose databases: PostgreSQL, MySQL, MongoDB.",
            ):
                time.sleep(0.35)
            with sw.tool(
                "fetch_docs",
                output="PostgreSQL docs: ACID, rich SQL, broad ecosystem.",
            ):
                time.sleep(0.35)
            with sw.chat(
                "grok-4.20-beta",
                provider="xai",
                output=(
                    "Recommendation: PostgreSQL. A robust general-purpose relational "
                    "database with strong ecosystem support."
                ),
                input_tokens=1400,
                output_tokens=420,
            ):
                time.sleep(0.7)

        # WORKER-2 — gets the throughput subtask intact.
        with sw.agent(
            "worker-2",
            inputs_from=["planner"],
            input="Estimate ingestion throughput and data-retention requirements.",
            conversation_id="conv-001",
        ):
            with sw.tool(
                "web_search",
                output="Sustained 2M writes/min implies time-partitioned, write-optimized storage.",
            ):
                time.sleep(0.35)
            with sw.chat(
                "grok-4.20-beta",
                provider="xai",
                output=(
                    "~2M writes/min sustained; 6-12 months retention into tens of TB. "
                    "Needs high write throughput and time-partitioned storage."
                ),
                input_tokens=1100,
                output_tokens=360,
            ):
                time.sleep(0.6)

        # JUDGE — picks PostgreSQL, propagating the upstream context loss.
        with sw.agent("judge", inputs_from=["worker-1", "worker-2"], conversation_id="conv-001"):
            with sw.chat(
                "grok-4.20-beta",
                provider="xai",
                input="worker-1: PostgreSQL. worker-2: 2M writes/min, time-partitioned storage.",
                output="Selected: PostgreSQL. Meets general storage needs with mature tooling.",
                input_tokens=1900,
                output_tokens=520,
            ):
                time.sleep(0.8)

    sw.shutdown()
    print("done — open http://127.0.0.1:8000/?mode=live")


if __name__ == "__main__":
    main()
