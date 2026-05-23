"""Rotation plan data models.

slot_index convention:
  0 = Q1 first half-quarter
  1 = Q1 second half-quarter
  2 = Q2 first half-quarter
  3 = Q2 second half-quarter
  ...
  6 = Q4 first half-quarter
  7 = Q4 second half-quarter

Quarter boundary (full break): transitions 1->2, 3->4, 5->6
Mid-quarter point: transitions 0->1, 2->3, 4->5, 6->7
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from backend.models.player import Player


class Position(StrEnum):
    GK = "GK"
    # DEF positions (DEF is first, DEF2–DEF4 for larger formations)
    DEF = "DEF"
    DEF2 = "DEF2"
    DEF3 = "DEF3"
    DEF4 = "DEF4"
    # MID positions (always numbered)
    MID1 = "MID1"
    MID2 = "MID2"
    MID3 = "MID3"
    MID4 = "MID4"
    MID5 = "MID5"
    # FWD positions (FWD is first, FWD2–FWD3 for larger formations)
    FWD = "FWD"
    FWD2 = "FWD2"
    FWD3 = "FWD3"


def normalize_position(pos: str | Position) -> str:
    """Normalize a position to its base type for variety checking.

    DEF, DEF2, DEF3, DEF4 → 'DEF'
    MID1, MID2, ... MID5  → 'MID'
    FWD, FWD2, FWD3       → 'FWD'
    GK                    → 'GK'
    """
    s = str(pos)
    if s.startswith("MID"):
        return "MID"
    if s.startswith("DEF"):
        return "DEF"
    if s.startswith("FWD"):
        return "FWD"
    return s


def is_def_position(pos: str | Position) -> bool:
    """Return True if the position is any DEF variant."""
    return normalize_position(pos) == "DEF"


# Default 5v5 formation slots: 1 GK + 1 DEF + 2 MID + 1 FWD
OUTFIELD_POSITIONS = [Position.DEF, Position.MID1, Position.MID2, Position.FWD]
ALL_POSITIONS = [Position.GK] + OUTFIELD_POSITIONS


@dataclass
class SlotAssignment:
    slot_index: int  # 0-7
    lineup: dict = field(default_factory=dict)  # dict[Position, Player]
    locked: bool = False

    @property
    def quarter(self) -> int:
        """1-indexed quarter number."""
        return (self.slot_index // 2) + 1

    @property
    def is_first_half_of_quarter(self) -> bool:
        return self.slot_index % 2 == 0

    @property
    def players(self) -> list:
        return list(self.lineup.values())

    @property
    def gk(self) -> Player | None:
        return self.lineup.get(Position.GK)

    @property
    def outfield_players(self) -> list:
        return [p for pos, p in self.lineup.items() if pos != Position.GK]

    @property
    def outfield_skill_total(self) -> int:
        return sum(p.skill_rating for p in self.outfield_players)


@dataclass
class RotationPlan:
    slots: list = field(default_factory=list)  # list[SlotAssignment]
    warnings: list = field(default_factory=list)  # list[str]

    def slot(self, index: int) -> SlotAssignment:
        return self.slots[index]

    def slots_for_player(self, player: Player) -> list:
        return [s for s in self.slots if player in s.players]

    def slot_count_for_player(self, player: Player) -> int:
        return len(self.slots_for_player(player))
