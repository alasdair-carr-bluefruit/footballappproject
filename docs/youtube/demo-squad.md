# Demo squad — "Richmond Greyhounds"

The squad to type in on camera for the L1–L4 tutorials. It's built for **5v5**
(1 keeper + 4 outfield). First names only, like most coaches use. Speed it up in
the edit.

**Your name (Create your team screen, and Settings):** `Ali`
**Team name:** `Richmond Greyhounds`
**Badge:** a simple homemade one, e.g. a greyhound silhouette or a big "R".

## The ten

Enter them in this order. The first two are the ones you add slowly in L1 BEAT 4,
and the last one is the duplicate-name demo.

| # | Name | Can Play | Best Position | Shirt | Skill | Why it's in the demo |
|---|---|---|---|---|---|---|
| 1 | Roy | DEF · MID | MID | 6 | 5 | The slow "full form" example in L1 4a–4c |
| 2 | Thierry | GK | GK | 1 | 3 | **GK on its own:** the dedicated keeper (L1 4d, Rotate keeper in L2) |
| 3 | Jamie | ATT | ATT | 9 | 5 | **Narrow on purpose:** ATT only, so L2 has something to flag |
| 4 | Sam | DEF · MID · ATT | DEF | 24 | 4 | |
| 5 | Dani | MID · ATT | ATT | 14 | 4 | No DEF, so it's a second example of the hard DEF rule |
| 6 | Isaac | GK · DEF · MID | DEF | 5 | 4 | **Backup keeper #1** |
| 7 | Jan | GK · DEF · MID | DEF | 21 | 3 | **Backup keeper #2** |
| 8 | Colin | DEF · MID · ATT | MID | 15 | 3 | |
| 9 | Richard | DEF · MID | DEF | 4 | 2 | |
| 10 | Sam → **Sam B** | GK · DEF · MID · ATT | MID | 3 | 2 | **Duplicate-name demo** (L1 4e), and **backup keeper #3** |

**Player 10:** type `Sam` first and save, so Level refuses it on camera. The
form stays open with a red line under the name; add ` B` and save. The script
(L1 4e) has the details.

Skill ratings are just there to give the balancer a spread. Nobody sees them,
and the team sheet only shows a total per period.

**What the squad covers:**
- 1 dedicated keeper and 3 outfielders who can also go in goal
- 9 of the 10 can play two or more positions. Jamie is the only narrow one, on purpose.
- 2 players with DEF unticked (Jamie, Dani), which shows the hard DEF rule
- 10 players is exactly 2× a 5v5 team, which matches the Cornwall league's match-day
  squad limit for mini-soccer

## For L2: who's away

Untick **Sam B** and **Richard**, leaving 8 available. I ran the real engine 200
times on that 8 (5v5, 1-2-1, Equal, All-rounder, Rotate keeper on). It nearly
always raises something worth narrating:

- Nearly every plan: a 2-slot game-time spread (most 6, fewest 4). Usually it's
  Thierry on 4, because Rotate keeper shares the gloves and a GK-only player
  can't make the time up outfield.
- ~60% of plans: *"Jamie plays MID … only picked ATT"*. With one ATT slot per
  period, Jamie has to drop into midfield to get equal time.
- Sometimes Roy pushed up to ATT for one slot

Every generate is different. Dry-run it and narrate whatever you actually get.

## Extras

- **L4 temporary (guest) player:** `Leo`, ATT · MID, best ATT, skill 4.
- **Duplicate-number pickup (L1):** give Leo or anyone **#9** for a moment to show
  the red duplicate badge, then change it back.
- **Fixtures (all fictional):** opponents `Westfield Juniors` (L2) and `Hillside
  Colts` (L3), tournament `Autumn Cup` (L4).
