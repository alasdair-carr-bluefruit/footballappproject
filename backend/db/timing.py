"""Per-request database timing, surfaced as a `Server-Timing` response header.

Answers "why is this request slow?" on the live stack without guessing: how long
was spent opening new DB connections, how many queries ran and how long they took,
and the total. Visible in browser devtools (Network → Timing) and via `curl -I`.

The middleware in main.py opens a per-request stats dict in a ContextVar; the
SQLAlchemy engine events below add to it. Sync route handlers run in a threadpool
that copies the context, so they update the same dict.
"""
from __future__ import annotations

import time
from contextvars import ContextVar

from sqlalchemy import event
from sqlalchemy.engine import Engine

_stats: ContextVar[dict | None] = ContextVar("db_timing_stats", default=None)


def start_request() -> dict:
    stats = {"queries": 0, "query_ms": 0.0, "connects": 0, "connect_ms": 0.0}
    _stats.set(stats)
    return stats


def server_timing_header(stats: dict, total_ms: float) -> str:
    return (
        f'db;dur={stats["query_ms"]:.1f};desc="{stats["queries"]} queries", '
        f'dbconnect;dur={stats["connect_ms"]:.1f};desc="{stats["connects"]} new connections", '
        f"total;dur={total_ms:.1f}"
    )


def instrument(engine: Engine) -> None:
    @event.listens_for(engine, "do_connect")
    def _before_connect(dialect, conn_rec, cargs, cparams):  # noqa: ARG001
        conn_rec.info["_t_connect"] = time.perf_counter()

    @event.listens_for(engine, "connect")
    def _after_connect(dbapi_conn, conn_rec):  # noqa: ARG001
        stats = _stats.get()
        started = conn_rec.info.pop("_t_connect", None)
        if stats is not None and started is not None:
            stats["connects"] += 1
            stats["connect_ms"] += (time.perf_counter() - started) * 1000

    @event.listens_for(engine, "before_cursor_execute")
    def _before_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        conn.info.setdefault("_t_query", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _after_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        started = conn.info["_t_query"].pop()
        stats = _stats.get()
        if stats is not None:
            stats["queries"] += 1
            stats["query_ms"] += (time.perf_counter() - started) * 1000
