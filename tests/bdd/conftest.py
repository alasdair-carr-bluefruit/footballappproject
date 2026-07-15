"""BDD-specific fixtures."""

import random
from datetime import date

import pytest

from backend.models.match import Match, Squad
from backend.models.player import GKTier
from tests.conftest import make_player

# Seed RNG before every BDD scenario for the same reason as the unit suite
# (tests/unit/conftest.py): the rotation algorithm shuffles candidates, which made
# `test_players_with_no_specialist` flake ~10% when a draw hit the accepted
# over-budget fallback. Pinning the seed makes the scenarios a stable oracle.
_BDD_SEED = 1234


@pytest.fixture(autouse=True)
def _seed_rng():
    random.seed(_BDD_SEED)
    yield


@pytest.fixture
def bdd_match() -> Match:
    return Match(date=date(2026, 3, 23))


@pytest.fixture
def bdd_squad_10_specialist() -> Squad:
    return Squad(players=[
        make_player("Specialist", GKTier.SPECIALIST),
        make_player("Preferred", GKTier.PREFERRED, skill_rating=4),
        make_player("Player3", skill_rating=3),
        make_player("Player4", skill_rating=5),
        make_player("Player5", skill_rating=2),
        make_player("Player6", skill_rating=4),
        make_player("Player7", skill_rating=3),
        make_player("Player8", skill_rating=2),
        make_player("Player9", skill_rating=3),
        make_player("Player10", skill_rating=4),
    ])
