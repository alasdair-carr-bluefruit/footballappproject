Feature: Equal playing time

  Scenario: All 10 players available with a GK specialist
    Given a squad of 10 available players with a GK specialist
    When the system generates a rotation plan for 4 quarters
    Then each player should appear in exactly 4 half-quarter slots
    And the GK specialist's 4 slots must all be in the GK position

  Scenario: 9 players including GK specialist
    Given a squad of 9 players including 1 GK specialist
    When the system generates a rotation plan for 4 quarters
    Then the specialist should appear in all 8 GK slots
    And each of the other 8 players should appear in exactly 4 slots

  Scenario: 9 players with no specialist
    Given a squad of 9 players with no GK specialist
    When the system generates a rotation plan for 4 quarters
    Then no player should appear in more than 5 half-quarter slots
    And no player should appear in fewer than 4 half-quarter slots
