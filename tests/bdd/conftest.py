"""BDD-specific fixtures."""

from datetime import date

import pytest

from backend.models.match import Match, Squad
from backend.models.player import GKTier
from tests.conftest import make_player


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
