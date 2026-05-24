Feature: Match lifecycle — start, progress, and player removal

  Scenario: Removed player does not appear in future slots
    Given a 10-player squad with a GK specialist
    And a rotation plan has been generated
    When player "Player2" is removed from slot 4 onward
    Then "Player2" should not appear in slots 4 through 7
    And "Player2" should still appear in slots 0 through 3

  Scenario: Reinstated player appears in slots from current position
    Given a 10-player squad with a GK specialist
    And a rotation plan has been generated
    And player "Player2" is removed from slot 4 onward
    When player "Player2" is reinstated from slot 4
    Then the plan is valid with all 10 players across all 8 slots

  Scenario: Removing a player still produces a valid rotation
    Given a 10-player squad with a GK specialist
    And a rotation plan has been generated
    When player "Player3" is removed from slot 0 onward
    Then slots 0 through 7 each have exactly 5 players on the pitch
    And no player appears more than once per slot

  Scenario: Locked slots are preserved when player is removed mid-match
    Given a 10-player squad with a GK specialist
    And a rotation plan has been generated
    When slots 0 through 3 are locked and "Player4" is removed from slot 4
    Then slots 0 through 3 are unchanged from the original plan
    And slots 4 through 7 do not contain "Player4"
