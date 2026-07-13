# User Feedback — captured July 2026

> Canonical record of the July 2026 user feedback (verbatim content, reformatted
> so it is greppable and diffable). The original `.rtf` has been removed — this is
> now the single source. Each item is mapped to the roadmap in
> DEVELOPMENT_PLAN.md Part 1.4 / Part 3.

## Tinkering confusion → v0.9 + v1.1

Lots of confusion around how tinkering affects teams. If a plan is created and the
coach starts tinkering with it, they often get unexpected messages about other
players — who have not been subbed off or on — getting more, or fewer slots.

## Tournament: adding matches → v0.9

Some confusion was observed around adding extra matches to a tournament. They were
not expecting to have to add a team name before pressing the "add match" button.

## "Review the match plan" → v1.1

In regular season mode when a new match is created, a simplification would be a
"Review the match plan" button: a simplified view of how the team will line up in
each slot — perhaps 2 or even 4 slots displayed in a table format:

| | Slot 1 | Slot 2 |
|---|---|---|
| GK | Ali | Ali |
| DEF | Jago, Harris | Jago, *Jude* |
| MID | Kobe | *Eli* |
| ATT | Rowan | Rowan |

At this point the coach can choose to tinker. When they make a sub they could either
"recalculate" all the other slots, or just make changes and accept that some players
will have fewer minutes / some quarters will have a weaker team. Flag players who
have fewer slots. After the table view, show the stats — how many slots each player
will play.

After the coach has reviewed the plan (and potentially made changes) they should be
able to either "Start match" (pitch view) or return to the previous screen. Any
changes made to the plan must persist — perhaps a "Save changes" option on the
review-the-plan section.

## Tournament consecutive sit-outs → v0.9 (top priority)

In a tournament recently, the same child sat out two matches altogether — in a row.
This was unexpected. There should be a check that players don't have too long on the
sidelines consecutively. (Corroborated by `Issue1/` screenshots: 12 slots vs 3 slots
on a "mostly fair" setting.)

## Match timer → v0.9

When a match is live, a timer should be displayed. Configurable count-up (default)
or count-down. If match duration is set on the create-match/create-tournament screen,
that drives the countdown start — e.g. 12-minute tournament matches in 2 blocks →
countdown from 6 minutes. An audible alert or vibration on a mobile device when the
countdown is reached would be very nice.

## Season/tournament component parity → refactor phase

Any components used in creating matches / during match play should be the same (as
much as possible) in season and tournament mode — easier for coaches, and easier to
change in future. Automated tests should include a check on tournament and season
mode so discrepancies are picked up and logged.

## Bug reporting → v0.9

The "report bug" function requires a GitHub account. Users didn't understand what
that meant and were unable to report bugs directly.

## Fun: competitive slider messages → v0.9

If selecting the most competitive option on the slider, the warning message should be
light-hearted and different each time — perhaps 10 different messages. Think more
Ted Lasso and less Roy Kent. Seed examples:

- Careful, Sir Alex! It's grassroots, not a cup final.
- Even Klopp rotates his squad! Give the bench a run.
- Parking the bus? Make sure everyone gets on it first.
- Save the tactical masterclass; let's ensure everyone gets a game.
- Great team, but remember: no Ballon d'Ors at this level.
- Three points are nice, but so is equal playing time.
- Steady on Pep — this isn't the Champions League.
