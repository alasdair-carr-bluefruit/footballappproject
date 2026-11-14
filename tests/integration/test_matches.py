import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

SQUAD_10 = [
    {"name": "Kai",     "gk_status": "specialist",     "def_restricted": False, "skill_rating": 4},
    {"name": "Rowan",   "gk_status": "preferred",      "def_restricted": False, "skill_rating": 3},
    {"name": "Wesley",  "gk_status": "preferred",      "def_restricted": False, "skill_rating": 3},
    {"name": "Kobe",    "gk_status": "can_play",       "def_restricted": True,  "skill_rating": 3},
    {"name": "Jago",    "gk_status": "can_play",       "def_restricted": False, "skill_rating": 3},
    {"name": "Eli",     "gk_status": "can_play",       "def_restricted": False, "skill_rating": 3},
    {"name": "Eden",    "gk_status": "can_play",       "def_restricted": False, "skill_rating": 3},
    {"name": "Jude",    "gk_status": "can_play",       "def_restricted": False, "skill_rating": 3},
    {"name": "Jackson", "gk_status": "can_play",       "def_restricted": False, "skill_rating": 3},
    {"name": "Oscar",   "gk_status": "can_play",       "def_restricted": False, "skill_rating": 3},
]


@pytest.fixture()
def squad_10(client: TestClient) -> None:
    for p in SQUAD_10:
        client.post("/api/squad/players", json=p)


def test_create_match(client: TestClient) -> None:
    resp = client.post("/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers FC"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["opponent"] == "Rovers FC"
    assert data["has_rotation"] is False


def test_list_matches(client: TestClient) -> None:
    client.post("/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers FC"})
    client.post("/api/matches/", json={"date": "2026-04-01", "opponent": "City FC"})
    resp = client.get("/api/matches/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_generate_rotation(client: TestClient, squad_10: None) -> None:
    match_id = client.post(
        "/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers FC"}
    ).json()["id"]

    resp = client.post(f"/api/matches/{match_id}/rotation")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["slots"]) == 8
    slot = data["slots"][0]
    assert set(slot["lineup"].keys()) == {"GK", "CB", "LM", "RM", "CF"}
    assert len(slot["bench"]) == 5  # 10 players - 5 on pitch


def test_generate_rotation_too_few_players(client: TestClient) -> None:
    client.post(
        "/api/squad/players",
        json={"name": "Kai", "gk_status": "specialist", "def_restricted": False, "skill_rating": 4},
    )
    match_id = client.post("/api/matches/", json={"date": "2026-03-25", "opponent": "Test"}).json()["id"]
    assert client.post(f"/api/matches/{match_id}/rotation").status_code == 400


def _slot_counts(slots: list) -> dict:
    counts: dict = {}
    for slot in slots:
        for player in slot["lineup"].values():
            name = player["name"] if isinstance(player, dict) else player
            counts[name] = counts.get(name, 0) + 1
    return counts


@pytest.fixture()
def squad_9_specialist(client: TestClient) -> None:
    """1 specialist keeper + 8 outfield-only players (no backup GK)."""
    client.post("/api/squad/players", json={
        "name": "Keeper", "gk_status": "specialist", "def_restricted": False, "skill_rating": 3,
    })
    for i in range(8):
        client.post("/api/squad/players", json={
            "name": f"Out{i}", "gk_status": "emergency_only", "def_restricted": False, "skill_rating": 3,
        })


def test_share_gk_default_keeps_specialist_time_fair(
    client: TestClient, squad_9_specialist: None,
) -> None:
    """Default (share_gk=1): a specialist keeper in a 9-player squad rotates out
    and does not play markedly more than the outfielders."""
    match_id = client.post(
        "/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers FC"}
    ).json()["id"]
    slots = client.post(f"/api/matches/{match_id}/rotation").json()["slots"]
    counts = _slot_counts(slots)
    others = [v for k, v in counts.items() if k != "Keeper"]
    # Keeper no longer plays double; within one slot of the busiest outfielder.
    assert counts["Keeper"] <= max(others)


def test_share_gk_off_keeps_specialist_in_goal_all_match(
    client: TestClient, squad_9_specialist: None,
) -> None:
    """share_gk=0: a specialist keeper stays in goal every slot (traditional)."""
    created = client.post(
        "/api/matches/",
        json={"date": "2026-03-25", "opponent": "Rovers FC", "share_gk": 0},
    ).json()
    assert created["share_gk"] == 0  # persisted + returned
    match_id = created["id"]
    slots = client.post(f"/api/matches/{match_id}/rotation").json()["slots"]
    counts = _slot_counts(slots)
    assert counts["Keeper"] == len(slots)  # in goal for every slot


def test_rotation_persists(client: TestClient, squad_10: None) -> None:
    match_id = client.post(
        "/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers FC"}
    ).json()["id"]

    client.post(f"/api/matches/{match_id}/rotation")

    data = client.get(f"/api/matches/{match_id}").json()
    assert data["slots"] is not None
    assert len(data["slots"]) == 8


def test_regenerate_rotation(client: TestClient, squad_10: None) -> None:
    match_id = client.post(
        "/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers FC"}
    ).json()["id"]

    client.post(f"/api/matches/{match_id}/rotation")
    resp2 = client.post(f"/api/matches/{match_id}/rotation")
    assert resp2.status_code == 200  # idempotent — overwrites existing


def test_delete_match(client: TestClient) -> None:
    match_id = client.post(
        "/api/matches/", json={"date": "2026-03-25", "opponent": "Test"}
    ).json()["id"]

    assert client.delete(f"/api/matches/{match_id}").status_code == 204
    assert client.get(f"/api/matches/{match_id}").status_code == 404


def test_match_not_found(client: TestClient) -> None:
    assert client.get("/api/matches/999").status_code == 404
    assert client.post("/api/matches/999/rotation").status_code == 404


# ── Start Match tests ──────────────────────────────────────────────────────────

def test_start_match(client: TestClient, squad_10: None) -> None:
    match_id = client.post("/api/matches/", json={"date": "2026-03-25"}).json()["id"]
    client.post(f"/api/matches/{match_id}/rotation")

    # Initial status is planned
    data = client.get(f"/api/matches/{match_id}").json()
    assert data["match"]["status"] == "planned"

    # Start the match
    resp = client.post(f"/api/matches/{match_id}/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"
    assert resp.json()["current_slot"] == 0

    # Status persists
    data = client.get(f"/api/matches/{match_id}").json()
    assert data["match"]["status"] == "in_progress"


def test_start_match_idempotent(client: TestClient, squad_10: None) -> None:
    match_id = client.post("/api/matches/", json={"date": "2026-03-25"}).json()["id"]
    client.post(f"/api/matches/{match_id}/rotation")
    client.post(f"/api/matches/{match_id}/start")
    resp = client.post(f"/api/matches/{match_id}/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


def test_update_progress(client: TestClient, squad_10: None) -> None:
    match_id = client.post("/api/matches/", json={"date": "2026-03-25"}).json()["id"]
    client.post(f"/api/matches/{match_id}/rotation")
    client.post(f"/api/matches/{match_id}/start")

    resp = client.post(f"/api/matches/{match_id}/progress", json={"current_slot": 3})
    assert resp.status_code == 200
    assert resp.json()["current_slot"] == 3

    # Mark completed
    resp = client.post(f"/api/matches/{match_id}/progress", json={"current_slot": 7, "status": "completed"})
    assert resp.json()["status"] == "completed"


# ── Remove / reinstate player tests ───────────────────────────────────────────

def test_remove_player_from_match(client: TestClient, squad_10: None) -> None:
    match_id = client.post("/api/matches/", json={"date": "2026-03-25"}).json()["id"]
    rotation_data = client.post(f"/api/matches/{match_id}/rotation").json()

    # Pick a bench player to remove
    bench_player = rotation_data["slots"][2]["bench"][0]
    player_id = bench_player["id"]

    resp = client.post(
        f"/api/matches/{match_id}/remove-player",
        json={"player_id": player_id, "from_slot": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert str(player_id) in data["removed_players"]
    assert data["removed_players"][str(player_id)] == 2
    # Removed player should not appear in any slot from index 2 onward
    for slot in data["slots"][2:]:
        lineup_ids = list(slot["lineup"].values())
        assert player_id not in [p["id"] if isinstance(p, dict) else p for p in lineup_ids]


def test_reinstate_player(client: TestClient, squad_10: None) -> None:
    match_id = client.post("/api/matches/", json={"date": "2026-03-25"}).json()["id"]
    rotation_data = client.post(f"/api/matches/{match_id}/rotation").json()
    client.post(f"/api/matches/{match_id}/start")
    client.post(f"/api/matches/{match_id}/progress", json={"current_slot": 2})

    bench_player = rotation_data["slots"][2]["bench"][0]
    player_id = bench_player["id"]

    # Remove then reinstate
    client.post(
        f"/api/matches/{match_id}/remove-player",
        json={"player_id": player_id, "from_slot": 3},
    )
    resp = client.post(
        f"/api/matches/{match_id}/reinstate-player",
        json={"player_id": player_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert str(player_id) not in data["removed_players"]


def test_match_includes_removed_players_on_load(client: TestClient, squad_10: None) -> None:
    """removed_players map is included when loading a match."""
    match_id = client.post("/api/matches/", json={"date": "2026-03-25"}).json()["id"]
    rotation_data = client.post(f"/api/matches/{match_id}/rotation").json()
    bench_player = rotation_data["slots"][0]["bench"][0]
    client.post(
        f"/api/matches/{match_id}/remove-player",
        json={"player_id": bench_player["id"], "from_slot": 0},
    )
    data = client.get(f"/api/matches/{match_id}").json()
    assert "removed_players" in data
    assert str(bench_player["id"]) in data["removed_players"]


def test_remove_player_slots_regenerated(client: TestClient, squad_10: None) -> None:
    """Slots from from_slot onward don't include the removed player."""
    match_id = client.post("/api/matches/", json={"date": "2026-03-25"}).json()["id"]
    rotation_data = client.post(f"/api/matches/{match_id}/rotation").json()
    bench_player = rotation_data["slots"][4]["bench"][0]
    player_id = bench_player["id"]

    resp = client.post(
        f"/api/matches/{match_id}/remove-player",
        json={"player_id": player_id, "from_slot": 4},
    )
    data = resp.json()
    # Player must not appear in any slot from index 4 onward
    for slot in data["slots"][4:]:
        all_ids_in_slot = (
            [p["id"] for p in slot["lineup"].values()]
            + [p["id"] for p in slot["bench"]]
        )
        assert player_id not in all_ids_in_slot

    # Locked slots 0-3 keep their original lineups intact
    # (bench is dynamically computed, so removed player may not appear there;
    #  the BDD test covers locked-slot lineup preservation at algorithm level)


def test_start_match_not_found(client: TestClient) -> None:
    assert client.post("/api/matches/999/start").status_code == 404


def test_progress_not_found(client: TestClient) -> None:
    assert client.post("/api/matches/999/progress", json={"current_slot": 0}).status_code == 404


def test_remove_player_no_rotation(client: TestClient) -> None:
    match_id = client.post("/api/matches/", json={"date": "2026-03-25"}).json()["id"]
    resp = client.post(
        f"/api/matches/{match_id}/remove-player",
        json={"player_id": 1, "from_slot": 0},
    )
    assert resp.status_code == 400


# ── Player history tests ───────────────────────────────────────────────────────

def test_player_history_no_matches(client: TestClient, squad_10: None) -> None:
    players = client.get("/api/squad/players").json()
    player_id = players[0]["id"]
    resp = client.get(f"/api/matches/stats/player/{player_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["player"]["id"] == player_id
    assert data["matches"] == []
    assert data["totals"]["matches_available"] == 0
    assert data["totals"]["slots_played"] == 0
    assert data["totals"]["goals"] == 0


def test_player_history_with_data(client: TestClient, squad_10: None) -> None:
    match_id = client.post("/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers"}).json()["id"]
    client.post(f"/api/matches/{match_id}/rotation")

    # Find a player who appears in lineup of slot 0
    data = client.get(f"/api/matches/{match_id}").json()
    first_lineup = data["slots"][0]["lineup"]
    on_pitch_player = list(first_lineup.values())[0]
    player_id = on_pitch_player["id"]

    resp = client.get(f"/api/matches/stats/player/{player_id}")
    assert resp.status_code == 200
    history = resp.json()
    assert history["player"]["id"] == player_id
    assert len(history["matches"]) == 1
    assert history["matches"][0]["opponent"] == "Rovers"
    assert history["matches"][0]["slots_played"] > 0
    assert history["totals"]["slots_played"] > 0


def test_player_history_not_found(client: TestClient) -> None:
    assert client.get("/api/matches/stats/player/999").status_code == 404


def test_player_history_goals_counted(client: TestClient, squad_10: None) -> None:
    match_id = client.post("/api/matches/", json={"date": "2026-03-25"}).json()["id"]
    client.post(f"/api/matches/{match_id}/rotation")

    players = client.get("/api/squad/players").json()
    player = players[0]

    client.post(f"/api/matches/{match_id}/goals", json={"goals": {player["name"]: 2}, "opponent_goals": 1})

    resp = client.get(f"/api/matches/stats/player/{player['id']}")
    data = resp.json()
    # Goals should be reflected in totals even if player wasn't in lineup
    total_goals = data["totals"]["goals"]
    assert total_goals == 2


def test_own_goals_count_for_us(client: TestClient, squad_10: None) -> None:
    """Opposition own goals add to our team total (no named scorer)."""
    match_id = client.post("/api/matches/", json={"date": "2026-03-25", "opponent": "City"}).json()["id"]
    client.post(f"/api/matches/{match_id}/rotation")
    players = client.get("/api/squad/players").json()

    # 1 scored by a player + 2 opposition own goals = 3 for us
    client.post(
        f"/api/matches/{match_id}/goals",
        json={"goals": {players[0]["name"]: 1}, "opponent_goals": 2, "own_goals": 2},
    )

    # get_match exposes own_goals on the match for the Full Time card / live state
    data = client.get(f"/api/matches/{match_id}").json()
    assert data["match"]["own_goals"] == 2
    assert data["match"]["opponent_goals"] == 2

    # Match list folds own goals into the team total for the scoreline badge
    m = next(x for x in client.get("/api/matches/").json() if x["id"] == match_id)
    assert m["our_goals"] == 3  # 1 player goal + 2 own goals
    assert m["own_goals"] == 2
    assert m["opponent_goals"] == 2

    # Own goals don't attribute to any player's stats
    hist = client.get(f"/api/matches/stats/player/{players[0]['id']}").json()
    assert hist["totals"]["goals"] == 1


def test_whole_slot_swap_via_adjust(client: TestClient, squad_10: None) -> None:
    """Swapping two whole slots (Q1a ⇄ Q1b) swaps every player and touches nothing else."""
    match_id = client.post("/api/matches/", json={"date": "2026-03-25"}).json()["id"]
    rotation = client.post(f"/api/matches/{match_id}/rotation").json()
    slots = rotation["slots"]

    q1a = {pos: p["id"] for pos, p in slots[0]["lineup"].items()}
    q1b = {pos: p["id"] for pos, p in slots[1]["lineup"].items()}

    # Each slot takes on the other's entire lineup; lock every slot so the engine
    # applies the swap verbatim and regenerates nothing.
    edits = {0: q1b, 1: q1a}
    locked = [s["slot_index"] for s in slots]
    resp = client.post(f"/api/matches/{match_id}/adjust", json={"edits": edits, "locked_slots": locked})
    assert resp.status_code == 200
    new_slots = resp.json()["slots"]

    # The two slots are swapped by position → player id
    assert {pos: p["id"] for pos, p in new_slots[0]["lineup"].items()} == q1b
    assert {pos: p["id"] for pos, p in new_slots[1]["lineup"].items()} == q1a

    # Every other slot is untouched
    for i in range(2, len(slots)):
        before = {pos: p["id"] for pos, p in slots[i]["lineup"].items()}
        after = {pos: p["id"] for pos, p in new_slots[i]["lineup"].items()}
        assert before == after

    # Swap persists across a reload
    reloaded = client.get(f"/api/matches/{match_id}").json()["slots"]
    assert {pos: p["id"] for pos, p in reloaded[0]["lineup"].items()} == q1b
    assert {pos: p["id"] for pos, p in reloaded[1]["lineup"].items()} == q1a


# ── Full match lifecycle integration test ────────────────────────────────────

def test_match_list_shows_status_and_score(client: TestClient, squad_10: None) -> None:
    """Match list includes status and our_goals for display."""
    match_id = client.post("/api/matches/", json={"date": "2026-03-25", "opponent": "City"}).json()["id"]
    client.post(f"/api/matches/{match_id}/rotation")

    # Planned — default status
    matches = client.get("/api/matches/").json()
    m = next(x for x in matches if x["id"] == match_id)
    assert m["status"] == "planned"
    assert m["our_goals"] == 0

    # Start and record a goal
    client.post(f"/api/matches/{match_id}/start")
    players = client.get("/api/squad/players").json()
    client.post(f"/api/matches/{match_id}/goals", json={"goals": {players[0]["name"]: 2}, "opponent_goals": 1})
    client.post(f"/api/matches/{match_id}/progress", json={"current_slot": 7, "status": "completed"})

    matches = client.get("/api/matches/").json()
    m = next(x for x in matches if x["id"] == match_id)
    assert m["status"] == "completed"
    assert m["our_goals"] == 2
    assert m["opponent_goals"] == 1


def test_full_match_lifecycle(client: TestClient, squad_10: None) -> None:
    """End-to-end: create → rotate → start → advance slots → goals → complete."""
    # Create and generate rotation
    match_id = client.post("/api/matches/", json={"date": "2026-03-25", "opponent": "City FC"}).json()["id"]
    rotation = client.post(f"/api/matches/{match_id}/rotation").json()
    assert len(rotation["slots"]) == 8

    # Initially planned
    assert rotation["match"]["status"] == "planned"
    assert rotation["match"]["current_slot"] == 0

    # Start match
    client.post(f"/api/matches/{match_id}/start")
    data = client.get(f"/api/matches/{match_id}").json()
    assert data["match"]["status"] == "in_progress"

    # Advance through slots
    for slot_i in range(1, 8):
        resp = client.post(f"/api/matches/{match_id}/progress", json={"current_slot": slot_i})
        assert resp.json()["current_slot"] == slot_i

    # Record goals
    on_pitch = list(rotation["slots"][0]["lineup"].values())
    scorer = on_pitch[1]["name"]
    client.post(f"/api/matches/{match_id}/goals", json={"goals": {scorer: 1}, "opponent_goals": 0})

    # Mark completed
    resp = client.post(f"/api/matches/{match_id}/progress", json={"current_slot": 7, "status": "completed"})
    assert resp.json()["status"] == "completed"

    # Season stats reflect the completed match
    stats = client.get("/api/matches/stats/season").json()
    scorer_stats = next(s for s in stats if s["name"] == scorer)
    assert scorer_stats["goals"] == 1
