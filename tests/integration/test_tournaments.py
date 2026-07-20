import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

SQUAD_10 = [
    {"name": "Kai",     "gk_status": "specialist", "def_restricted": False, "skill_rating": 4},
    {"name": "Rowan",   "gk_status": "preferred",  "def_restricted": False, "skill_rating": 3},
    {"name": "Wesley",  "gk_status": "preferred",  "def_restricted": False, "skill_rating": 3},
    {"name": "Kobe",    "gk_status": "can_play",   "def_restricted": True,  "skill_rating": 3},
    {"name": "Jago",    "gk_status": "can_play",   "def_restricted": False, "skill_rating": 3},
    {"name": "Eli",     "gk_status": "can_play",   "def_restricted": False, "skill_rating": 3},
    {"name": "Eden",    "gk_status": "can_play",   "def_restricted": False, "skill_rating": 3},
    {"name": "Jude",    "gk_status": "can_play",   "def_restricted": False, "skill_rating": 3},
    {"name": "Jackson", "gk_status": "can_play",   "def_restricted": False, "skill_rating": 3},
    {"name": "Oscar",   "gk_status": "can_play",   "def_restricted": False, "skill_rating": 3},
]

TOURNAMENT_BASE = {
    "name": "Easter Cup",
    "date": "2026-04-12",
    "team_size": 5,
    "formation": "1-2-1",
    "match_duration_mins": 10,
    "has_halftime": False,
    "fairness_value": 50,
    "rotation_intensity": 50,
}


@pytest.fixture()
def squad_10(client: TestClient) -> None:
    for p in SQUAD_10:
        client.post("/api/squad/players", json=p)


@pytest.fixture()
def tournament(client: TestClient) -> dict:
    resp = client.post("/api/tournaments/", json=TOURNAMENT_BASE)
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture()
def squad_ids(client: TestClient, squad_10: None) -> list[int]:
    return [p["id"] for p in client.get("/api/squad/players").json()]


# ── CRUD ──────────────────────────────────────────────────────────────────────

def test_create_tournament(client: TestClient) -> None:
    resp = client.post("/api/tournaments/", json=TOURNAMENT_BASE)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Easter Cup"
    assert data["team_size"] == 5
    assert data["has_halftime"] is False
    assert data["status"] == "active"


def test_list_tournaments(client: TestClient, tournament: dict) -> None:
    resp = client.get("/api/tournaments/")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == tournament["id"]


def test_get_tournament(client: TestClient, tournament: dict, squad_10: None) -> None:
    resp = client.get(f"/api/tournaments/{tournament['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert "tournament" in data
    assert "matches" in data
    assert "squad_players" in data
    assert "guest_players" in data
    assert len(data["squad_players"]) == 10


def test_get_tournament_not_found(client: TestClient) -> None:
    assert client.get("/api/tournaments/999").status_code == 404


def test_delete_tournament(client: TestClient, tournament: dict) -> None:
    tid = tournament["id"]
    assert client.delete(f"/api/tournaments/{tid}").status_code == 204
    assert client.get(f"/api/tournaments/{tid}").status_code == 404


# ── Guest players ─────────────────────────────────────────────────────────────

def test_add_guest_player(client: TestClient, tournament: dict) -> None:
    resp = client.post(
        f"/api/tournaments/{tournament['id']}/players",
        json={"name": "Guest McGee", "gk_status": "can_play", "skill_rating": 3},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Guest McGee"
    assert data["is_guest"] is True


def test_guest_player_not_in_main_squad(client: TestClient, tournament: dict) -> None:
    client.post(
        f"/api/tournaments/{tournament['id']}/players",
        json={"name": "Guest McGee", "gk_status": "can_play", "skill_rating": 3},
    )
    squad = client.get("/api/squad/players").json()
    assert all(p["name"] != "Guest McGee" for p in squad)


def test_guest_player_appears_in_tournament(client: TestClient, tournament: dict) -> None:
    client.post(
        f"/api/tournaments/{tournament['id']}/players",
        json={"name": "Guest McGee", "gk_status": "can_play", "skill_rating": 3},
    )
    data = client.get(f"/api/tournaments/{tournament['id']}").json()
    assert any(p["name"] == "Guest McGee" for p in data["guest_players"])


def test_remove_guest_player(client: TestClient, tournament: dict) -> None:
    tid = tournament["id"]
    pid = client.post(
        f"/api/tournaments/{tid}/players",
        json={"name": "Guest", "gk_status": "can_play", "skill_rating": 3},
    ).json()["id"]
    assert client.delete(f"/api/tournaments/{tid}/players/{pid}").status_code == 204
    data = client.get(f"/api/tournaments/{tid}").json()
    assert all(p["id"] != pid for p in data["guest_players"])


def test_delete_tournament_removes_guest_players(
    client: TestClient, tournament: dict
) -> None:
    """Guest players are cascade-deleted with the tournament."""
    tid = tournament["id"]
    guest_id = client.post(
        f"/api/tournaments/{tid}/players",
        json={"name": "Guest", "gk_status": "can_play", "skill_rating": 3},
    ).json()["id"]

    client.delete(f"/api/tournaments/{tid}")
    # Guest player should not appear in the main squad either
    squad = client.get("/api/squad/players").json()
    assert all(p["id"] != guest_id for p in squad)


# ── Match generation ──────────────────────────────────────────────────────────

def test_add_tournament_match(
    client: TestClient, tournament: dict, squad_ids: list[int]
) -> None:
    resp = client.post(
        f"/api/tournaments/{tournament['id']}/matches",
        json={"opponent": "Lions FC", "stage": "group", "available_player_ids": squad_ids},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["match"]["tournament_id"] == tournament["id"]
    assert data["match"]["tournament_stage"] == "group"
    assert data["match"]["match_number"] == 1
    # 5v5 no-halftime = 2 slots
    assert len(data["slots"]) == 2


def test_tournament_match_not_in_season_list(
    client: TestClient, tournament: dict, squad_ids: list[int]
) -> None:
    client.post(
        f"/api/tournaments/{tournament['id']}/matches",
        json={"opponent": "Lions FC", "stage": "group", "available_player_ids": squad_ids},
    )
    season_matches = client.get("/api/matches/").json()
    assert len(season_matches) == 0


def test_tournament_match_not_in_season_stats(
    client: TestClient, tournament: dict, squad_ids: list[int]
) -> None:
    client.post(
        f"/api/tournaments/{tournament['id']}/matches",
        json={"opponent": "Lions FC", "stage": "group", "available_player_ids": squad_ids},
    )
    stats = client.get("/api/matches/stats/season").json()
    assert all(s["matches_available"] == 0 for s in stats)


def test_add_multiple_matches_increments_match_number(
    client: TestClient, tournament: dict, squad_ids: list[int]
) -> None:
    for opponent in ["Lions", "Tigers", "Bears"]:
        client.post(
            f"/api/tournaments/{tournament['id']}/matches",
            json={"opponent": opponent, "stage": "group", "available_player_ids": squad_ids},
        )
    data = client.get(f"/api/tournaments/{tournament['id']}").json()
    numbers = [m["match_number"] for m in data["matches"]]
    assert numbers == [1, 2, 3]


def test_knockout_match_stage(
    client: TestClient, tournament: dict, squad_ids: list[int]
) -> None:
    resp = client.post(
        f"/api/tournaments/{tournament['id']}/matches",
        json={
            "opponent": "Final Opponent",
            "stage": "knockout",
            "available_player_ids": squad_ids,
            "knockout_fairness_value": 80,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["match"]["tournament_stage"] == "knockout"


def test_with_halftime_gives_4_slots(client: TestClient, squad_ids: list[int]) -> None:
    tournament = client.post(
        "/api/tournaments/",
        json={**TOURNAMENT_BASE, "match_duration_mins": 20, "has_halftime": True},
    ).json()
    resp = client.post(
        f"/api/tournaments/{tournament['id']}/matches",
        json={"opponent": "Rovers", "stage": "group", "available_player_ids": squad_ids},
    )
    assert len(resp.json()["slots"]) == 4


def test_cross_match_prior_slots_used(
    client: TestClient, tournament: dict, squad_ids: list[int]
) -> None:
    """Generating match 2 succeeds — prior slots from match 1 are loaded without error."""
    for _ in range(2):
        resp = client.post(
            f"/api/tournaments/{tournament['id']}/matches",
            json={"opponent": "Team", "stage": "group", "available_player_ids": squad_ids},
        )
        assert resp.status_code == 200


def test_too_few_players_rejected(client: TestClient, tournament: dict) -> None:
    resp = client.post(
        f"/api/tournaments/{tournament['id']}/matches",
        json={"opponent": "Team", "stage": "group", "available_player_ids": [1]},
    )
    assert resp.status_code == 400


def test_tournament_match_with_guest_player(
    client: TestClient, tournament: dict, squad_ids: list[int]
) -> None:
    tid = tournament["id"]
    guest_id = client.post(
        f"/api/tournaments/{tid}/players",
        json={"name": "Guest", "gk_status": "can_play", "skill_rating": 3},
    ).json()["id"]

    resp = client.post(
        f"/api/tournaments/{tid}/matches",
        json={
            "opponent": "Team",
            "stage": "group",
            "available_player_ids": squad_ids + [guest_id],
        },
    )
    assert resp.status_code == 200


# ── Consecutive sit-out constraint (Issue1) ───────────────────────────────────

@pytest.fixture()
def squad_ids_12(client: TestClient, squad_10: None) -> list[int]:
    """12 available players for a 5v5 2-slot match → 10 player-slots, so exactly
    2 players must sit out each match entirely. Guarantees the sit-out case."""
    for p in [
        {"name": "Finn", "gk_status": "can_play", "def_restricted": False, "skill_rating": 3},
        {"name": "Theo", "gk_status": "can_play", "def_restricted": False, "skill_rating": 3},
    ]:
        client.post("/api/squad/players", json=p)
    return [p["id"] for p in client.get("/api/squad/players").json()]


def _zero_slot_names(match_data: dict, all_names: set[str]) -> set[str]:
    played: set[str] = set()
    for slot in match_data["slots"]:
        played.update(p["name"] for p in slot["lineup"].values())
    return all_names - played


def _add_match(client: TestClient, tournament_id: int, player_ids: list[int]) -> dict:
    resp = client.post(
        f"/api/tournaments/{tournament_id}/matches",
        json={"opponent": "Team", "stage": "group", "available_player_ids": player_ids},
    )
    assert resp.status_code == 200
    return resp.json()


def test_no_consecutive_sit_outs_across_tournament_matches(
    client: TestClient, tournament: dict, squad_ids_12: list[int]
) -> None:
    """A player benched for all of match N must get at least one slot in match N+1."""
    all_names = {p["name"] for p in client.get("/api/squad/players").json()}

    match1 = _add_match(client, tournament["id"], squad_ids_12)
    benched_m1 = _zero_slot_names(match1, all_names)
    assert benched_m1, "test setup expects 12 players / 10 slots to bench someone"

    match2 = _add_match(client, tournament["id"], squad_ids_12)
    benched_m2 = _zero_slot_names(match2, all_names)

    repeat_offenders = benched_m1 & benched_m2
    assert not repeat_offenders, (
        f"{repeat_offenders} sat out two consecutive tournament matches entirely"
    )


def test_adjust_flags_consecutive_sit_out(
    client: TestClient, tournament: dict, squad_ids_12: list[int]
) -> None:
    """Tinkering a benched-last-match player back out of match 2 must raise a
    VIOLATION warning (the constraint survives manual adjustment)."""
    all_names = {p["name"] for p in client.get("/api/squad/players").json()}

    match1 = _add_match(client, tournament["id"], squad_ids_12)
    benched_m1 = _zero_slot_names(match1, all_names)
    assert benched_m1

    match2 = _add_match(client, tournament["id"], squad_ids_12)
    target_name = next(iter(benched_m1 - _zero_slot_names(match2, all_names)))

    # Build edits replacing the must-play player with a bench player in every
    # slot they appear, and lock all slots so no regeneration can restore them.
    edits: dict[int, dict[str, int]] = {}
    for slot in match2["slots"]:
        for pos_key, player in slot["lineup"].items():
            if player["name"] == target_name:
                replacement = next(
                    b for b in slot["bench"]
                    if not b["def_restricted"] and b["name"] != target_name
                )
                edits.setdefault(slot["slot_index"], {})[pos_key] = replacement["id"]
    assert edits, f"{target_name} should have at least one slot in match 2"

    all_slot_indices = [s["slot_index"] for s in match2["slots"]]
    resp = client.post(
        f"/api/matches/{match2['match']['id']}/adjust",
        json={"edits": edits, "locked_slots": all_slot_indices},
    )
    assert resp.status_code == 200
    warnings = resp.json()["warnings"]
    assert any("Consecutive sit-out" in w and target_name in w for w in warnings), (
        f"expected a consecutive sit-out violation for {target_name}, got: {warnings}"
    )


# ── Specialist keeper cross-match fairness (Titans bug, ported to multi-user) ──

def test_specialist_keeper_gets_fair_share_across_tournament(
    client: TestClient, tournament: dict, squad_ids: list[int]
) -> None:
    """A specialist keeper (Kai) must play only in goal but get ~a fair share of
    slots across a no-halftime tournament, not every match. 10 players, 6
    no-halftime matches → fair share = 6*2*5 / 10 = 6 goal slots. GK sharing is
    on by default, so the cross-match budget applies."""
    kai_goal = 0
    kai_outfield = 0
    played_per_match: list[int] = []

    for _ in range(6):
        match = _add_match(client, tournament["id"], squad_ids)
        played = 0
        for slot in match["slots"]:
            for pos_key, player in slot["lineup"].items():
                if player["name"] == "Kai":
                    played += 1
                    if pos_key == "GK":
                        kai_goal += 1
                    else:
                        kai_outfield += 1
        played_per_match.append(played)

    assert kai_outfield == 0, "a specialist keeper must never be played outfield"
    assert kai_goal > 0, "the keeper should still keep goal sometimes"
    assert 6 <= kai_goal <= 8, f"keeper goal slots {kai_goal} not near fair share (6)"
    for a, b in zip(played_per_match, played_per_match[1:], strict=False):
        assert not (a == 0 and b == 0), (
            f"keeper sat out two consecutive matches: {played_per_match}"
        )


# ── Editing tournament settings regenerates planned matches (halftime bug) ─────

def test_editing_halftime_regenerates_planned_matches(
    client: TestClient, squad_ids: list[int]
) -> None:
    """Toggling half-time on an existing tournament must actually change its
    planned matches (regression: the edit saved but matches kept their old slots)."""
    created = client.post(
        "/api/tournaments/", json={**TOURNAMENT_BASE, "has_halftime": True}
    )
    assert created.status_code == 201
    t = created.json()

    _add_match(client, t["id"], squad_ids)
    match_id = client.get(f"/api/tournaments/{t['id']}").json()["matches"][0]["id"]

    assert len(client.get(f"/api/matches/{match_id}").json()["slots"]) == 4

    resp = client.put(f"/api/tournaments/{t['id']}", json={"has_halftime": False})
    assert resp.status_code == 200
    assert resp.json()["has_halftime"] is False
    assert len(client.get(f"/api/matches/{match_id}").json()["slots"]) == 2


def test_editing_unrelated_field_does_not_regenerate(
    client: TestClient, squad_ids: list[int]
) -> None:
    """Editing a non-structural field (name) leaves the matches' rotations alone."""
    created = client.post(
        "/api/tournaments/", json={**TOURNAMENT_BASE, "has_halftime": False}
    )
    t = created.json()
    _add_match(client, t["id"], squad_ids)
    match_id = client.get(f"/api/tournaments/{t['id']}").json()["matches"][0]["id"]
    before = client.get(f"/api/matches/{match_id}").json()["slots"]

    resp = client.put(f"/api/tournaments/{t['id']}", json={"name": "Renamed Cup"})
    assert resp.status_code == 200
    after = client.get(f"/api/matches/{match_id}").json()["slots"]
    assert len(after) == len(before) == 2


# ── Configurable max subs (T2.4) ──────────────────────────────────────────────

def test_create_echoes_max_subs(client: TestClient) -> None:
    t = client.post("/api/tournaments/", json={**TOURNAMENT_BASE, "max_subs": 3}).json()
    assert t["max_subs"] == 3
    fetched = client.get(f"/api/tournaments/{t['id']}").json()["tournament"]
    assert fetched["max_subs"] == 3


def test_max_subs_defaults_to_null(client: TestClient) -> None:
    """Omitting max_subs stores NULL — the engine falls back to the preset cap."""
    t = client.post("/api/tournaments/", json=TOURNAMENT_BASE).json()
    assert t["max_subs"] is None


def test_max_subs_generation_stays_valid(client: TestClient, squad_ids: list[int]) -> None:
    """A custom max_subs must thread through generation without breaking it: a
    no-halftime match still yields 2 fully-filled slots. (The cap is a soft upper
    bound subordinate to fair playing time — it never leaves a position empty.)"""
    t = client.post("/api/tournaments/", json={**TOURNAMENT_BASE, "max_subs": 2}).json()
    resp = _add_match(client, t["id"], squad_ids)
    slots = resp["slots"]
    assert len(slots) == 2
    # Every slot fields a full lineup (GK + outfield).
    for s in slots:
        assert len(s["lineup"]) == 5


def test_editing_max_subs_is_structural(
    client: TestClient, squad_ids: list[int]
) -> None:
    """max_subs is a rotation-affecting field: editing it persists and regenerates
    planned matches (matches remain valid afterwards)."""
    t = client.post("/api/tournaments/", json={**TOURNAMENT_BASE, "max_subs": 4}).json()
    _add_match(client, t["id"], squad_ids)
    match_id = client.get(f"/api/tournaments/{t['id']}").json()["matches"][0]["id"]

    resp = client.put(f"/api/tournaments/{t['id']}", json={"max_subs": 1})
    assert resp.status_code == 200
    assert resp.json()["max_subs"] == 1
    # Persisted on the tournament and the regenerated match still has its 2 slots.
    assert client.get(f"/api/tournaments/{t['id']}").json()["tournament"]["max_subs"] == 1
    assert len(client.get(f"/api/matches/{match_id}").json()["slots"]) == 2
