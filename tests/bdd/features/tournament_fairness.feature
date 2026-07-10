Feature: Tournament cross-match fairness — consecutive sit-out constraint

  Scenario: A player benched for an entire tournament match must play in the next match
    Given a 12-player squad and a short single-period tournament match
    When the system generates the first match's rotation plan
    And the system generates the second match's rotation plan for players benched entirely in the first match
    Then no player benched entirely in the first match should sit out the second match too

  Scenario: The validator flags a consecutive sit-out violation
    Given a 12-player squad and a short single-period tournament match
    And a player who sat out the entire previous tournament match
    When that player is forced to zero slots in the current rotation plan
    Then the validator should report a consecutive sit-out violation
