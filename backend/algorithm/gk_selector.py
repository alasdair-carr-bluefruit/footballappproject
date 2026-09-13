"""GK slot assignment logic.

GK assignments are made per quarter (not per slot), since the GK never
changes mid-quarter. The same GK is duplicated for both half-quarters
of each quarter.

Priority order (strict tier fallback, not mixing):
  1. specialist  -- see squad_size rules
  2. preferred   -- first choice when specialist absent or off-bench
  3. can_play    -- second choice
  4. emergency_only -- last resort; adds warning to plan

Time budget:
  max GK quarters per player = ceil(fair_share_slots / 2)
  This prevents any one GK player from exceeding their fair share of total slots.
  When a player exhausts their GK quarter budget, the next eligible tier is used.
"""
from __future__ import annotations

import random
from itertools import permutations

from backend.models.player import GKTier, Player


def select_gk_for_slots(
    players: list,
    num_slots: int,
    squad_size: int,
    players_per_slot: int = 5,
    share_gk: bool | None = None,
    specialist_max_slots: int | None = None,
) -> tuple:
    """Return a list of GK assignments (one per slot) and any warnings.

    GK assignments are made per-period (same GK for both sub-periods).

    ``share_gk`` controls how a *specialist* keeper's time is handled:
      * True  — the keeper splits goal duty (plays alternate periods, rests the
        others while a backup covers) so their total pitch time matches the rest
        of the squad. This is the fair-time default set by the setup form.
      * False — the keeper stays in goal every period (traditional; they play
        more total time than outfielders).
      * None  — legacy heuristic used by bare callers/tests: share only when the
        squad has 10+ players.
    Sharing needs at least one spare player to cover goal while the keeper rests,
    so it is forced off when ``squad_size <= players_per_slot`` (no bench).

    ``specialist_max_slots`` adds a *cross-match* cap for tournaments: when sharing
    is on, the specialist keeps goal only up to this many slots this match (their
    fair share across the day minus what they've already played — see
    ``match_service``), then a backup covers and the keeper rests. Within a single
    match, one goal period alternates within it as before. ``None`` = no cap
    (season / single match) — the legacy within-match alternation is used. Ignored
    when sharing is off (the keeper stays in goal all match by the coach's choice).

    Returns:
        gk_assignments: list of length num_slots
        warnings: list of warning strings
    """
    num_quarters = num_slots // 2
    total_player_slots = num_slots * players_per_slot
    fair_share = total_player_slots // squad_size
    # Max GK quarters one player can take within their fair-share budget.
    # Each GK quarter = 2 slots. Use floor(fair_share / 2) so outfield time is possible.
    max_gk_quarters = max(1, fair_share // 2)
    # One period of headroom above the strict budget, offered only to a willing
    # keeper and only when the alternative is a child who never picked GK (see
    # _pick_gk_for_quarter). Withheld unless that extra period still leaves the
    # keeper within fair share + 1 slots — the tolerance equal time already allows.
    # Two guards, both needed: the extra period must keep the keeper within fair
    # share + 1 slots (the tolerance equal time already allows), and must not leave
    # one child in goal for more than half the match — stretching past that isn't
    # sharing goal duty, it's the opposite of what the coach asked for.
    stretch_gk_quarters = (
        max_gk_quarters + 1
        if (max_gk_quarters + 1) * 2 <= fair_share + 1
        and (max_gk_quarters + 1) * 2 <= num_slots // 2
        else max_gk_quarters
    )

    warnings: list = []
    specialist = next((p for p in players if p.gk_status == GKTier.SPECIALIST), None)

    if specialist is not None:
        if share_gk is None:
            share = squad_size >= 10  # legacy default
        else:
            share = share_gk
        # Can only rest the keeper if a spare player exists to cover goal.
        if squad_size <= players_per_slot:
            share = False
        if not share:
            # Specialist plays every quarter
            gk_per_quarter = [specialist] * num_quarters
        elif specialist_max_slots is not None:
            # Tournament: keeper keeps goal only up to their cross-match budget;
            # a backup covers once it's spent (keeper rests, never plays outfield).
            spec_quarter_budget = specialist_max_slots // 2  # 2 slots per goal period
            other_players = [p for p in players if p is not specialist]
            backup_pool = _ranked_gk_pool(other_players, warnings)
            q_counts: dict = {}
            gk_per_quarter = []
            spec_used = 0
            for _ in range(num_quarters):
                if spec_used < spec_quarter_budget:
                    gk_per_quarter.append(specialist)
                    spec_used += 1
                elif backup_pool:
                    gk = _pick_gk_for_quarter(
                        backup_pool, q_counts, max_gk_quarters, stretch=stretch_gk_quarters,
                    )
                    gk_per_quarter.append(gk)
                    q_counts[id(gk)] = q_counts.get(id(gk), 0) + 1
                else:
                    # No backup keeper available — the specialist must cover goal.
                    gk_per_quarter.append(specialist)
                    spec_used += 1
        else:
            # Specialist plays Q1 and Q3 (alternating quarters).
            # Non-specialist GKs cover Q2 and Q4 — spreads GK experience more evenly.
            other_players = [p for p in players if p is not specialist]
            gk_pool = _ranked_gk_pool(other_players, warnings)
            q_counts = {}
            gk_per_quarter = []
            for q in range(num_quarters):
                if q % 2 == 0:  # Q1, Q3
                    gk_per_quarter.append(specialist)
                else:           # Q2, Q4
                    gk = _pick_gk_for_quarter(
                        gk_pool, q_counts, max_gk_quarters, stretch=stretch_gk_quarters,
                    )
                    gk_per_quarter.append(gk)
                    q_counts[id(gk)] = q_counts.get(id(gk), 0) + 1
    else:
        gk_pool = _ranked_gk_pool(players, warnings)
        if not gk_pool:
            warnings.append("No GK-capable player available. Manual assignment required.")
            return [None] * num_slots, warnings

        gk_per_quarter = []
        q_counts_: dict = {}
        for _ in range(num_quarters):
            gk = _pick_gk_for_quarter(
                gk_pool, q_counts_, max_gk_quarters,
                avoid=gk_per_quarter[-1] if gk_per_quarter else None,
                stretch=stretch_gk_quarters,
            )
            gk_per_quarter.append(gk)
            q_counts_[id(gk)] = q_counts_.get(id(gk), 0) + 1
        gk_per_quarter = _spread_gk_quarters(gk_per_quarter)

    # Expand: each quarter produces 2 slots with the same GK
    gk_per_slot = [gk for gk in gk_per_quarter for _ in range(2)]
    return gk_per_slot, warnings


def _spread_gk_quarters(gk_per_quarter: list) -> list:
    """Reorder WHO keeps goal in WHICH period so no keeper is left sitting a block.

    A keeper taking two of four periods has spent their whole fair share in goal,
    so whatever periods they don't keep, they sit. Q1+Q4 leaves them benched for
    the entire middle of the match; Q1+Q2 leaves them benched for the whole second
    half. Only the alternating patterns (Q1+Q3, Q2+Q4) keep their bench spells
    short — and the greedy per-period pick, which only knows about the period
    before, lands on a bad pattern often enough that it was the single biggest
    source of long bench runs in an 11-player 5-a-side squad.

    This permutes the periods only: every keeper ends up with exactly the number of
    periods they were already given, so playing time and GK budgets are untouched.
    Tier priority is preserved as a tiebreak — among arrangements that bench people
    equally well, the better-tier keeper still takes the earlier period — and the
    original order wins outright ties.
    """
    n = len(gk_per_quarter)
    if n < 3:
        return gk_per_quarter

    tier_rank = {
        GKTier.SPECIALIST: 0, GKTier.PREFERRED: 1,
        GKTier.CAN_PLAY: 2, GKTier.EMERGENCY_ONLY: 3,
    }

    def score(order: list) -> tuple:
        # Bench cost: only keepers with 2+ periods are "fully booked" — a keeper
        # with a single period still has outfield slots left for the balancer.
        bench = 0
        for keeper in {id(g): g for g in order if g is not None}.values():
            quarters = [i for i, g in enumerate(order) if g is keeper]
            if len(quarters) < 2:
                continue
            on = {i * 2 + h for i in quarters for h in (0, 1)}
            longest = run = 0
            for slot in range(n * 2):
                run = 0 if slot in on else run + 1
                longest = max(longest, run)
            bench += longest
        # Tier cost: minimised when the best available tier keeps goal earliest.
        # Weight is (worst_rank - rank) so a better tier keeping goal EARLIER scores
        # lower — the plain rank would have done exactly the opposite.
        tier = sum(
            i * (3 - tier_rank.get(g.gk_status, 3))
            for i, g in enumerate(order) if g is not None
        )
        return (bench, tier)

    best = list(gk_per_quarter)
    best_score = score(best)
    seen = {tuple(id(g) for g in best)}
    for idx in permutations(range(n)):
        candidate = [gk_per_quarter[i] for i in idx]
        key = tuple(id(g) for g in candidate)
        if key in seen:
            continue
        seen.add(key)
        candidate_score = score(candidate)
        if candidate_score < best_score:
            best, best_score = candidate, candidate_score
    return best


def _pick_gk_for_quarter(
    gk_pool: list, q_counts: dict, max_quarters: int, avoid: Player | None = None,
    stretch: int | None = None,
) -> Player:
    """Pick the best-tier GK who still has budget remaining.

    Within a tier, picks the least-used player (random tiebreak so the same
    player isn't always chosen first). Falls back to least-used overall if all
    players have exhausted their budget.

    ``avoid`` is last quarter's keeper: where another keeper *of the same tier* can
    go in goal, they do — the preference never reaches down a tier.
    A keeper who takes consecutive periods spends the rest of the match on the
    bench in one unbroken block — with a keeper and a backup that used to be
    Q1+Q2 then Q3+Q4, leaving *both* children sitting a full half, every match.
    Alternating gives each the same number of goal periods, just spread out, so
    nobody's playing time changes. Mirrors what the specialist branch above
    already does with Q1/Q3.
    """
    # Walk tier-by-tier; within each tier pick the least-used eligible player
    seen_tier = None
    tier_candidates: list = []
    for p in gk_pool:
        tier = p.gk_status
        if tier != seen_tier:
            # Entering a new tier — check if previous tier had eligible candidates
            if tier_candidates:
                break
            seen_tier = tier
            tier_candidates = []
        if q_counts.get(id(p), 0) < max_quarters:
            tier_candidates.append(p)

    # About to put a child who never picked GK in goal? Let a willing keeper take
    # one period more than the strict fair-share budget first. That budget is
    # floor(fair_share / 2), which rounds a 3-slot fair share down to a single goal
    # period — so an 11-player 5v5 squad with three volunteer keepers could only
    # staff three of its four quarters and the fourth fell to an emergency-tier
    # player. The coach reads that as the app ignoring the positions their players
    # chose, and they're right. One period over is 1 slot above fair share, which
    # equal time already tolerates, and it is only ever spent to keep a
    # non-volunteer out of goal — never to hand a keeper a bigger share for its own
    # sake, since the strict budget above is always tried first, for everyone.
    willing_pool = [p for p in gk_pool if p.gk_status != GKTier.EMERGENCY_ONLY]
    stretch_to = stretch if stretch is not None else max_quarters
    if (
        tier_candidates
        and tier_candidates[0].gk_status == GKTier.EMERGENCY_ONLY
        and stretch_to > max_quarters
    ):
        for tier in (GKTier.SPECIALIST, GKTier.PREFERRED, GKTier.CAN_PLAY):
            willing = [
                p for p in willing_pool
                if p.gk_status == tier and q_counts.get(id(p), 0) < stretch_to
            ]
            if willing:
                tier_candidates = willing
                break

    if not tier_candidates:
        # All exhausted — pick least-used overall (random tiebreak)
        min_count = min(q_counts.get(id(p), 0) for p in gk_pool)
        tier_candidates = [p for p in gk_pool if q_counts.get(id(p), 0) == min_count]

    # Alternation, but only ever *within* the tier we just settled on. Applying it
    # to the whole pool (as this used to) meant "anyone but last period's keeper"
    # outranked "someone who actually chose GK": a squad with one willing keeper
    # put a non-keeper in goal every other period, whatever the coach had picked.
    if avoid is not None and len(tier_candidates) > 1:
        others = [p for p in tier_candidates if p is not avoid]
        if others:
            tier_candidates = others

    # Among candidates, pick least-used; shuffle first so ties are broken randomly
    random.shuffle(tier_candidates)
    return min(tier_candidates, key=lambda p: q_counts.get(id(p), 0))


def _ranked_gk_pool(players: list, warnings: list) -> list:
    """Return all capable non-specialist GK players, best-tier first.

    Never mixes players from different tiers — uses best available tier only
    for the initial pool, but falls back to lower tiers when budget is exceeded.

    Actually returns ALL capable players ordered by tier, so the per-quarter
    picker can fall back tier-by-tier naturally.
    """
    preferred = [p for p in players if p.gk_status == GKTier.PREFERRED]
    can_play = [p for p in players if p.gk_status == GKTier.CAN_PLAY]
    emergency = [p for p in players if p.gk_status == GKTier.EMERGENCY_ONLY]

    if emergency and not preferred and not can_play:
        warnings.append(
            "Warning: Only emergency GK players available "
            "(" + ", ".join(p.name for p in emergency) + "). "
            "Please review the rotation plan."
        )

    # Return in tier order: _pick_gk_for_quarter iterates this list
    return preferred + can_play + emergency
