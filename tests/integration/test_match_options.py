"""Integration tests for per-match length (float) + show_timer options."""
import io

import openpyxl
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

SQUAD = [
    {"name": "Gary Keeper", "gk_status": "specialist",     "skill_rating": 3},
    {"name": "Alan Back",   "gk_status": "emergency_only", "skill_rating": 4},
    {"name": "Bob Wing",    "gk_status": "emergency_only", "skill_rating": 3},
    {"name": "Carl Mid",    "gk_status": "emergency_only", "skill_rating": 5},
    {"name": "Dan Fwd",     "gk_status": "emergency_only", "skill_rating": 2},
    {"name": "Ed Sub",      "gk_status": "emergency_only", "skill_rating": 4},
]


def _seed(client: TestClient) -> None:
    for p in SQUAD:
        client.post("/api/squad/players", json=p)


def test_create_match_accepts_fractional_length_and_show_timer(client: TestClient) -> None:
    resp = client.post("/api/matches/", json={
        "date": "2026-03-25", "opponent": "Rovers",
        "quarter_length_mins": 12.5, "show_timer": 0,
    })
    assert resp.status_code == 201
    d = resp.json()
    assert d["quarter_length_mins"] == 12.5  # float round-trips, not truncated
    assert d["show_timer"] == 0


def test_create_match_defaults(client: TestClient) -> None:
    d = client.post("/api/matches/", json={"date": "2026-03-25"}).json()
    assert d["quarter_length_mins"] == 10
    assert d["show_timer"] == 1  # timer shown by default


def test_update_planned_match(client: TestClient) -> None:
    mid = client.post("/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers"}).json()["id"]
    resp = client.put(f"/api/matches/{mid}", json={
        "opponent": "Lions", "quarter_length_mins": 12.5, "show_timer": 0,
    })
    assert resp.status_code == 200
    d = resp.json()
    assert d["opponent"] == "Lions"
    assert d["quarter_length_mins"] == 12.5
    assert d["show_timer"] == 0
    # unspecified fields are preserved
    assert d["team_size"] == 5


def test_update_tournament_match_is_rejected(client: TestClient) -> None:
    _seed(client)
    ids = [p["id"] for p in client.get("/api/squad/players").json()]
    tid = client.post("/api/tournaments/", json={
        "name": "Cup", "date": "2026-04-12", "team_size": 5, "formation": "1-2-1",
        "match_duration_mins": 10, "has_halftime": False,
    }).json()["id"]
    match_id = client.post(
        f"/api/tournaments/{tid}/matches",
        json={"opponent": "Lions", "stage": "group", "available_player_ids": ids},
    ).json()["match"]["id"]
    assert client.put(f"/api/matches/{match_id}", json={"opponent": "X"}).status_code == 400


def test_export_minutes_reflect_period_length(client: TestClient) -> None:
    _seed(client)
    mid = client.post("/api/matches/", json={
        "date": "2026-03-25", "opponent": "Rovers", "quarter_length_mins": 12.5,
    }).json()["id"]
    assert client.post(f"/api/matches/{mid}/rotation").status_code == 200

    resp = client.get("/api/matches/export/season.xlsx")
    assert resp.status_code == 200
    rows = [[c.value for c in row] for row in openpyxl.load_workbook(io.BytesIO(resp.content)).active.iter_rows()]
    data = [r for r in rows if r and r[0] not in ("Player", "TOTAL") and isinstance(r[2], int)]
    played = [r for r in data if r[2] > 0]
    assert played
    for r in played:
        # 12.5-min quarters → one slot = 6.25 min; minutes column rounds the sum.
        assert r[3] == round(r[2] * 6.25)


def test_goals_save_persists_hide_score(client: TestClient) -> None:
    """The FA sub-U12 'hide score' flag round-trips via the goals save + reads."""
    _seed(client)
    mid = client.post("/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers"}).json()["id"]
    assert client.post(f"/api/matches/{mid}/rotation").status_code == 200

    # Defaults off on both the get-match payload and the list read.
    assert client.get(f"/api/matches/{mid}").json()["match"]["hide_score"] == 0
    listed = next(m for m in client.get("/api/matches/").json() if m["id"] == mid)
    assert listed["hide_score"] == 0

    # Saving goals with hide_score=1 sets and persists it.
    r = client.post(f"/api/matches/{mid}/goals", json={"goals": {}, "opponent_goals": 2, "hide_score": 1})
    assert r.status_code == 200
    assert client.get(f"/api/matches/{mid}").json()["match"]["hide_score"] == 1
    listed = next(m for m in client.get("/api/matches/").json() if m["id"] == mid)
    assert listed["hide_score"] == 1

    # Omitting hide_score leaves the stored flag unchanged (None = no-op).
    client.post(f"/api/matches/{mid}/goals", json={"goals": {}, "opponent_goals": 3})
    assert client.get(f"/api/matches/{mid}").json()["match"]["hide_score"] == 1

    # Explicit 0 clears it again.
    client.post(f"/api/matches/{mid}/goals", json={"goals": {}, "opponent_goals": 3, "hide_score": 0})
    assert client.get(f"/api/matches/{mid}").json()["match"]["hide_score"] == 0
