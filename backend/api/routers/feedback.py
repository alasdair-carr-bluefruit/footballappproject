"""In-app bug/feedback reports.

Every report is stored in the DB (audit trail). When a GITHUB_TOKEN env var is
configured, the report is also forwarded as a GitHub issue so it lands in the
normal triage flow; users never need a GitHub account.
"""
import json
import os
import urllib.request
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from backend.db.database import get_session
from backend.db.models import FeedbackDB

router = APIRouter()

DEFAULT_REPO = "alasdair-carr-bluefruit/footballappproject"


class FeedbackCreate(BaseModel):
    description: str = Field(min_length=3, max_length=5000)
    context: dict[str, Any] | None = None


def _create_github_issue(description: str, context: dict[str, Any]) -> str | None:
    """Create a GitHub issue for the report. Returns the issue URL, or None if
    no token is configured or the request fails (the DB row is the fallback)."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return None
    repo = os.environ.get("GITHUB_REPO", DEFAULT_REPO)

    first_line = description.strip().splitlines()[0][:60]
    context_lines = "\n".join(f"- **{k}**: {v}" for k, v in context.items())
    body_md = f"{description}\n\n---\n_Reported via the in-app form._\n{context_lines}"

    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=json.dumps(
            {"title": f"[Bug] {first_line}", "body": body_md, "labels": ["bug", "in-app"]}
        ).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("html_url")
    except Exception:
        return None


@router.post("/", status_code=201)
def submit_feedback(
    body: FeedbackCreate, session: Session = Depends(get_session)
) -> dict[str, Any]:
    context = body.context or {}
    issue_url = _create_github_issue(body.description, context)

    session.add(FeedbackDB(
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        description=body.description,
        context_json=json.dumps(context),
        forwarded=issue_url is not None,
        issue_url=issue_url or "",
    ))
    session.commit()

    return {"status": "reported" if issue_url else "stored", "issue_url": issue_url}


@router.get("/")
def list_feedback(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rows = session.exec(select(FeedbackDB)).all()
    return [
        {
            "id": r.id,
            "created_at": r.created_at,
            "description": r.description,
            "context": json.loads(r.context_json),
            "forwarded": r.forwarded,
            "issue_url": r.issue_url,
        }
        for r in sorted(rows, key=lambda r: r.created_at, reverse=True)
    ]
