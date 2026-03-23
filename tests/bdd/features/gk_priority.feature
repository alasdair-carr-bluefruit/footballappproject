Feature: GK assignment priority

  Scenario: Specialist present with reduced squad
    Given a squad of 8 players including a GK specialist
    When the system generates a rotation plan
    Then the specialist fills the GK slot in every half-quarter
    And no other player is assigned GK

  Scenario: Specialist absent, preferred keeper available
    Given a squad of 9 players with no specialist but with a preferred GK player
    When the system generates a rotation plan
    Then the preferred GK player should fill at least one GK slot
    And no emergency_only player should fill a GK slot

  Scenario: Only emergency_only GK available
    Given a squad where the only available GK-capable players are emergency_only
    When the system generates a rotation plan
    Then an emergency_only player is assigned GK
    And the plan includes a warning about emergency GK usage
