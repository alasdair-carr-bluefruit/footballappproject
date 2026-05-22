"""Player data model."""

from dataclasses import dataclass, field
from enum import StrEnum


class GKTier(StrEnum):
    SPECIALIST = "specialist"
    PREFERRED = "preferred"
    CAN_PLAY = "can_play"
    EMERGENCY_ONLY = "emergency_only"


@dataclass(unsafe_hash=True)
class Player:
    name: str
    gk_status: GKTier
    def_restricted: bool = False
    skill_rating: int = 3  # 1–5, coach-only, never displayed after setup
    preferred_positions: list[str] = field(default_factory=list, hash=False, compare=False)
    best_position: str | None = field(default=None, hash=False, compare=False)
