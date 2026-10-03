# L1 — Edit and publish

Everything that happens after filming: the running order, on-screen text,
blurs, chapters, and the YouTube description. Clips are from `L1-shoot.md`,
voiceover blocks from `L1-voiceover.md`.

## Running order

| # | Footage | Voiceover | On-screen text |
|---|---|---|---|
| 1 | Clip 16 — finished squad | 0 · Cold open | `Set up in 6 minutes` |
| 2 | Sting (see `intro-outro.md`) | — | `LEVEL · PART 1 OF 4` / `Getting started` |
| 3 | Clips 1–2 — website, about page *(or you to camera)* | 1 · Who I am | `Free · in beta` |
| 4 | Clip 3 — early-access form | 2 · Getting an invite | `Two ways in: request access, or a coach invites you` |
| 5 | Title card on Studio Green | — | `A day or so later…` (2s) |
| 6 | Clip 4 — invite email | 3 · The invite email | — |
| 7 | Clip 5 — Create your team | 4 · Create your team | `Invite links: one use, one coach, and they expire` |
| 8 | Clip 6 — Welcome screen | 5 · Team name and badge | `Your badge goes on the team sheet and the result card` |
| 9 | Clip 7 — sign out / back in | 6 · Signing in next time | `You must tap "Sign in to Level" — the link alone won't do it` **(hold 4s)** · `Opened in WhatsApp/Outlook? Use "Copy link" → paste into Safari or Chrome` |
| 10 | Clip 8 — Roy, slowly; **cut to clip 17 (laptop) for the laptop tip in 7a** | 7a–7d | `GK ticked on its own = never plays outfield` · `DEF unticked = hard rule. Other picks = best-effort` · `Skill rating is private — it's for balancing, not ranking` |
| 11 | Clips 9–10 — Thierry, then **sped up** | 8 | — |
| 12 | Clip 11 — second Sam | 9 | `Two players, same name? Add an initial: Sam → Sam B` |
| 13 | Clip 12 — squad list, delete confirm | 10 | `Deleting a player deletes their goals and match history` |
| 14 | Clip 13 — team switcher | 11 | `Tap your team name to switch or add a team` |
| 15 | Clip 14 — assistant coach, then Invite a friend | 12 | `Assistants: view plans, reports & stats — can't change anything` · `They never see skill ratings` · `Know a coach who'd use it? Settings → Invite a friend` |
| 16 | Clip 15 — Report a bug, home | 13 · Wrap | `Ideas? hello@keepthingslevel.com — or comment below` |
| 17 | End card | — | `Next: planning your first match` |

If a voiceover block runs longer than its footage, slow the footage or hold
the last frame. Don't speed up the voice.

## 🔴 Blur / check before publishing

- [ ] The **demo email address**: early-access form (clip 3), Gmail (clips 4, 7),
      Create your team (clip 5), Coach sign-in (clip 7)
- [ ] The **URL bar** in clips 4, 5 and 7: it shows a live `?invite=` /
      `?login=` token. Blur it, and check frame by frame.
- [ ] The **assistant invite link** in clip 14
- [ ] No real children's names anywhere

## After publishing

- [ ] Delete the demo early-access request from your list
- [ ] Once L1–L4 are filmed, suspend the demo account
      (`POST /admin/accounts/{id}/suspend`; `/reactivate` brings it back)

---

## End card

Last 15 seconds: the sting reversed, or the logo held, with
`keepthingslevel.com` and `Ideas? hello@keepthingslevel.com`. Leave the left
half clear for YouTube's end-screen boxes. Link Part 2. See `intro-outro.md`.

## Publishing

**Title:** `Getting started with Level — set up your grassroots football squad in 6 minutes`

**Chapters** (rough; set them from the final cut. The first must be `0:00`):
```
0:00 What we're doing
0:20 Who I am
0:35 Getting an invite
1:00 Creating your account
1:30 Team name and badge
2:05 Signing in (the bit people miss)
2:55 Adding your squad
5:00 More than one team, and your assistant
5:50 What's next
```

**Description:**
```
New to Level? This takes you from the website to a fully set-up squad in about
six minutes — including the sign-in gotcha that catches everybody out.

Level is a free rotation planner for grassroots youth football coaches — fair
playing time, sorted before you get to the pitch. Works on your phone or in any
browser on a laptop.
👉 keepthingslevel.com

Chapters:
<paste above>

Level is invite-only during the beta — request access at keepthingslevel.com.

It's in beta, so your feedback really does shape what gets built next.
Something you wish it did? Email hello@keepthingslevel.com or comment below.

Know another coach who'd find it useful? Invite them from Settings → Invite a friend.
```

**Thumbnail:** the squad list on a phone, held at a pitch side, with two words
in Signal Lime: **START HERE**.
