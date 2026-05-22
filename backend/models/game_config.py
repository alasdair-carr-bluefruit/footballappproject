"""Game configuration: team sizes, formations, sub limits, and presets.

Each team size (5v5 through 11v11) has a set of valid formations and
match-structure rules. A GameConfig bundles these into a single object
that the algorithm pipeline consumes.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Formation:
    """A formation parsed from 'D-M-F' notation (e.g. '2-3-1')."""

    defense: int
    midfield: int
    forward: int

    @classmethod
    def parse(cls, notation: str) -> Formation:
        """Parse '2-3-1' into Formation(2, 3, 1)."""
        parts = notation.split("-")
        if len(parts) != 3:
            raise ValueError(f"Invalid formation notation: {notation!r} (expected 'D-M-F')")
        return cls(defense=int(parts[0]), midfield=int(parts[1]), forward=int(parts[2]))

    @property
    def outfield_count(self) -> int:
        return self.defense + self.midfield + self.forward

    @property
    def team_size(self) -> int:
        """Players on pitch including GK."""
        return 1 + self.outfield_count

    @property
    def notation(self) -> str:
        return f"{self.defense}-{self.midfield}-{self.forward}"

    def outfield_positions(self) -> list[str]:
        """Generate position keys for this formation.

        Single-count positions use bare names (DEF, FWD).
        Multi-count positions use numbered names (DEF, DEF2, DEF3; MID1, MID2).
        This preserves backward compatibility with the original 1-2-1 formation
        which used DEF, MID1, MID2, FWD.
        """
        positions: list[str] = []

        # DEF positions: DEF, DEF2, DEF3, DEF4
        for i in range(1, self.defense + 1):
            positions.append("DEF" if i == 1 else f"DEF{i}")

        # MID positions: always numbered MID1, MID2, ...
        for i in range(1, self.midfield + 1):
            positions.append(f"MID{i}")

        # FWD positions: FWD, FWD2, FWD3
        for i in range(1, self.forward + 1):
            positions.append("FWD" if i == 1 else f"FWD{i}")

        return positions

    def __str__(self) -> str:
        return self.notation


@dataclass(frozen=True)
class GameConfig:
    """Complete match configuration for a given team size and formation."""

    team_size: int
    formation: Formation
    periods: int  # 4 (quarters) or 2 (halves)
    period_length_mins: int
    mid_period_subs: int  # max subs at mid-period transition
    break_subs: int | None  # max subs at period break (None = unlimited)
    period_label: str  # "Quarter" or "Half"

    @property
    def total_slots(self) -> int:
        """Total sub-period slots in the match."""
        return self.periods * 2

    @property
    def players_per_slot(self) -> int:
        return self.formation.team_size

    def all_positions(self) -> list[str]:
        """All position keys including GK."""
        return ["GK"] + self.formation.outfield_positions()


# ── Default (backward-compatible 5v5) ────────────────────────────────────────

DEFAULT_FORMATION = Formation(defense=1, midfield=2, forward=1)

DEFAULT_CONFIG = GameConfig(
    team_size=5,
    formation=DEFAULT_FORMATION,
    periods=4,
    period_length_mins=10,
    mid_period_subs=2,
    break_subs=5,
    period_label="Quarter",
)


# ── Preset configurations per team size ──────────────────────────────────────

def _make_configs(
    team_size: int,
    formations: list[str],
    periods: int,
    period_length_mins: int,
    mid_period_subs: int,
    break_subs: int | None,
    period_label: str,
) -> dict[str, GameConfig]:
    return {
        f: GameConfig(
            team_size=team_size,
            formation=Formation.parse(f),
            periods=periods,
            period_length_mins=period_length_mins,
            mid_period_subs=mid_period_subs,
            break_subs=break_subs,
            period_label=period_label,
        )
        for f in formations
    }


PRESET_CONFIGS: dict[int, dict[str, GameConfig]] = {
    5: _make_configs(5, ["1-2-1", "2-1-1"], 4, 10, 2, 5, "Quarter"),
    6: _make_configs(6, ["1-3-1", "2-2-1", "1-2-2"], 4, 10, 2, 5, "Quarter"),
    7: _make_configs(7, ["2-3-1", "1-3-2", "2-2-2"], 4, 10, 3, 4, "Quarter"),
    9: _make_configs(9, ["3-3-2", "2-4-2", "3-2-3"], 2, 20, 4, None, "Half"),
    11: _make_configs(11, ["4-4-2", "4-3-3", "3-5-2"], 2, 25, 4, None, "Half"),
}

DEFAULT_FORMATIONS: dict[int, str] = {
    5: "1-2-1",
    6: "1-3-1",
    7: "2-3-1",
    9: "3-3-2",
    11: "4-4-2",
}


def get_config(team_size: int, formation: str) -> GameConfig:
    """Look up a preset GameConfig by team size and formation notation.

    Raises KeyError if the combination is not valid.
    """
    configs = PRESET_CONFIGS.get(team_size)
    if configs is None:
        raise KeyError(f"No presets for team size {team_size}")
    config = configs.get(formation)
    if config is None:
        valid = ", ".join(configs.keys())
        raise KeyError(f"Formation {formation!r} not valid for {team_size}v{team_size}. Valid: {valid}")
    return config
