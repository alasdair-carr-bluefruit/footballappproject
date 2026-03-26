"""Match and squad data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Match:
    date: date
    opponent: str = ""
    quarters: int = 4
    quarter_length_mins: int = 10

    @property
    def half_quarters(self) -> int:
        return self.quarters * 2


@dataclass
class Squad:
    players: list = field(default_factory=list)  # list[Player]

    @property
    def available(self) -> list:
        return list(self.players)

    def __len__(self) -> int:
        return len(self.players)
