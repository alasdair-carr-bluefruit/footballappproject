Feature: Substitution rules

  Scenario: Mid-quarter substitution limit
    Given a generated rotation plan for 10 players
    When comparing any two consecutive half-quarter slots within the same quarter
    Then no more than 2 players should differ between the two lineups

  Scenario: GK not substituted mid-quarter
    Given a generated rotation plan for 10 players
    When comparing the two half-quarter slots within any single quarter
    Then the GK must be the same player in both half-quarter slots of that quarter
