Feature: Team balance

  Scenario: Outfield skill ratings are roughly balanced across slots
    Given players with varying skill ratings
    When the system generates a rotation plan
    Then the total outfield skill rating variance across slots should be minimal
    And the GK slot skill rating is excluded from this calculation
