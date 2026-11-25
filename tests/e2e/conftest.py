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


def _wait_until_ready(proc: subprocess.Popen, base_url: str) -> None:
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("uvicorn exited during startup")
        try:
            if httpx.get(base_url + "/", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.25)
    raise RuntimeError("uvicorn did not become ready within 30s")


@pytest.fixture(scope="session")
def auth_server(tmp_path_factory):
    """Start uvicorn with multi-user AUTH ENABLED (own temp DB); yield the base URL.

    COOKIE_SECURE=false so the session cookie rides the http test server. ADMIN_KEY
    lets the test mint invites via the API. This exercises the real auth gate that
    the default (auth-off) suite deliberately skips.
    """
    port = _free_port()
    db_path = tmp_path_factory.mktemp("e2e-auth-db") / "e2e.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_path}",
        "AUTH_ENABLED": "true",
        "SECRET_KEY": "e2e-secret",
        "ADMIN_KEY": "e2e-admin",
        "COOKIE_SECURE": "false",
    }
    python = str(VENV_PY) if VENV_PY.exists() else sys.executable
    proc = subprocess.Popen(
        [python, "-m", "uvicorn", "main:app", "--port", str(port), "--log-level", "warning"],
        cwd=str(REPO_ROOT),
        env=env,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_until_ready(proc, base_url)
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _whats_new_seen_script() -> str:
    """Init script marking the current "What's new" and every walkthrough intro
    (welcome tour, assistant welcome, first-use intros) as seen. The version and
    intro ids are read from the modules, so adding one never silently blocks the
    suite behind a carousel."""
    import re
    src = (REPO_ROOT / "frontend" / "whats-new.js").read_text()
    version = re.search(r'WHATS_NEW_VERSION = "([^"]+)"', src).group(1)
    return (
        "try { localStorage.setItem('gaffer_whats_new', "
        f"JSON.stringify({{v: '{version}', status: 'done'}})); }} catch (_) {{}}\n"
        + _intros_seen_script()
    )


def _intro_ids() -> list[str]:
    import re
    src = (REPO_ROOT / "frontend" / "intros.js").read_text()
    line = re.search(r"export const INTRO_IDS = \[([^\]]*)\]", src).group(1)
    return re.findall(r'"([^"]+)"', line)


INTRO_IDS = _intro_ids()


def _intros_seen_script() -> str:
    import json
    seen = json.dumps({i: "2026-01-01" for i in INTRO_IDS})
    return f"try {{ localStorage.setItem('gaffer_intros', '{seen}'); }} catch (_) {{}}"


# Pre-dismisses What's new AND every intro (add it to any extra browser context).
WHATS_NEW_SEEN = _whats_new_seen_script()


@pytest.fixture(autouse=True)
def _whats_new_already_seen(request):
    """Returning coaches get the What's new carousel on boot, and new ones the
    walkthrough intros; keep them out of every browser test except those marked
    `show_whats_new` / `show_intros` (which opt out of their own pre-dismiss)."""
    if "page" not in request.fixturenames:
        return
    page = request.getfixturevalue("page")
    if request.node.get_closest_marker("show_intros"):
        if not request.node.get_closest_marker("show_whats_new"):
            page.add_init_script(WHATS_NEW_SEEN.split("\n")[0])
    elif not request.node.get_closest_marker("show_whats_new"):
        page.add_init_script(WHATS_NEW_SEEN)
    else:
        page.add_init_script(_intros_seen_script())


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


@pytest.fixture(autouse=True)
def _fresh_plans(request):
    """Start each seeded-squad test with no matches or tournaments.

    New Match / New Tournament pre-fill from the team's latest plan (remembered
    settings), so on the shared session server one test's choices (timer off,
    7v7, ...) would otherwise leak into the next test's defaults.
    """
    if "seeded_squad" in request.fixturenames:
        base = request.getfixturevalue("seeded_squad")
        with httpx.Client(base_url=base, timeout=10) as api:
            for m in api.get("/api/matches/").json():
                api.delete(f"/api/matches/{m['id']}")
            for t in api.get("/api/tournaments/").json():
                api.delete(f"/api/tournaments/{t['id']}")
    yield
