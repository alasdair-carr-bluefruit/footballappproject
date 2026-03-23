# Team Selection Tool
**Project:** Football (Soccer) Squad Rotation Manager
**Owner:** Personal project — coach use only (initially)
**Tech Stack:** Python backend, web app frontend (browser-accessible on mobile)
**Development Approach:** TDD with pytest + BDD with pytest-bdd (Gherkin scenarios)

---

## 1. Problem Statement

A youth football coach needs to manage fair and balanced playing time across a squad during a match, whilst:
- Ensuring all children play equal (or near-equal) time
- Respecting player GK capability tiers and position restrictions
- Maintaining a competitively balanced outfield team across the match
- Giving players experience across a range of positions over time

---

## 2. Match Structure

- A match consists of **4 quarters**, each approximately **10 minutes**
- Each quarter is divided into **2 half-quarters (~5 minutes each)**
- Substitutions may occur at **half-quarter intervals** or at **full quarter breaks**
- **At a mid-quarter (5 min) sub point:** up to 2 players may be substituted
- **At a full quarter break:** up to 5 players may be substituted (full swap is fine, partial is also fine)
- A goalkeeper is **never substituted mid-quarter** — GK changes only at full quarter breaks
- Total time slots per match: **8 half-quarters × 5 players = 40 player-slots**
- Playing time equality is measured by total half-quarter slots assigned, regardless of position. GK slots count as playing time. When extra slots must be allocated because exact equality is impossible, priority is given first to players who covered non-specialist GK slots in that match.
- Where exact equality is not possible, the difference between the most-played and least-played available player must be no more than 1 half-quarter slot, unless unavoidable due to hard GK constraints.


### Equal Time Calculation
| Players available | Outfield players | Half-quarters each | Notes |
|---|---|---|---|
| 10 (inc. specialist) | 9 outfield | 4 each | All 10 players get exactly 4 half-quarter slots. Specialist's 4 slots are all GK. Remaining 4 GK slots filled by preferred/can_play players — counts toward their playing time. 32 outfield slots shared across 9 players minus however many GK slots they cover |
| 9 (inc. specialist) | 8 | 4 | 32 outfield slots ÷ 8 = exactly 4 each |
| 9 (no specialist) | 9 | ~4–5 | 40 slots ÷ 9 — distribute remainder fairly |
| 8 (inc. specialist) | 7 | ~4–5 | 28 outfield slots ÷ 7 = 4 each |

- Where perfect equal time is not possible, extra half-quarter slots are distributed using this priority:
  1. **Players who covered a non-specialist GK slot** in that match are rewarded with an extra half-quarter first
  2. **Remaining players** share any further extra slots in rotation

---

## 3. Positions & Formation

### 3.1 Default Formation
**1-2-1**: 1 DEF, 2 MID, 1 FWD (configurable in future versions)

### 3.2 Position Types
| Code | Position |
|---|---|
| GK | Goalkeeper |
| DEF | Defender |
| MID | Midfielder |
| FWD | Forward |

### 3.3 Position Rules
- Each lineup must include exactly **1 GK** and **4 outfield players** in 1-2-1 formation
- A player flagged as **DEF-restricted** must never be assigned to DEF
- Each player should play **no more than 2 different positions** in a single match
- Position variety across a match is a **nice-to-have**, not a hard requirement
- The system should **not** prefer keeping a player in one position for a continuous block
- Position variety across **multiple matches** is the primary tracking goal

---

## 4. Player Model

Each player has the following attributes:

| Attribute | Type | Description |
|---|---|---|
| name | string | Player's name |
| gk_status | enum | See GK tier table below |
| def_restricted | boolean | Must not be assigned to DEF |
| skill_rating | integer (1–5) | Coach-only — entered at setup, never displayed again |
| position_history | dict | Tracks half-quarter slots played per position, per match and cumulative |
| minutes_played | integer | Cumulative playing time across matches |

### 4.1 GK Status Tiers
| Tier | Value | Meaning | Behaviour |
|---|---|---|---|
| 1 | `specialist` | Plays GK only — never plays outfield | Plays GK only - never plays outfield. Game time depends on squad size|
| 2 | `preferred` | Good in goal — happy to use here | First choice for GK when specialist is absent |
| 3 | `can_play` | Capable if needed | Used when tiers 1 & 2 unavailable or need rest |
| 4 | `emergency_only` | Shouldn't play GK unless no alternative | System assigns only as last resort and flags to coach |

**When the specialist is present with a full squad of 10:** specialist plays 2 full quarters in goal (4 half-quarter slots) and sits on the bench for the remaining 4 slots. He never plays outfield under any circumstances. The remaining GK slots are filled by tier 2/3/4 players.

**When the squad has fewer than 10 players:** the specialist plays the full match in goal, freeing all outfield slots for the other players to share equally.

**GK assignment priority when specialist is absent:**
1. Preferred (`preferred`) players first
2. Then `can_play` players
3. Then `emergency_only` — system flags this to the coach

---

## 5. Team Balance

- Skill ratings apply to **outfield players only** — GK slot is neutral and excluded from balance calculations
- Each half-quarter lineup's outfield skill total should be as balanced as possible across the match.
- This is a **soft preference** — the algorithm should optimise for it but not reject solutions that can't perfectly achieve it
- Skill ratings are **coach-only** — entered once at player setup and never displayed in the UI again

---

## 6. Functional Requirements

### 6.1 Squad Management
- FR-01: Coach can add a player with name, GK status, DEF restriction flag, and skill rating
- FR-02: Coach can edit player attributes at any time
- FR-03: Skill rating is entered once at setup and not shown again in any view
- FR-04: Coach can mark a player as absent for a specific match
- FR-05: System handles squads of 6–12 players

### 6.2 Match Setup
- FR-06: Coach creates a new match (date, optional opponent name)
- FR-07: Coach confirms which players are available for that match
- FR-08: Coach can configure number of quarters (default: 4) and quarter length (default: 10 mins)

### 6.3 Rotation Planning
- FR-09: System generates a full rotation plan (all 8 half-quarter slots) before the match starts
- FR-10: Each available player receives equal or near-equal playing time
- FR-11: GK slot is filled according to the tier priority order
- FR-12: GK specialist only ever plays in the GK position (plays full match if squad < 10, or half the match if squad = 10)
- FR-13: DEF-restricted players are never assigned to DEF
- FR-14: Each player plays no more than 2 different positions in a single match
- FR-15: Outfield skill ratings are balanced across quarters (soft preference)
- FR-16: At most 2 players are substituted at any mid-quarter point
- FR-17: GK changes only occur at full quarter breaks, never mid-quarter
- FR-18: Coach can view and approve the rotation plan before the match
- FR-19: Coach can regenerate the plan if unhappy
- FR-20: Coach can manually override an individual assignment (with a warning if it breaks a rule)

### 6.4 Match Day View
- FR-21: Coach sees the current lineup clearly on a mobile screen
- FR-22: View shows: who is on, who is off, each player's current position
- FR-23: Coach advances to the next half-quarter slot manually (single tap)
- FR-24: Current lineup is displayed as player positions on a visual pitch graphic
- FR-25: Incoming substitutes are visually indicated on the pitch — showing which player they will replace
- FR-26: The pitch view is clear enough to show players directly (e.g. gathered around the coach's phone before a quarter)

### 6.5 History & Development Tracking
- FR-27: System records each player's position history per match and cumulatively
- FR-28: System records total minutes played per player
- FR-29: Coach can view a per-player summary: positions played, minutes, matches attended

---

## 7. Non-Functional Requirements

- NFR-01: Runs in a modern mobile browser — no app install required
- NFR-02: Works with minimal or no connectivity (coach is on a pitch) App must be built as a Progressive Web App (PWA) with a Service Worker so it continues to function seamlessly offline on the pitch.
- NFR-03: Large, clear UI
- NFR-04: Data persists between sessions (local storage or lightweight database)
- NFR-05: No login required for single-user v1

---

## 8. Out of Scope (v1)

- Multi-coach / shared access
- No countdown timer or auto-advance — coach controls all progression manually
- Tactical formation drawing
- Player performance input during a match
- 'Tactics board' drawing tools (dashed/solid lines), moveable player tiles

---

## 9. BDD Acceptance Scenarios

```gherkin
Feature: Equal playing time

  Scenario: All 10 players available, 4 quarters
    Given a squad of 10 available players with a GK specialist
    When the system generates a rotation plan for 4 quarters
    Then each player should appear in exactly 4 half-quarter slots
    And the GK specialist's 4 slots must all be in the GK position

  Scenario: 9 players including GK specialist
    Given a squad of 9 players including 1 GK specialist
    When the system generates a rotation plan for 4 quarters
    Then the specialist should appear in all 8 GK slots
    And each of the other 8 players should appear in exactly 4 slots
    And each of those slots should be outfield slots

Feature: GK assignment priority

  Scenario: Specialist present reduced squad
    Given a squad of 9 or fewer players including a GK specialist
    When the system generates a rotation plan
    Then the specialist fills the GK slot in every quarter
    And no other player is assigned GK

  Scenario: Specialist absent, preferred keeper available
    Given a squad with no specialist but with a preferred GK player
    When the system generates a rotation plan
    Then the preferred GK player should fill GK slots before can_play or emergency_only players

  Scenario: Only emergency_only GK available
    Given a squad where the only available GK-capable players are emergency_only
    When the system generates a rotation plan
    Then an emergency_only player is assigned GK
    And the coach is shown a warning

Feature: Position restrictions

  Scenario: DEF-restricted player never plays defence
    Given a player with def_restricted = true
    When the system generates a rotation plan
    Then that player must not appear in the DEF position in any slot

Feature: Substitution rules

  Scenario: Mid-quarter substitution limit
    Given a generated rotation plan
    When comparing any two consecutive half-quarter slots within the same quarter
    Then no more than 2 players should differ between the two lineups

  Scenario: GK not substituted mid-quarter
    Given a generated rotation plan
    When comparing the two half-quarter slots within any single quarter
    Then the GK must be the same player in both half-quarter slots

Feature: Team balance

  Scenario: Outfield skill ratings are roughly balanced across quarters
    Given players with varying skill ratings
    When the system generates a rotation plan
    Then the total outfield skill rating for each quarter should be as equal as possible
    And the GK slot skill rating is excluded from this calculation
```

---

## 10. Suggested Development Phases

| Phase | Scope |
|---|---|
| **v0.1** | Core rotation algorithm (Python only, no UI) — 10 players, full quarters only, GK tiers, DEF restriction |
| **v0.2** | Half-quarter substitution support — mid-quarter subs, 2-player limit, GK lock |
| **v0.3** | Skill balancing across quarters (soft preference) |
| **v0.4** | Simple web UI — pitch visualisation with player positions and incoming subs highlighted |
| **v0.5** | Player history and position tracking |
| **v0.6** | Manual override with rule validation warnings |
| **v1.0** | Persistent storage, stable for real match use |
