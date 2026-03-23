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
from enum import Enum
from typing import Optional

from backend.models.player import Player


class Position(str, Enum):
    GK = "GK"
    DEF = "DEF"
    MID1 = "MID1"
    MID2 = "MID2"
    FWD = "FWD"


# Formation slots: 1 GK + 1 DEF + 2 MID + 1 FWD
OUTFIELD_POSITIONS = [Position.DEF, Position.MID1, Position.MID2, Position.FWD]
ALL_POSITIONS = [Position.GK] + OUTFIELD_POSITIONS


@dataclass
class SlotAssignment:
    slot_index: int  # 0-7
    lineup: dict = field(default_factory=dict)  # dict[Position, Player]

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
    def gk(self) -> Optional[Player]:
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
