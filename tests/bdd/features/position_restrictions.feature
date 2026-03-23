Feature: Position restrictions

  Scenario: DEF-restricted player never plays defence
    Given a squad of 9 players where 2 players are DEF-restricted
    When the system generates a rotation plan
    Then no DEF-restricted player should appear in the DEF position in any slot

  Scenario: Player plays at most 2 different positions
    Given a squad of 9 players with no GK specialist
    When the system generates a rotation plan
    Then no player should appear in more than 2 different positions across all slots
