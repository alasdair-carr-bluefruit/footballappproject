
from sqlmodel import Field, SQLModel


class SquadDB(SQLModel, table=True):
    __tablename__ = "squads"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    name: str = "My Squad"
    team_name: str = "My Team"
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
