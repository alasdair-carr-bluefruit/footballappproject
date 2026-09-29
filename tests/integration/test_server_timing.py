"""The Server-Timing header reports per-request DB work (diagnosing live slowness)."""
import re

import pytest

pytestmark = pytest.mark.integration


def test_api_responses_carry_db_timing(client, session):
    from backend.db.timing import instrument

    instrument(session.get_bind())  # the test engine isn't the app's module engine
    resp = client.get("/api/squad/players")
    assert resp.status_code == 200
    header = resp.headers["server-timing"]
    queries = int(re.search(r'db;dur=[\d.]+;desc="(\d+) queries"', header).group(1))
    assert queries >= 1
    assert "dbconnect;dur=" in header and "total;dur=" in header


def test_static_files_are_not_instrumented(client):
    assert "server-timing" not in client.get("/sw.js").headers
