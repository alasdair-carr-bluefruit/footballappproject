
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class SquadDB(SQLModel, table=True):
    __tablename__ = "squads"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    # Owner account (multi-team). Nullable so the auth-off dev default squad and
    # any legacy row stay valid; backfilled from AccountDB.squad_id by migration.
    # Plain indexed column (no DB-level FK) — avoids an accounts↔squads create/drop
    # cycle and matches the TournamentDB.squad_id convention.
    account_id: int | None = Field(default=None, index=True)
    name: str = "My Squad"
    team_name: str = ""
    team_logo: str = ""  # base64 DataURL or empty string


# ── Multi-user identity (v1.1) ──────────────────────────────────────────────────
# An AccountDB row is the identity; a squad belongs to exactly one account (the
# link lives here, not on SquadDB, so multi-squad-per-account later is additive).
# Auth is magic-link only: no passwords/PINs are ever stored. See V1_MULTIUSER_PLAN.md.
class AccountDB(SQLModel, table=True):
    __tablename__ = "accounts"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    squad_id: int = Field(foreign_key="squads.id")  # the account's ACTIVE squad (may own several)
    email: str = Field(index=True, unique=True)  # the login handle (magic-link target)
    display_name: str = ""  # coach's name, shown in the UI
    status: str = "invited"  # "invited" | "active" | "disabled"
    created_at: str = ""  # ISO datetime
    last_login_at: str | None = None
    seen_tutorial: int = 0  # server-side onboarding flag (follows the coach across devices)
    session_epoch: int = 0  # bump to invalidate all issued sessions ("sign out everywhere")


# A one-time invite token — only coaches sent a /join?token=… link can create a
# team (invite-only onboarding). We store only the hash of the raw token.
class InviteDB(SQLModel, table=True):
    __tablename__ = "invites"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    token_hash: str = Field(index=True)  # sha256 of the raw token; raw is never stored
    account_id: int | None = None  # set once redeemed
    created_at: str = ""
    expires_at: str = ""  # ISO datetime, e.g. +14 days
    redeemed_at: str | None = None
    note: str = ""  # free text, e.g. "Dave – U10s"


# A one-time magic-link login token — hashed, short-lived, single-use. Same shape
# as InviteDB but scoped to an existing account (returning-device login).
class LoginTokenDB(SQLModel, table=True):
    __tablename__ = "login_tokens"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    token_hash: str = Field(index=True)  # sha256 of the raw token
    created_at: str = ""
    expires_at: str = ""  # ISO datetime, ~15-min expiry
    consumed_at: str | None = None


# A one-time token that confirms an email-address change. Emailed to the NEW
# address (proving the coach controls that inbox) — only when confirmed do we
# swap AccountDB.email, so a change can't silently hijack the login handle.
class EmailChangeTokenDB(SQLModel, table=True):
    __tablename__ = "email_change_tokens"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    new_email: str  # the address to switch to once confirmed
    token_hash: str = Field(index=True)  # sha256 of the raw token
    created_at: str = ""
    expires_at: str = ""  # ISO datetime, ~15-min expiry
    consumed_at: str | None = None


# A one-time "reclaim your squad" token, emailed to the OLD address whenever an
# account's email is changed. Clicking it reverts the email and bumps the account's
# session_epoch (signing out every device) — the recovery path if a change wasn't
# the owner. Longer-lived than a login token: the owner may not read mail promptly.
class ReclaimTokenDB(SQLModel, table=True):
    __tablename__ = "reclaim_tokens"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    prior_email: str  # the address to restore on reclaim
    token_hash: str = Field(index=True)  # sha256 of the raw token
    created_at: str = ""
    expires_at: str = ""  # ISO datetime, ~7-day expiry
    consumed_at: str | None = None


class TournamentDB(SQLModel, table=True):
    __tablename__ = "tournaments"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    squad_id: int  # FK to squads.id (not enforced at DB level to keep migrations simple)
    name: str = "Tournament"
    date: str  # ISO date string e.g. "2026-04-12"
    team_size: int = 5
    formation: str = "1-2-1"
    match_duration_mins: int = 10  # total match duration (one period if no halftime)
    has_halftime: int = 0  # 0=False, 1=True (SQLite has no native bool)
    max_subs: int | None = None  # coach-set mid-period sub cap; None = per-size preset default
    show_timer: int = 1  # 0=hide the match clock, 1=show (applied to this tournament's matches)
    fairness_value: int = 50  # 0=equal time, 100=start strong
    rotation_intensity: int = 50
    share_gk: int = 1  # 1=specialist keeper rotates for equal time, 0=in goal all match
    status: str = "active"  # "active" | "completed"
    player_position_overrides_json: str = "{}"  # JSON dict: {player_id: [positions]} — tournament-scoped overrides


class PlayerDB(SQLModel, table=True):
    __tablename__ = "players"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    squad_id: int = Field(foreign_key="squads.id")
    name: str
    gk_status: str  # GKTier value: specialist | preferred | can_play | emergency_only
    def_restricted: bool = False
    skill_rating: int = 3
    preferred_positions: str = "[]"  # JSON list of position types e.g. '["DEF","MID"]'
    best_position: str = ""  # e.g. "DEF", "MID", "FWD", or "" for unset
    shirt_number: int | None = None  # optional squad number (1–99)
    source_tournament_id: int | None = None  # if set, guest player scoped to this tournament


class MatchDB(SQLModel, table=True):
    __tablename__ = "matches"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    squad_id: int = Field(foreign_key="squads.id")
    date: str  # ISO date string e.g. "2026-03-25"
    opponent: str = ""
    quarters: int = 4
    quarter_length_mins: float = 10  # minutes per period; float to allow e.g. 12.5
    team_size: int = 5
    formation: str = "1-2-1"
    show_timer: int = 1  # 0=hide the match clock, 1=show
    fairness: str = "equal"  # "equal" or "competitive"
    fairness_value: int = 0  # 0-100 slider raw value
    rotation_intensity: int = 50  # 0 = specialist, 100 = all-rounder
    share_gk: int = 1  # 1=specialist keeper rotates for equal time, 0=in goal all match
    max_subs: int | None = None  # tournament only: coach-set mid-period sub cap (None = preset default)
    home_away: str = "home"  # "home" or "away"
    opponent_goals: int = 0
    hide_score: int = 0  # 0=show scoreline, 1=mask as "X - X" (FA sub-U12 guidance)
    status: str = "planned"  # "planned" | "in_progress" | "completed"
    current_slot: int = 0  # furthest slot reached during live match
    tournament_id: int | None = None  # if set, this match belongs to a tournament
    tournament_stage: str = ""  # "group" or "knockout" (empty for season matches)
    match_number: int | None = None  # sequence within tournament (1-based)


class RotationPlanDB(SQLModel, table=True):
    __tablename__ = "rotation_plans"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    match_id: int = Field(foreign_key="matches.id", unique=True)
    slots_json: str  # JSON list of {slot_index, lineup: {pos: player_id}}
    warnings_json: str = "[]"
    goals_json: str = "{}"  # JSON dict: {player_id: goal_count}
    available_player_ids_json: str = "[]"  # JSON list of player IDs selected for this match
    removed_players_json: str = "{}"  # JSON dict: {player_id: from_slot_index}


# ── Relational rotation storage ─────────────────────────────────────────────────
#
# These normalise the RotationPlanDB JSON blobs (slots_json, goals_json,
# available_player_ids_json, removed_players_json) into proper tables. Keyed by
# match_id (matches RotationPlanDB's 1:1 relationship with a match). warnings_json
# stays on RotationPlanDB — it's plan metadata, not relational data.


class SlotDB(SQLModel, table=True):
    __tablename__ = "slots"  # type: ignore[assignment]
    __table_args__ = (UniqueConstraint("match_id", "slot_index", name="uq_slot_match_index"),)

    id: int | None = Field(default=None, primary_key=True)
    match_id: int = Field(foreign_key="matches.id", index=True)
    slot_index: int  # 0..N; a slot row exists even when its lineup is empty


class SlotAssignmentDB(SQLModel, table=True):
    __tablename__ = "slot_assignments"  # type: ignore[assignment]
    __table_args__ = (UniqueConstraint("slot_id", "position", name="uq_assignment_slot_position"),)

    id: int | None = Field(default=None, primary_key=True)
    slot_id: int = Field(foreign_key="slots.id", index=True)
    position: str  # position code e.g. "GK", "LB", "CM", "CF"
    player_id: int  # references players.id (not FK-enforced, matching existing convention)


class GoalRecordDB(SQLModel, table=True):
    __tablename__ = "goal_records"  # type: ignore[assignment]
    __table_args__ = (UniqueConstraint("match_id", "player_id", name="uq_goal_match_player"),)

    id: int | None = Field(default=None, primary_key=True)
    match_id: int = Field(foreign_key="matches.id", index=True)
    player_id: int
    goals: int = 0


class MatchAvailabilityDB(SQLModel, table=True):
    __tablename__ = "match_availability"  # type: ignore[assignment]
    __table_args__ = (UniqueConstraint("match_id", "player_id", name="uq_avail_match_player"),)

    id: int | None = Field(default=None, primary_key=True)
    match_id: int = Field(foreign_key="matches.id", index=True)
    player_id: int


class RemovedPlayerDB(SQLModel, table=True):
    __tablename__ = "removed_players"  # type: ignore[assignment]
    __table_args__ = (UniqueConstraint("match_id", "player_id", name="uq_removed_match_player"),)

    id: int | None = Field(default=None, primary_key=True)
    match_id: int = Field(foreign_key="matches.id", index=True)
    player_id: int
    from_slot: int


class FeedbackDB(SQLModel, table=True):
    __tablename__ = "feedback"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    created_at: str  # ISO datetime
    description: str
    context_json: str = "{}"  # JSON dict: screen, match id, user agent, etc.
    forwarded: bool = False  # True once successfully sent to GitHub
    issue_url: str = ""  # GitHub issue URL when forwarded
