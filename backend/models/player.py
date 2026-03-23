"""Player data model."""

from dataclasses import dataclass, field
from enum import Enum


class GKTier(str, Enum):
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
    # position_history added in v0.5 when DB is introduced
