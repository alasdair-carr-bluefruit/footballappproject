Feature: Multi-size rotation support

  Scenario: 7v7 rotation generates correct lineup size
    Given a squad of 12 players for 7v7 with formation 2-3-1
    When the system generates a rotation plan
    Then each slot should have exactly 7 players on pitch
    And the plan should have 8 slots

  Scenario: 9v9 rotation uses halves not quarters
    Given a squad of 14 players for 9v9 with formation 3-3-2
    When the system generates a rotation plan
    Then the plan should have 4 slots
    And each slot should have exactly 9 players on pitch

  Scenario: 7v7 respects mid-period sub limit of 3
    Given a squad of 12 players for 7v7 with formation 2-3-1
    When the system generates a rotation plan
    Then no more than 3 players should change at any mid-period transition

  Scenario: Competitive mode gives skilled players more time
    Given a squad of 10 players with varied skill ratings in competitive mode
    When the system generates a rotation plan
    Then the highest-skilled player should have more slots than the lowest-skilled player
