
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class SquadDB(SQLModel, table=True):
    __tablename__ = "squads"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    name: str = "My Squad"
    team_name: str = ""
    team_logo: str = ""  # base64 DataURL or empty string


class TournamentDB(SQLModel, table=True):
    __tablename__ = "tournaments"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    squad_id: int  # FK to squads.id (not enforced at DB level to keep migrations simple)
    name: str = "Tournament"
    date: str  # ISO date string e.g. "2026-04-12"
    team_size: int = 5
    formation: str = "1-2-1"
    match_duration_mins: int = 10  # total match duration (one period if no halftime)
    has_halftime: int = 0  # 0=False, 1=True (SQLite has no native bool)
    fairness_value: int = 50  # 0=equal time, 100=start strong
    rotation_intensity: int = 50
    status: str = "active"  # "active" | "completed"
    player_position_overrides_json: str = "{}"  # JSON dict: {player_id: [positions]} — tournament-scoped overrides


class PlayerDB(SQLModel, table=True):
    __tablename__ = "players"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    squad_id: int = Field(foreign_key="squads.id")
    name: str
    gk_status: str  # GKTier value: specialist | preferred | can_play | emergency_only
    def_restricted: bool = False
    skill_rating: int = 3
    preferred_positions: str = "[]"  # JSON list of position types e.g. '["DEF","MID"]'
    best_position: str = ""  # e.g. "DEF", "MID", "FWD", or "" for unset
    shirt_number: int | None = None  # optional squad number (1–99)
    source_tournament_id: int | None = None  # if set, guest player scoped to this tournament


class MatchDB(SQLModel, table=True):
    __tablename__ = "matches"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    squad_id: int = Field(foreign_key="squads.id")
    date: str  # ISO date string e.g. "2026-03-25"
    opponent: str = ""
    quarters: int = 4
    quarter_length_mins: int = 10
    team_size: int = 5
    formation: str = "1-2-1"
    fairness: str = "equal"  # "equal" or "competitive"
    fairness_value: int = 0  # 0-100 slider raw value
    rotation_intensity: int = 50  # 0 = specialist, 100 = all-rounder
    home_away: str = "home"  # "home" or "away"
    opponent_goals: int = 0
    status: str = "planned"  # "planned" | "in_progress" | "completed"
    current_slot: int = 0  # furthest slot reached during live match
    tournament_id: int | None = None  # if set, this match belongs to a tournament
    tournament_stage: str = ""  # "group" or "knockout" (empty for season matches)
    match_number: int | None = None  # sequence within tournament (1-based)


class RotationPlanDB(SQLModel, table=True):
    __tablename__ = "rotation_plans"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    match_id: int = Field(foreign_key="matches.id", unique=True)
    slots_json: str  # JSON list of {slot_index, lineup: {pos: player_id}}
    warnings_json: str = "[]"
    goals_json: str = "{}"  # JSON dict: {player_id: goal_count}
    available_player_ids_json: str = "[]"  # JSON list of player IDs selected for this match
    removed_players_json: str = "{}"  # JSON dict: {player_id: from_slot_index}


# ── Relational rotation storage ─────────────────────────────────────────────────
#
# These normalise the RotationPlanDB JSON blobs (slots_json, goals_json,
# available_player_ids_json, removed_players_json) into proper tables. Keyed by
# match_id (matches RotationPlanDB's 1:1 relationship with a match). warnings_json
# stays on RotationPlanDB — it's plan metadata, not relational data.


class SlotDB(SQLModel, table=True):
    __tablename__ = "slots"  # type: ignore[assignment]
    __table_args__ = (UniqueConstraint("match_id", "slot_index", name="uq_slot_match_index"),)

    id: int | None = Field(default=None, primary_key=True)
    match_id: int = Field(foreign_key="matches.id", index=True)
    slot_index: int  # 0..N; a slot row exists even when its lineup is empty


class SlotAssignmentDB(SQLModel, table=True):
    __tablename__ = "slot_assignments"  # type: ignore[assignment]
    __table_args__ = (UniqueConstraint("slot_id", "position", name="uq_assignment_slot_position"),)

    id: int | None = Field(default=None, primary_key=True)
    slot_id: int = Field(foreign_key="slots.id", index=True)
    position: str  # position code e.g. "GK", "LB", "CM", "CF"
    player_id: int  # references players.id (not FK-enforced, matching existing convention)


class GoalRecordDB(SQLModel, table=True):
    __tablename__ = "goal_records"  # type: ignore[assignment]
    __table_args__ = (UniqueConstraint("match_id", "player_id", name="uq_goal_match_player"),)

    id: int | None = Field(default=None, primary_key=True)
    match_id: int = Field(foreign_key="matches.id", index=True)
    player_id: int
    goals: int = 0


class MatchAvailabilityDB(SQLModel, table=True):
    __tablename__ = "match_availability"  # type: ignore[assignment]
    __table_args__ = (UniqueConstraint("match_id", "player_id", name="uq_avail_match_player"),)

    id: int | None = Field(default=None, primary_key=True)
    match_id: int = Field(foreign_key="matches.id", index=True)
    player_id: int


class RemovedPlayerDB(SQLModel, table=True):
    __tablename__ = "removed_players"  # type: ignore[assignment]
    __table_args__ = (UniqueConstraint("match_id", "player_id", name="uq_removed_match_player"),)

    id: int | None = Field(default=None, primary_key=True)
    match_id: int = Field(foreign_key="matches.id", index=True)
    player_id: int
    from_slot: int


class FeedbackDB(SQLModel, table=True):
    __tablename__ = "feedback"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    created_at: str  # ISO datetime
    description: str
    context_json: str = "{}"  # JSON dict: screen, match id, user agent, etc.
    forwarded: bool = False  # True once successfully sent to GitHub
    issue_url: str = ""  # GitHub issue URL when forwarded
