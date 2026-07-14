"""Direct unit tests for skill_balancer internals (C.4 mutation hardening).

The existing ``test_skill_balancer.py`` drives the balancer only through
``generate_rotation`` + ``balance_skills``, which never exercises the hard
constraint helpers with crafted inputs — so mutants in ``_swap_is_valid``,
``_all_mid_quarter_limits_ok``, ``_transition_ok_after_swap``,
``_effective_outfield_ids`` and friends survived. These tests call those
helpers directly on hand-built slots to pin their behaviour.

Known equivalent-mutant tail (deliberately not chased):
- ``_position_variety_ok`` (+ its callers passing ``norm_i``/``norm_j`` and
  ``_norm_pos``) only ever returns True: outfield positions normalise to at
  most DEF/MID/FWD (3 categories), so ``len(after) <= 4`` can never be False.
  Same unreachable-variety story as the validator. We still pin the one
  *reachable* effect — inverting the ``not`` in ``_swap_is_valid`` blocks every
  swap — via ``test_swap_valid_baseline``.
- ``changes // 2`` vs ``changes / 2`` in ``_transition_ok_after_swap``: the
  ``<=`` comparison treats ``2.0`` and ``2`` identically, so it's equivalent.
- ``balance_skills`` loop-counter arithmetic (``max_iterations`` ±1, ``+= 2``,
  ``iterations`` init) — variance decreases monotonically so the loop always
  reaches the same fixpoint well before the cap.
"""
from __future__ import annotations

from backend.algorithm.skill_balancer import (
    _all_mid_quarter_limits_ok,
    _copy_slot,
    _effective_outfield_ids,
    _norm_pos,
    _skill_variance,
    _swap_is_valid,
    _transition_ok_after_swap,
    _try_best_swap,
    balance_skills,
)
from backend.models.player import GKTier
from backend.models.rotation import Position, RotationPlan, SlotAssignment
from tests.conftest import make_player


def _slot(idx, gk, cb, lm, rm, cf, locked=False):
    s = SlotAssignment(slot_index=idx, locked=locked)
    s.lineup = {
        Position.GK: gk,
        Position.CB: cb,
        Position.LM: lm,
        Position.RM: rm,
        Position.CF: cf,
    }
    return s


# ---------------------------------------------------------------------------
# _norm_pos
# ---------------------------------------------------------------------------

class TestNormPos:
    def test_maps_each_category(self):
        assert _norm_pos(Position.CB) == "DEF"
        assert _norm_pos(Position.LM) == "MID"
        assert _norm_pos(Position.CF) == "FWD"
        assert _norm_pos(Position.GK) == "GK"


# ---------------------------------------------------------------------------
# _skill_variance
# ---------------------------------------------------------------------------

class TestSkillVariance:
    def _one_skill_slot(self, idx, total):
        s = SlotAssignment(slot_index=idx)
        s.lineup = {Position.CB: make_player(f"p{idx}", skill_rating=total)}
        return s

    def test_zero_when_equal(self):
        slots = [self._one_skill_slot(0, 3), self._one_skill_slot(1, 3)]
        assert _skill_variance(slots) == 0.0

    def test_exact_value(self):
        # totals 2 and 4 -> mean 3 -> (2-3)^2 + (4-3)^2 = 2
        slots = [self._one_skill_slot(0, 2), self._one_skill_slot(1, 4)]
        assert _skill_variance(slots) == 2.0


# ---------------------------------------------------------------------------
# _copy_slot
# ---------------------------------------------------------------------------

class TestCopySlot:
    def test_preserves_locked_and_deep_copies_lineup(self):
        p = make_player("x")
        src = SlotAssignment(slot_index=2, locked=True)
        src.lineup = {Position.CB: p}
        copy = _copy_slot(src)
        assert copy.locked is True
        assert copy.slot_index == 2
        assert copy.lineup == src.lineup
        assert copy.lineup is not src.lineup  # mutating copy must not touch src

    def test_unlocked_stays_unlocked(self):
        src = SlotAssignment(slot_index=0, locked=False)
        src.lineup = {Position.CB: make_player("x")}
        assert _copy_slot(src).locked is False


# ---------------------------------------------------------------------------
# _effective_outfield_ids
# ---------------------------------------------------------------------------

class TestEffectiveOutfieldIds:
    def _slot_ab(self):
        a = make_player("a")
        b = make_player("b")
        s = SlotAssignment(slot_index=0)
        s.lineup = {Position.CB: a, Position.LM: b}
        return s, a, b

    def test_base_ids_when_slot_untouched(self):
        s, a, b = self._slot_ab()
        z = make_player("z")
        # slot_idx 9 is neither swap_from(0) nor swap_to(5): ids unchanged
        ids = _effective_outfield_ids(s, 9, 0, 5, a, z)
        assert ids == frozenset({id(a), id(b)})

    def test_swap_from_replaces_out_with_in(self):
        s, a, b = self._slot_ab()
        z = make_player("z")
        ids = _effective_outfield_ids(s, 0, 0, 5, a, z)  # a leaves, z enters
        assert ids == frozenset({id(b), id(z)})

    def test_swap_to_replaces_in_with_out(self):
        s, a, b = self._slot_ab()
        z = make_player("z")
        # this slot is the swap_to: player_in (a) leaves, player_out (z) enters
        ids = _effective_outfield_ids(s, 5, 9, 5, z, a)
        assert ids == frozenset({id(b), id(z)})


# ---------------------------------------------------------------------------
# _transition_ok_after_swap
# ---------------------------------------------------------------------------

class TestTransitionOkAfterSwap:
    def _pair(self, out0, out1):
        pos = [Position.CB, Position.LM, Position.RM, Position.CF]
        s0 = SlotAssignment(slot_index=0)
        s0.lineup = {Position.GK: make_player("gk0")}
        for pp, pl in zip(pos, out0):
            s0.lineup[pp] = pl
        s1 = SlotAssignment(slot_index=1)
        s1.lineup = {Position.GK: make_player("gk1")}
        for pp, pl in zip(pos, out1):
            s1.lineup[pp] = pl
        return [s0, s1]

    def test_no_swap_counts_existing_changes(self):
        a, b, c, d, e, f = [make_player(n) for n in "abcdef"]
        slots = self._pair([a, b, c, d], [a, b, e, f])  # 2 players differ
        # i,j far from 0/1 so the swap has no effect: pure existing diff = 2 changes
        dummy = make_player("dummy")
        assert _transition_ok_after_swap(slots, 0, 1, 99, 98, dummy, dummy, 2) is True
        assert _transition_ok_after_swap(slots, 0, 1, 99, 98, dummy, dummy, 1) is False

    def test_boundary_equal_to_limit_is_ok(self):
        a, b, c, d, e, f = [make_player(n) for n in "abcdef"]
        slots = self._pair([a, b, c, d], [a, b, e, f])  # exactly 2 changes
        dummy = make_player("dummy")
        # 2 changes, limit 2 -> "<=" ok; kills the "<" mutant
        assert _transition_ok_after_swap(slots, 0, 1, 99, 98, dummy, dummy, 2) is True

    def test_over_limit_blocks(self):
        a, b, c, d, e, f, g, h = [make_player(n) for n in "abcdefgh"]
        slots = self._pair([a, b, c, d], [e, f, g, h])  # 4 changes
        dummy = make_player("dummy")
        # 4 changes, limit 3 -> False; kills "// 3" and "// 2"->wrong-count mutants
        assert _transition_ok_after_swap(slots, 0, 1, 99, 98, dummy, dummy, 3) is False

    def test_default_sub_limit_is_two(self):
        # 3 existing changes; default limit is 2 -> blocked. Kills the
        # default-argument mutant (mid_period_subs=2 -> 3).
        a, b, c, d, e, f, g = [make_player(n) for n in "abcdefg"]
        slots = self._pair([a, b, c, d], [a, e, f, g])  # differ by 3
        dummy = make_player("dummy")
        assert _transition_ok_after_swap(slots, 0, 1, 99, 98, dummy, dummy) is False

    def test_swap_on_first_slot_changes_count(self):
        # identical pair (0 changes); a swap that alters slot 0 introduces 1 change
        a, b, c, d = [make_player(n) for n in "abcd"]
        z = make_player("z")
        slots = self._pair([a, b, c, d], [a, b, c, d])
        # swap between slot 0 (swap_from) and slot 5: a -> z in slot 0
        assert _transition_ok_after_swap(slots, 0, 1, 0, 5, a, z, 0) is False
        assert _transition_ok_after_swap(slots, 0, 1, 0, 5, a, z, 1) is True


# ---------------------------------------------------------------------------
# _swap_is_valid
# ---------------------------------------------------------------------------

class TestSwapIsValid:
    def _two_quarter_slots(self, **kw):
        """Q1 (slots 0,1) share players a,b,c,d; Q2 (slots 2,3) share e,f,g,h.

        Identical within each quarter so a single cross-quarter swap costs
        exactly one mid-quarter change per pair (well within the limit of 2).
        """
        a = make_player("a", **kw.get("a", {}))
        b = make_player("b", **kw.get("b", {}))
        c = make_player("c")
        d = make_player("d")
        e = make_player("e", **kw.get("e", {}))
        f = make_player("f", **kw.get("f", {}))
        g = make_player("g")
        h = make_player("h")
        gk1 = make_player("gk1")
        gk2 = make_player("gk2")
        slots = [
            _slot(0, gk1, a, b, c, d),
            _slot(1, gk1, a, b, c, d),
            _slot(2, gk2, e, f, g, h),
            _slot(3, gk2, e, f, g, h),
        ]
        return slots, dict(a=a, b=b, c=c, d=d, e=e, f=f, g=g, h=h)

    def test_swap_valid_baseline(self):
        slots, p = self._two_quarter_slots()
        # swap CB(a) in slot 0 with LM(f) in slot 2 — no constraint hit
        assert _swap_is_valid(slots, 0, 2, Position.CB, p["a"], Position.LM, p["f"]) is True

    def test_specialist_player_i_rejected(self):
        slots, p = self._two_quarter_slots(a={"gk_status": GKTier.SPECIALIST})
        assert _swap_is_valid(slots, 0, 2, Position.CB, p["a"], Position.LM, p["f"]) is False

    def test_specialist_player_j_rejected(self):
        slots, p = self._two_quarter_slots(f={"gk_status": GKTier.SPECIALIST})
        assert _swap_is_valid(slots, 0, 2, Position.CB, p["a"], Position.LM, p["f"]) is False

    def test_def_restricted_into_def_pos_i_rejected(self):
        # player_j is DEF-restricted; pos_i (CB) is a DEF position -> blocked
        slots, p = self._two_quarter_slots(f={"def_restricted": True})
        assert _swap_is_valid(slots, 0, 2, Position.CB, p["a"], Position.LM, p["f"]) is False

    def test_def_restricted_into_def_pos_j_rejected(self):
        # player_i ('a') is DEF-restricted; pos_j (CB) is a DEF position -> blocked
        slots, p = self._two_quarter_slots(a={"def_restricted": True})
        assert _swap_is_valid(slots, 0, 2, Position.CB, p["a"], Position.CB, p["e"]) is False

    def test_def_restricted_into_non_def_allowed(self):
        # DEF-restricted player_j moving into MID (LM) is fine
        slots, p = self._two_quarter_slots(f={"def_restricted": True})
        assert _swap_is_valid(slots, 0, 2, Position.LM, p["b"], Position.RM, p["f"]) is True

    def test_unrestricted_into_def_pos_j_allowed(self):
        # pos_j (CB) is DEF but player_i is NOT restricted -> allowed.
        # Kills the "and -> or" mutant on the pos_j DEF guard.
        slots, p = self._two_quarter_slots()
        assert _swap_is_valid(slots, 0, 2, Position.LM, p["b"], Position.CB, p["e"]) is True

    def test_swap_over_mid_quarter_limit_rejected(self):
        # slot 0 and slot 1 already differ by 2; a swap altering slot 1 pushes
        # the 0-1 transition to 3 changes (> 2). None of the specialist/DEF/dup
        # guards fire, so mid-quarter is the deciding constraint.
        a, b, c, d = (make_player(n) for n in "abcd")
        e, f = make_player("e"), make_player("f")
        z = make_player("z")
        gk1, gk2 = make_player("gk1"), make_player("gk2")
        slots = [
            _slot(0, gk1, a, b, c, d),
            _slot(1, gk1, a, b, e, f),   # differs from slot 0 by RM/CF
            _slot(2, gk2, z, make_player("m"), make_player("n"), make_player("o")),
            _slot(3, gk2, z, make_player("p"), make_player("q"), make_player("r")),
        ]
        # swap CB(a) in slot 1 with CB(z) in slot 3 -> slot 0/1 transition -> 3
        assert _swap_is_valid(slots, 1, 3, Position.CB, a, Position.CB, z) is False

    def test_duplicate_incoming_to_slot_i_rejected(self):
        # 'b' already plays in slot 0 (LM); bringing it in as player_j blocks
        a, b, c, d = (make_player(n) for n in "abcd")
        e, g, h = (make_player(n) for n in "egh")
        gk1, gk2 = make_player("gk1"), make_player("gk2")
        slots = [
            _slot(0, gk1, a, b, c, d),
            _slot(1, gk1, a, b, c, d),
            _slot(2, gk2, e, b, g, h),  # b (LM) also here
            _slot(3, gk2, e, b, g, h),
        ]
        # swap CB(a) in slot 0 with LM(b) in slot 2 -> b would duplicate in slot 0
        assert _swap_is_valid(slots, 0, 2, Position.CB, a, Position.LM, b) is False

    def test_duplicate_incoming_to_slot_j_rejected(self):
        # player_i ('b') already plays in slot 2 -> blocked by the slot_j check
        a, b, c, d = (make_player(n) for n in "abcd")
        e, g, h = (make_player(n) for n in "egh")
        gk1, gk2 = make_player("gk1"), make_player("gk2")
        slots = [
            _slot(0, gk1, a, b, c, d),
            _slot(1, gk1, a, b, c, d),
            _slot(2, gk2, e, b, g, h),  # b (LM) also here
            _slot(3, gk2, e, b, g, h),
        ]
        # swap LM(b) in slot 0 with RM(g) in slot 2 -> b already in slot 2
        assert _swap_is_valid(slots, 0, 2, Position.LM, b, Position.RM, g) is False


# ---------------------------------------------------------------------------
# _all_mid_quarter_limits_ok
# ---------------------------------------------------------------------------

class TestAllMidQuarterLimitsOk:
    def test_single_swap_within_limit(self):
        a, b, c, d = (make_player(n) for n in "abcd")
        e, f, g, h = (make_player(n) for n in "efgh")
        gk1, gk2 = make_player("gk1"), make_player("gk2")
        slots = [
            _slot(0, gk1, a, b, c, d),
            _slot(1, gk1, a, b, c, d),
            _slot(2, gk2, e, f, g, h),
            _slot(3, gk2, e, f, g, h),
        ]
        # a<->e single swap -> 1 change per affected pair -> ok
        assert _all_mid_quarter_limits_ok(slots, 0, 2, Position.CB, a, Position.CB, e) is True

    def test_swap_pushing_pair_over_limit_blocked(self):
        # slot 0 and slot 1 already differ by 2 players; a swap altering slot 0
        # pushes the 0-1 mid-quarter transition to 3 changes (> 2).
        a, b, c, d = (make_player(n) for n in "abcd")
        e, f = make_player("e"), make_player("f")
        z_g, z_h = make_player("g"), make_player("h")
        gk1, gk2 = make_player("gk1"), make_player("gk2")
        slots = [
            _slot(0, gk1, a, b, c, d),
            _slot(1, gk1, a, b, e, f),   # differs from slot 0 by 2 (RM/CF)
            _slot(2, gk2, z_g, z_h, make_player("i"), make_player("j")),
            _slot(3, gk2, z_g, z_h, make_player("k"), make_player("l")),
        ]
        # bring z_g into slot 0's CB (a leaves): slot0-slot1 transition -> 3 changes
        assert _all_mid_quarter_limits_ok(
            slots, 0, 2, Position.CB, a, Position.CB, z_g
        ) is False

    def test_higher_sub_limit_permits_bigger_change(self):
        # same over-limit scenario, but a 9v9-style limit of 4 permits it
        a, b, c, d = (make_player(n) for n in "abcd")
        e, f = make_player("e"), make_player("f")
        z_g, z_h = make_player("g"), make_player("h")
        gk1, gk2 = make_player("gk1"), make_player("gk2")
        slots = [
            _slot(0, gk1, a, b, c, d),
            _slot(1, gk1, a, b, e, f),
            _slot(2, gk2, z_g, z_h, make_player("i"), make_player("j")),
            _slot(3, gk2, z_g, z_h, make_player("k"), make_player("l")),
        ]
        assert _all_mid_quarter_limits_ok(
            slots, 0, 2, Position.CB, a, Position.CB, z_g, mid_period_subs=4
        ) is True

    def test_odd_swap_slot_pairs_with_earlier_partner(self):
        # Swap slots are BOTH odd (1 and 3). slot 1's mid-quarter partner is the
        # earlier slot 0, and (0,1) is over-limit while (1,2)/(2,3) are fine.
        # Kills the odd-branch partner mutants (+1 instead of -1) and the
        # "exclude index 0" bounds mutants: both would drop the (0,1) pair.
        a, b, c, d = (make_player(n) for n in "abcd")
        e, f = make_player("e"), make_player("f")
        zg = make_player("zg")
        gk1, gk2 = make_player("gk1"), make_player("gk2")
        slots = [
            _slot(0, gk1, a, b, c, d),
            _slot(1, gk1, a, b, e, f),    # (0,1) differ by 2 already
            _slot(2, gk2, zg, b, e, f),   # == slot 1 after a->zg swap
            _slot(3, gk2, zg, b, e, f),
        ]
        # swap CB(a) in slot 1 with CB(zg) in slot 3
        assert _all_mid_quarter_limits_ok(slots, 1, 3, Position.CB, a, Position.CB, zg) is False

    def test_partner_index_out_of_range_is_skipped(self):
        # 3 slots; swapping slot 2 (even) makes its partner index 3 == len(slots).
        # The strict "partner < len(slots)" must skip it; the "<=" mutant would
        # index slots[3] and raise IndexError.
        a, b, c, d = (make_player(n) for n in "abcd")
        e, f, g, h = (make_player(n) for n in "efgh")
        gk1, gk2 = make_player("gk1"), make_player("gk2")
        slots = [
            _slot(0, gk1, a, b, c, d),
            _slot(1, gk1, a, b, c, d),
            _slot(2, gk2, e, f, g, h),
        ]
        # swap CB(e) in slot 2 with CB(a) in slot 0 -> only pair (0,1) is in range
        assert _all_mid_quarter_limits_ok(slots, 2, 0, Position.CB, e, Position.CB, a) is True


# ---------------------------------------------------------------------------
# _try_best_swap
# ---------------------------------------------------------------------------

class TestTryBestSwap:
    def _polarised(self, lock0=False, lock2=False):
        highs = [make_player(f"H{i}", skill_rating=5) for i in range(4)]
        lows = [make_player(f"L{i}", skill_rating=1) for i in range(4)]
        gk1, gk2 = make_player("gk1"), make_player("gk2")
        slots = [
            _slot(0, gk1, *highs, locked=lock0),
            _slot(1, gk1, *highs),
            _slot(2, gk2, *lows, locked=lock2),
            _slot(3, gk2, *lows),
        ]
        return slots

    def test_applies_variance_reducing_swap(self):
        slots = self._polarised()
        before = slots[0].outfield_skill_total  # 20
        assert _try_best_swap(slots, 0, 2) is True
        assert slots[0].outfield_skill_total < before  # a high moved out

    def test_locked_slot_i_blocks_swap(self):
        slots = self._polarised(lock0=True)
        before = slots[0].outfield_skill_total
        assert _try_best_swap(slots, 0, 2) is False
        assert slots[0].outfield_skill_total == before

    def test_locked_slot_j_blocks_swap(self):
        slots = self._polarised(lock2=True)
        assert _try_best_swap(slots, 0, 2) is False

    def test_no_improving_swap_returns_false(self):
        # both slots already equal skill totals -> no variance to shave
        p = [make_player(f"P{i}", skill_rating=3) for i in range(4)]
        q = [make_player(f"Q{i}", skill_rating=3) for i in range(4)]
        gk1, gk2 = make_player("gk1"), make_player("gk2")
        slots = [
            _slot(0, gk1, *p), _slot(1, gk1, *p),
            _slot(2, gk2, *q), _slot(3, gk2, *q),
        ]
        assert _try_best_swap(slots, 0, 2) is False

    def test_skips_invalid_pair_and_still_finds_valid_swap(self):
        # First product pair (CB restricted-high <-> CB low) is INVALID (moving a
        # DEF-restricted player into DEF). The engine must `continue`, not `break`
        # — a valid improving swap (a MID high <-> low) comes later.
        restricted = make_player("R", def_restricted=True, skill_rating=5)
        highs = [restricted] + [make_player(f"H{i}", skill_rating=5) for i in range(3)]
        lows = [make_player(f"L{i}", skill_rating=1) for i in range(4)]
        gk1, gk2 = make_player("gk1"), make_player("gk2")
        slots = [
            _slot(0, gk1, *highs), _slot(1, gk1, *highs),
            _slot(2, gk2, *lows), _slot(3, gk2, *lows),
        ]
        assert _try_best_swap(slots, 0, 2) is True

    def test_skips_same_player_pair_and_still_finds_valid_swap(self):
        # A shared player X (CB in both slots) makes the first product pair a
        # no-op (player_i is player_j). The engine must `continue`, not `break`.
        shared = make_player("X", skill_rating=3)
        h = [make_player(f"H{i}", skill_rating=5) for i in range(3)]
        low = [make_player(f"L{i}", skill_rating=1) for i in range(3)]
        gk1, gk2 = make_player("gk1"), make_player("gk2")
        slots = [
            _slot(0, gk1, shared, *h), _slot(1, gk1, shared, *h),
            _slot(2, gk2, shared, *low), _slot(3, gk2, shared, *low),
        ]
        assert _try_best_swap(slots, 0, 2) is True


# ---------------------------------------------------------------------------
# balance_skills (end-to-end on crafted plans)
# ---------------------------------------------------------------------------

class TestBalanceSkills:
    def test_reduces_variance_on_polarised_plan(self):
        highs = [make_player(f"H{i}", skill_rating=5) for i in range(4)]
        lows = [make_player(f"L{i}", skill_rating=1) for i in range(4)]
        gk1, gk2 = make_player("gk1"), make_player("gk2")
        slots = [
            _slot(0, gk1, *highs), _slot(1, gk1, *highs),
            _slot(2, gk2, *lows), _slot(3, gk2, *lows),
        ]
        before = _skill_variance(slots)
        result = balance_skills(RotationPlan(slots=slots))
        after = _skill_variance(result.slots)
        assert after < before

    def test_already_balanced_plan_left_untouched(self):
        # distinct players, equal skill everywhere: variance is 0, every swap has
        # delta 0. The strict "delta > best_delta" must leave the plan unchanged.
        p = [make_player(f"P{i}", skill_rating=3) for i in range(4)]
        q = [make_player(f"Q{i}", skill_rating=3) for i in range(4)]
        gk1, gk2 = make_player("gk1"), make_player("gk2")
        slots = [
            _slot(0, gk1, *p), _slot(1, gk1, *p),
            _slot(2, gk2, *q), _slot(3, gk2, *q),
        ]
        original = [dict(s.lineup) for s in slots]
        result = balance_skills(RotationPlan(slots=slots))
        assert [dict(s.lineup) for s in result.slots] == original
