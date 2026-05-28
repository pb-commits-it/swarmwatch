"""DuckDB-backed span store.

DuckDB keeps swarmwatch zero-ops (a single file, or in-memory) while still
giving real analytical queries over span trees. Each span is kept both as typed
columns (for aggregation) and as its full JSON payload (for faithful rebuild).
"""

from __future__ import annotations

import duckdb

from swarmwatch.model import Span

_SCHEMA = """
CREATE TABLE IF NOT EXISTS spans (
    trace_id       VARCHAR,
    span_id        VARCHAR PRIMARY KEY,
    parent_span_id VARCHAR,
    name           VARCHAR,
    kind           VARCHAR,
    start_time     TIMESTAMP,
    end_time       TIMESTAMP,
    agent          VARCHAR,
    model          VARCHAR,
    tool           VARCHAR,
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    status         VARCHAR,
    data           JSON
)
"""


class SpanStore:
    def __init__(self, db_path: str = ":memory:") -> None:
        self.con = duckdb.connect(db_path)
        self.con.execute(_SCHEMA)

    def add_span(self, span: Span) -> None:
        self.con.execute(
            "INSERT OR REPLACE INTO spans VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                span.trace_id,
                span.span_id,
                span.parent_span_id,
                span.name,
                span.kind.value,
                span.start_time,
                span.end_time,
                span.agent,
                span.model,
                span.tool,
                span.usage.input_tokens,
                span.usage.output_tokens,
                span.status,
                span.model_dump_json(),
            ],
        )

    def get_spans(self, trace_id: str) -> list[Span]:
        rows = self.con.execute(
            "SELECT data FROM spans WHERE trace_id = ? ORDER BY start_time",
            [trace_id],
        ).fetchall()
        return [Span.model_validate_json(row[0]) for row in rows]

    def all_spans(self) -> list[Span]:
        rows = self.con.execute("SELECT data FROM spans ORDER BY start_time").fetchall()
        return [Span.model_validate_json(row[0]) for row in rows]

    def list_traces(self) -> list[str]:
        rows = self.con.execute("SELECT DISTINCT trace_id FROM spans").fetchall()
        return [row[0] for row in rows]

    def agent_stats(self, trace_id: str) -> list[dict]:
        """Per-agent rollup, computed in DuckDB rather than in Python."""
        rows = self.con.execute(
            """
            SELECT
                agent,
                count(*) FILTER (WHERE kind = 'llm')  AS llm_calls,
                count(*) FILTER (WHERE kind = 'tool') AS tool_calls,
                coalesce(sum(input_tokens), 0)        AS input_tokens,
                coalesce(sum(output_tokens), 0)       AS output_tokens
            FROM spans
            WHERE trace_id = ? AND agent IS NOT NULL
            GROUP BY agent
            ORDER BY min(start_time)
            """,
            [trace_id],
        ).fetchall()
        return [
            {
                "agent": r[0],
                "llm_calls": r[1],
                "tool_calls": r[2],
                "input_tokens": r[3],
                "output_tokens": r[4],
            }
            for r in rows
        ]

    def close(self) -> None:
        self.con.close()
