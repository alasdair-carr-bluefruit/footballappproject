"""Fixtures for the Playwright end-to-end smoke suite.

Launches the real FastAPI app (static frontend + API) in a uvicorn subprocess
against a throwaway file-backed SQLite DB, so a real browser can drive the full
season/tournament flows. Service workers are blocked in every context to avoid
the stale-cache class of false failure (see CLAUDE.md known limitations).
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VENV_PY = REPO_ROOT / ".venv" / "bin" / "python"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    """Start uvicorn against an isolated temp DB; yield the base URL."""
    port = _free_port()
    db_path = tmp_path_factory.mktemp("e2e-db") / "e2e.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    python = str(VENV_PY) if VENV_PY.exists() else sys.executable

    proc = subprocess.Popen(
        [python, "-m", "uvicorn", "main:app", "--port", str(port), "--log-level", "warning"],
        cwd=str(REPO_ROOT),
        env=env,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError("uvicorn exited during startup")
            try:
                if httpx.get(base_url + "/", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.25)
        else:
            raise RuntimeError("uvicorn did not become ready within 30s")
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture
def browser_context_args(browser_context_args):
    """Block service workers so a stale SW cache never masks a real change."""
    return {**browser_context_args, "service_workers": "block"}


# Enough players for a 5v5 (5 on pitch + subs), one specialist keeper. Empty
# preferred_positions means "can play anywhere", so the algorithm always fills.
_SEED_PLAYERS = [
    {"name": "Gary Keeper", "gk_status": "specialist", "skill_rating": 3},
    {"name": "Alan Back", "gk_status": "emergency_only", "skill_rating": 4},
    {"name": "Bob Wing", "gk_status": "emergency_only", "skill_rating": 3},
    {"name": "Carl Mid", "gk_status": "emergency_only", "skill_rating": 5},
    {"name": "Dan Fwd", "gk_status": "emergency_only", "skill_rating": 2},
    {"name": "Ed Sub", "gk_status": "emergency_only", "skill_rating": 4},
    {"name": "Frank Sub", "gk_status": "emergency_only", "skill_rating": 3},
    {"name": "Gus Sub", "gk_status": "emergency_only", "skill_rating": 3},
]


@pytest.fixture(scope="session")
def seeded_squad(live_server):
    """Create a team + squad once via the API so browser tests start with data.

    Also makes initScreen skip the first-launch tutorial (team_name exists) and
    auto-dismiss the squad-building tip (players exist), landing tests straight
    on the mode-select screen.
    """
    httpx.put(live_server + "/api/squad/info",
              json={"team_name": "Testers FC", "team_logo": ""}, timeout=10).raise_for_status()
    for p in _SEED_PLAYERS:
        r = httpx.post(live_server + "/api/squad/players", json=p, timeout=10)
        if r.status_code not in (201, 422):  # 422 = already seeded on a re-run
            r.raise_for_status()
    return live_server
