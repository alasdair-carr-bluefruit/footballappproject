"""Match and squad data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.models.game_config import GameConfig


@dataclass
class Match:
    date: date
    opponent: str = ""
    quarters: int = 4
    quarter_length_mins: int = 10
    game_config: GameConfig | None = None  # None → DEFAULT_CONFIG
    fairness: str = "equal"  # "equal" or "competitive"

    @property
    def half_quarters(self) -> int:
        """Backward-compatible slot count. Prefer game_config.total_slots."""
        if self.game_config:
            return self.game_config.total_slots
        return self.quarters * 2


@dataclass
class Squad:
    players: list = field(default_factory=list)  # list[Player]

    @property
    def available(self) -> list:
        return list(self.players)

    def __len__(self) -> int:
        return len(self.players)
