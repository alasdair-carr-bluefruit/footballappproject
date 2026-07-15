"""Game configuration: team sizes, formations, sub limits, and presets.

Each team size (5v5 through 11v11) has a set of valid formations and
match-structure rules. A GameConfig bundles these into a single object
that the algorithm pipeline consumes.
"""
from __future__ import annotations

from dataclasses import dataclass


_DEF_KEYS: dict[int, list[str]] = {
    1: ["CB"],
    2: ["CB", "CB2"],
    3: ["LB", "CB", "RB"],
    4: ["LB", "CB", "CB2", "RB"],
}

_MID_KEYS: dict[int, list[str]] = {
    1: ["CM"],
    2: ["LM", "RM"],
    3: ["LM", "CM", "RM"],
    4: ["LM", "CM", "CM2", "RM"],
    5: ["LM", "CM", "CM2", "RM", "CAM"],
}

_FWD_KEYS: dict[int, list[str]] = {
    1: ["CF"],
    2: ["CF", "CF2"],
    3: ["LW", "CF", "RW"],
}


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
        """Return real football position keys for this formation.

        Defense:  1→[CB]  2→[CB,CB2]  3→[LB,CB,RB]  4→[LB,CB,CB2,RB]
        Midfield: 1→[CM]  2→[LM,RM]  3→[LM,CM,RM]  4→[LM,CM,CM2,RM]  5→[LM,CM,CM2,RM,CAM]
        Forward:  1→[CF]  2→[CF,CF2]  3→[LW,CF,RW]
        """
        return _DEF_KEYS[self.defense] + _MID_KEYS[self.midfield] + _FWD_KEYS[self.forward]

    def __str__(self) -> str:
        return self.notation


@dataclass(frozen=True)
class GameConfig:
    """Complete match configuration for a given team size and formation."""

    team_size: int
    formation: Formation
    periods: int  # 4 (quarters) or 2 (halves)
    period_length_mins: float  # minutes per period; float to allow e.g. 12.5
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
    period_length_mins: float,
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
    7: _make_configs(7, ["2-3-1", "3-2-1", "3-1-2", "1-3-2", "2-2-2", "2-1-3"], 4, 12.5, 3, 4, "Quarter"),
    9: _make_configs(9, ["3-3-2", "2-4-2", "3-2-3", "3-4-1", "4-3-1"], 2, 30, 4, None, "Half"),
}

DEFAULT_FORMATIONS: dict[int, str] = {
    5: "1-2-1",
    6: "1-3-1",
    7: "2-3-1",
    9: "3-3-2",
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


def build_tournament_config(
    team_size: int,
    formation: str,
    match_duration_mins: int,
    has_halftime: bool,
) -> GameConfig:
    """Build a GameConfig for a tournament match with custom period structure.

    Tournament matches use 1 period (no halftime) or 2 periods (with halftime),
    giving 2 or 4 total slots respectively. Sub limits are inherited from the
    nearest season preset for the given team size.
    """
    formation_obj = Formation.parse(formation)
    preset_configs = PRESET_CONFIGS.get(team_size, {})
    default_f = DEFAULT_FORMATIONS.get(team_size, formation)
    base = preset_configs.get(formation) or preset_configs.get(default_f)

    mid_period_subs = base.mid_period_subs if base else 2

    if has_halftime:
        periods = 2
        period_length_mins = max(1, match_duration_mins // 2)
        break_subs = base.break_subs if base else 5
        period_label = "Half"
    else:
        periods = 1
        period_length_mins = match_duration_mins
        break_subs = None
        period_label = "Period"

    return GameConfig(
        team_size=team_size,
        formation=formation_obj,
        periods=periods,
        period_length_mins=period_length_mins,
        mid_period_subs=mid_period_subs,
        break_subs=break_subs,
        period_label=period_label,
    )
