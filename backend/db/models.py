
from sqlmodel import Field, SQLModel


class SquadDB(SQLModel, table=True):
    __tablename__ = "squads"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    name: str = "My Squad"
    team_name: str = "My Team"
    team_logo: str = ""  # base64 DataURL or empty string


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


class RotationPlanDB(SQLModel, table=True):
    __tablename__ = "rotation_plans"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    match_id: int = Field(foreign_key="matches.id", unique=True)
    slots_json: str  # JSON list of {slot_index, lineup: {pos: player_id}}
    warnings_json: str = "[]"
    goals_json: str = "{}"  # JSON dict: {player_id: goal_count}
    available_player_ids_json: str = "[]"  # JSON list of player IDs selected for this match
