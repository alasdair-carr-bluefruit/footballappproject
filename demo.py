"""Quick demo of the rotation engine. Run with:

    cd "/Users/ali/Football App Project"
    source .venv/bin/activate
    PYTHONPATH=. python3 demo.py
"""
from datetime import date

from backend.models.player import Player, GKTier
from backend.models.match import Match, Squad
from backend.algorithm.rotation_engine import generate_rotation
from backend.models.rotation import Position

# ── Tweak your squad here ─────────────────────────────────────────────────────

squad = Squad(players=[
    Player("Kai",   GKTier.SPECIALIST,     skill_rating=1),
    Player("Rowan",     GKTier.PREFERRED,      skill_rating=4),
    Player("Jago", GKTier.CAN_PLAY, skill_rating=5),
    Player("Kobe",   GKTier.CAN_PLAY, skill_rating=4, def_restricted=True),
    Player("Eli",     GKTier.EMERGENCY_ONLY, skill_rating=4),
    Player("Eden",   GKTier.EMERGENCY_ONLY, skill_rating=4),
    Player("Jude",   GKTier.CAN_PLAY, skill_rating=2),
    Player("Jackson",   GKTier.EMERGENCY_ONLY, skill_rating=3),
    Player("Oscar",    GKTier.EMERGENCY_ONLY, skill_rating=3),
    Player("Wesley",    GKTier.PREFERRED, skill_rating=2),
])

match = Match(date=date(2026, 3, 24), opponent="Rovers FC")

# ── Generate ──────────────────────────────────────────────────────────────────

plan = generate_rotation(squad, match)

# ── Print rotation table ──────────────────────────────────────────────────────

COL = 12

def row(cells):
    return "  ".join(str(c).ljust(COL) for c in cells)

print()
print(f"  Match: {match.date}  vs  {match.opponent or '(no opponent)'}")
print(f"  Squad: {len(squad)} players\n")

header = ["Slot", "GK", "DEF", "MID", "MID", "FWD", "Skill"]
print("  " + row(header))
print("  " + "-" * (COL * 7 + 12))

for slot in plan.slots:
    q = slot.quarter
    hq = "H1" if slot.is_first_half_of_quarter else "H2"
    label = f"Q{q} {hq}"
    if slot.is_first_half_of_quarter and q > 1:
        print("  " + "·" * (COL * 7 + 12))   # quarter break divider

    gk   = slot.lineup.get(Position.GK,   None)
    def_ = slot.lineup.get(Position.DEF,  None)
    mid1 = slot.lineup.get(Position.MID1, None)
    mid2 = slot.lineup.get(Position.MID2, None)
    fwd  = slot.lineup.get(Position.FWD,  None)
    skill = slot.outfield_skill_total

    cells = [
        label,
        gk.name   if gk   else "-",
        def_.name if def_ else "-",
        mid1.name if mid1 else "-",
        mid2.name if mid2 else "-",
        fwd.name  if fwd  else "-",
        skill,
    ]
    print("  " + row(cells))

# ── Playing time summary ──────────────────────────────────────────────────────

print()
print("  Playing time (half-quarter slots):")
print()

counts = {p: plan.slot_count_for_player(p) for p in squad.available}
max_slots = max(counts.values())

for p in squad.available:
    n = counts[p]
    bar = "█" * n + "░" * (max_slots - n)
    tag = ""
    if p.gk_status == GKTier.SPECIALIST:
        tag = " [specialist]"
    elif p.def_restricted:
        tag = " [DEF-restricted]"
    print(f"    {p.name:<10} {bar}  {n} slots{tag}")

# ── Warnings ─────────────────────────────────────────────────────────────────

if plan.warnings:
    print()
    print("  ⚠  Warnings / violations:")
    for w in plan.warnings:
        print(f"     • {w}")

print()
