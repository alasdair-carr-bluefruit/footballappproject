
from sqlmodel import Field, SQLModel


class SquadDB(SQLModel, table=True):
    __tablename__ = "squads"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    name: str = "My Squad"


class PlayerDB(SQLModel, table=True):
    __tablename__ = "players"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    squad_id: int = Field(foreign_key="squads.id")
    name: str
    gk_status: str  # GKTier value: specialist | preferred | can_play | emergency_only
    def_restricted: bool = False
    skill_rating: int = 3


class MatchDB(SQLModel, table=True):
    __tablename__ = "matches"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    squad_id: int = Field(foreign_key="squads.id")
    date: str  # ISO date string e.g. "2026-03-25"
    opponent: str = ""
    quarters: int = 4
    quarter_length_mins: int = 10


class RotationPlanDB(SQLModel, table=True):
    __tablename__ = "rotation_plans"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    match_id: int = Field(foreign_key="matches.id", unique=True)
    slots_json: str  # JSON list of {slot_index, lineup: {pos: player_id}}
    warnings_json: str = "[]"
