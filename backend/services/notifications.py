"""Plan notifications between the coaches of one team (email, via Resend).

Recipients are resolved here, inside the request; the send itself is queued as a
background task so a slow mail API never delays the coach. Every send is best-effort
and honours the recipient's `notify_plans` setting.
"""
from __future__ import annotations

from fastapi import BackgroundTasks
from sqlmodel import Session

from backend.auth import email
from backend.db.memberships import head_account
from backend.db.models import AccountDB, SquadDB
from backend.settings import app_base_url


def _team(squad: SquadDB) -> str:
    return squad.team_name or "your team"


def _queue(
    background: BackgroundTasks, to: AccountDB | None, *, subject: str, heading: str,
    paragraphs: list[str],
) -> None:
    if to is None or not to.notify_plans or to.status != "active" or not to.email:
        return
    background.add_task(
        email.send_notice, to.email, subject=subject, heading=heading,
        paragraphs=paragraphs, cta_label="Open Level", link=app_base_url(),
    )


def assistant_made_plan(
    background: BackgroundTasks, session: Session, squad: SquadDB,
    author: AccountDB | None, *, what: str,
) -> None:
    """Tell the head coach an assistant made a plan. `what` e.g. "vs Rovers on 15 Nov"."""
    if author is None or squad.id is None:
        return
    head = head_account(session, squad.id)
    if head is None or head.id == author.id:
        return
    name = author.display_name or "An assistant coach"
    _queue(
        background, head,
        subject=f"{name} made a plan for {_team(squad)}",
        heading="A new plan is ready to look at",
        paragraphs=[
            f"{name} has made a plan for {_team(squad)} {what}.",
            "You can open it, tinker with it and mark it as reviewed. It is already live "
            "— nothing is waiting on you.",
        ],
    )


def plan_handed_over(
    background: BackgroundTasks, squad: SquadDB, head: AccountDB | None,
    new_owner: AccountDB | None, *, what: str,
) -> None:
    """Tell an assistant the head coach has handed them a plan to do."""
    if new_owner is None or (head is not None and head.id == new_owner.id):
        return
    name = (head.display_name if head else "") or "Your head coach"
    _queue(
        background, new_owner,
        subject=f"{name} asked you to do a plan for {_team(squad)}",
        heading="A plan has been handed to you",
        paragraphs=[
            f"{name} has asked you to do the plan for {_team(squad)} {what}.",
            "You can now set it up, tinker with it and run the match from it.",
        ],
    )


def team_handed_over(
    background: BackgroundTasks, squad: SquadDB, old_head: AccountDB | None,
    new_head: AccountDB | None,
) -> None:
    """Tell an assistant they're now the team's head coach."""
    if new_head is None or (old_head is not None and old_head.id == new_head.id):
        return
    name = (old_head.display_name if old_head else "") or "The head coach"
    _queue(
        background, new_head,
        subject=f"You're now head coach of {_team(squad)}",
        heading="You're the head coach now",
        paragraphs=[
            f"{name} has made you head coach of {_team(squad)}.",
            "You can now manage the squad, change any plan and invite assistant coaches. "
            f"{name} stays on as an assistant.",
        ],
    )
