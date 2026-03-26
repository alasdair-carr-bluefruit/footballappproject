"""Shared fixtures for all tests."""

from datetime import date

import pytest

from backend.models.match import Match, Squad
from backend.models.player import GKTier, Player


def make_player(
    name: str,
    gk_status: GKTier = GKTier.EMERGENCY_ONLY,
    def_restricted: bool = False,
    skill_rating: int = 3,
) -> Player:
    return Player(
        name=name,
        gk_status=gk_status,
        def_restricted=def_restricted,
        skill_rating=skill_rating,
    )


@pytest.fixture
def standard_match() -> Match:
    return Match(date=date(2026, 3, 23), opponent="Test FC")


@pytest.fixture
def squad_10_with_specialist() -> Squad:
    """10 players: 1 specialist GK + 9 outfield."""
    players = [
        make_player("Alice", GKTier.SPECIALIST),
        make_player("Bob", GKTier.PREFERRED, skill_rating=4),
        make_player("Charlie", skill_rating=3),
        make_player("Diana", skill_rating=5),
        make_player("Eve", skill_rating=2),
        make_player("Frank", skill_rating=4),
        make_player("Grace", skill_rating=3),
        make_player("Harry", skill_rating=2),
        make_player("Iris", skill_rating=3),
        make_player("Jack", skill_rating=4),
    ]
    return Squad(players=players)


@pytest.fixture
def squad_9_with_specialist() -> Squad:
    """9 players: 1 specialist GK + 8 outfield."""
    players = [
        make_player("Alice", GKTier.SPECIALIST),
        make_player("Bob", GKTier.PREFERRED, skill_rating=4),
        make_player("Charlie", skill_rating=3),
        make_player("Diana", skill_rating=5),
        make_player("Eve", skill_rating=2),
        make_player("Frank", skill_rating=4),
        make_player("Grace", skill_rating=3),
        make_player("Harry", skill_rating=2),
        make_player("Iris", skill_rating=3),
    ]
    return Squad(players=players)


@pytest.fixture
def squad_9_no_specialist() -> Squad:
    """9 players: no specialist, 1 preferred GK."""
    players = [
        make_player("Bob", GKTier.PREFERRED, skill_rating=4),
        make_player("Charlie", skill_rating=3),
        make_player("Diana", skill_rating=5),
        make_player("Eve", skill_rating=2),
        make_player("Frank", skill_rating=4),
        make_player("Grace", skill_rating=3),
        make_player("Harry", skill_rating=2),
        make_player("Iris", skill_rating=3),
        make_player("Jack", skill_rating=4),
    ]
    return Squad(players=players)
