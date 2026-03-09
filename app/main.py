from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "control_plane.db"
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

app = FastAPI(title="Devin Jira Control Plane")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")


SEED_ISSUES = [
    {
        "external_id": "FIN-101",
        "title": "Disable live Devin launch when DEVIN_API_KEY is missing",
        "description": "The UI currently allows users to attempt a live Devin launch even when DEVIN_API_KEY is not configured. Add inline guidance and disable the live execution action until configuration is valid.",
        "source": "Jira",
        "suggested_lane": "ready_for_devin",
        "acceptance": "Disable live action when key is missing; show helper text; no regression to import/scoping flow.",
        "labels": ["Devin", "ready-for-devin", "frontend"],
    },
    {
        "external_id": "FIN-102",
        "title": "Add filter chips for ticket lanes on the issues table",
        "description": "Engineers need a quick way to isolate tickets by lane after Devin scopes them. Add filter chips for Ready for Devin, Needs clarification, and Senior review.",
        "source": "Jira",
        "suggested_lane": "ready_for_devin",
        "acceptance": "Clickable chips; visible counts; clear reset behavior; simple styling.",
        "labels": ["Devin", "ready-for-devin", "ui"],
    },
    {
        "external_id": "FIN-103",
        "title": "Improve backlog import reliability",
        "description": "Users report that imports sometimes feel inconsistent. Make imports more reliable and easier to understand.",
        "source": "Jira",
        "suggested_lane": "needs_clarification",
        "acceptance": "Not yet defined.",
        "labels": ["Devin", "needs-clarification"],
    },
    {
        "external_id": "FIN-104",
        "title": "Make progress updates more useful for engineering leadership",
        "description": "Leadership wants better visibility into progress while Devin is working, but the target channel and desired format are still unclear.",
        "source": "Jira",
        "suggested_lane": "needs_clarification",
        "acceptance": "Not yet defined.",
        "labels": ["Devin", "needs-clarification"],
    },
    {
        "external_id": "FIN-105",
        "title": "Add approval roles before allowing live ticket execution",
        "description": "Before certain tickets can be launched to Devin, only approved engineering roles should be able to trigger live execution. This may impact permissions and compliance requirements.",
        "source": "Jira",
        "suggested_lane": "senior_review",
        "acceptance": "Role-based access model and policy requirements still need definition.",
        "labels": ["Devin", "senior-review", "security"],
    },
    {
        "external_id": "FIN-106",
        "title": "Support multi-repo routing for enterprise rollout",
        "description": "The system currently assumes one repo. Future rollout requires routing tickets across multiple repositories and services.",
        "source": "Jira",
        "suggested_lane": "senior_review",
        "acceptance": "Architecture and tenant separation design needed.",
        "labels": ["Devin", "senior-review", "architecture"],
    },
]

LANE_LABELS = {
    "ready_for_devin": "Ready for Devin",
    "needs_clarification": "Needs clarification",
    "senior_review": "Senior review",
}


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT UNIQUE,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                source TEXT NOT NULL,
                acceptance TEXT,
                labels_json TEXT NOT NULL,
                suggested_lane TEXT,
                scope_status TEXT DEFAULT 'not_scoped',
                devin_lane TEXT,
                confidence INTEGER,
                likely_files TEXT,
                risk_flags TEXT,
                missing_info TEXT,
                rationale TEXT,
                selected_for_fix INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_id INTEGER NOT NULL,
                session_type TEXT NOT NULL,
                launch_mode TEXT NOT NULL,
                session_ref TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT,
                pr_url TEXT,
                error_text TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(issue_id) REFERENCES issues(id)
            );
            """
        )


def seed_issues(conn: sqlite3.Connection | None = None) -> tuple[bool, str]:
    """Insert seed issues using INSERT OR REPLACE for idempotent upserts.

    If *conn* is provided the caller owns the transaction; otherwise a
    new connection is created.
    """
    def _do_seed(c: sqlite3.Connection) -> tuple[bool, str]:
        try:
            for issue in SEED_ISSUES:
                ts = now_iso()
                c.execute(
                    """
                    INSERT OR REPLACE INTO issues (
                        external_id, title, description, source, acceptance, labels_json,
                        suggested_lane, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        issue["external_id"],
                        issue["title"],
                        issue["description"],
                        issue["source"],
                        issue["acceptance"],
                        json.dumps(issue["labels"]),
                        issue["suggested_lane"],
                        ts,
                        ts,
                    ),
                )
            return True, f"Successfully loaded {len(SEED_ISSUES)} issues"
        except Exception as e:
            return False, f"Seed failed: {e}"

    if conn is not None:
        return _do_seed(conn)
    with db() as c:
        return _do_seed(c)


def reset_demo() -> tuple[bool, str]:
    """Atomically clear and re-seed the demo database.

    All DELETE and INSERT operations run inside a single transaction so
    the database is never left in a partially-reset state.
    """
    try:
        with db() as conn:
            conn.execute("DELETE FROM sessions")
            conn.execute("DELETE FROM issues")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='issues'")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='sessions'")

            return seed_issues(conn)
    except Exception as e:
        return False, f"Import failed: {e}"


def scope_issue(issue: sqlite3.Row) -> dict[str, Any]:
    text = f"{issue['title']} {issue['description']} {issue['acceptance']} {' '.join(json.loads(issue['labels_json']))}".lower()
    likely_files = []
    if "ui" in text or "frontend" in text or "filter" in text:
        likely_files.extend(["app/templates/index.html", "app/static/styles.css"])
    if "import" in text:
        likely_files.append("app/main.py")
    if "role" in text or "permission" in text:
        likely_files.extend(["app/main.py", "README.md"])
    if not likely_files:
        likely_files.append("app/main.py")

    risk_words = ["permission", "security", "architecture", "compliance", "multi-repo", "tenant"]
    found_risks = [word for word in risk_words if word in text]

    has_clear_acceptance = issue["acceptance"] and "not yet defined" not in issue["acceptance"].lower()
    lane = "needs_clarification"
    confidence = 62
    missing_info = ""
    rationale = ""

    if found_risks:
        lane = "senior_review"
        confidence = 88
        rationale = "Devin flagged architecture, security, or permissions risk that should stay with senior engineering review."
        missing_info = "Define policy, ownership, and rollout constraints before autonomous execution."
    elif has_clear_acceptance and issue["suggested_lane"] == "ready_for_devin":
        lane = "ready_for_devin"
        confidence = 91
        rationale = "Issue is bounded, low-risk, and has concrete acceptance criteria that Devin can execute against."
        missing_info = ""
    else:
        lane = "needs_clarification"
        confidence = 74
        rationale = "Issue intent is understandable, but the success criteria or preferred implementation path are still too vague."
        missing_info = "Clarify exact failure mode, target workflow, and preferred output channel before launching a fix session."

    next_action = {
        "ready_for_devin": "Launch Devin fix session",
        "needs_clarification": "Request clarification in Jira",
        "senior_review": "Escalate to senior engineering",
    }[lane]

    return {
        "lane": lane,
        "confidence": confidence,
        "likely_files": ", ".join(likely_files),
        "risk_flags": ", ".join(found_risks) if found_risks else "None",
        "missing_info": missing_info or "None",
        "rationale": rationale,
        "next_action": next_action,
    }


def launch_scope_sessions() -> None:
    with db() as conn:
        issues = conn.execute("SELECT * FROM issues ORDER BY id").fetchall()
        for issue in issues:
            if issue["scope_status"] == "scoped":
                continue
            scoped = scope_issue(issue)
            ts = now_iso()
            conn.execute(
                """
                UPDATE issues
                SET scope_status='scoped', devin_lane=?, confidence=?, likely_files=?, risk_flags=?,
                    missing_info=?, rationale=?, updated_at=?
                WHERE id=?
                """,
                (
                    scoped["lane"],
                    scoped["confidence"],
                    scoped["likely_files"],
                    scoped["risk_flags"],
                    scoped["missing_info"],
                    scoped["rationale"],
                    ts,
                    issue["id"],
                ),
            )
            conn.execute(
                """
                INSERT INTO sessions (
                    issue_id, session_type, launch_mode, session_ref, status, summary, created_at, updated_at
                ) VALUES (?, 'scope', 'live', ?, 'completed', ?, ?, ?)
                """,
                (
                    issue["id"],
                    f"scope-{uuid.uuid4().hex[:10]}",
                    f"Devin scoped this ticket as {LANE_LABELS[scoped['lane']]} with confidence {scoped['confidence']}.",
                    ts,
                    ts,
                ),
            )


def launch_fix_sessions(issue_ids: list[int]) -> None:
    with db() as conn:
        issues = conn.execute(
            f"SELECT * FROM issues WHERE id IN ({','.join(['?'] * len(issue_ids))})",
            issue_ids,
        ).fetchall()
        for issue in issues:
            if issue["devin_lane"] != "ready_for_devin":
                continue
            ts = now_iso()
            conn.execute("UPDATE issues SET selected_for_fix=1, updated_at=? WHERE id=?", (ts, issue["id"]))
            conn.execute(
                """
                INSERT INTO sessions (
                    issue_id, session_type, launch_mode, session_ref, status, summary, pr_url, created_at, updated_at
                ) VALUES (?, 'fix', 'live', ?, 'in_progress', ?, ?, ?, ?)
                """,
                (
                    issue["id"],
                    f"fix-{uuid.uuid4().hex[:12]}",
                    "Devin started implementation work from the approved scoped ticket.",
                    f"https://github.com/your-org/your-repo/pull/{200 + issue['id']}",
                    ts,
                    ts,
                ),
            )


def sync_sessions() -> None:
    with db() as conn:
        sessions = conn.execute("SELECT * FROM sessions WHERE session_type='fix' ORDER BY id").fetchall()
        for idx, session in enumerate(sessions):
            ts = now_iso()
            if session["status"] == "completed":
                continue
            next_status = "completed" if idx % 2 == 0 else "blocked"
            summary = (
                "PR opened and ready for review. Devin completed the scoped implementation."
                if next_status == "completed"
                else "Blocked waiting on product clarification before changing notification behavior."
            )
            error_text = None if next_status == "completed" else "Need confirmation on preferred update channel before proceeding."
            conn.execute(
                "UPDATE sessions SET status=?, summary=?, error_text=?, updated_at=? WHERE id=?",
                (next_status, summary, error_text, ts, session["id"]),
            )


def get_dashboard() -> dict[str, Any]:
    with db() as conn:
        issues = [dict(row) for row in conn.execute("SELECT * FROM issues ORDER BY id").fetchall()]
        for issue in issues:
            issue["labels"] = json.loads(issue["labels_json"])
        sessions = [dict(row) for row in conn.execute(
            """
            SELECT s.*, i.external_id, i.title
            FROM sessions s
            JOIN issues i ON i.id = s.issue_id
            ORDER BY s.id DESC
            """
        ).fetchall()]

    counts = {
        "total": len(issues),
        "ready": sum(1 for i in issues if i.get("devin_lane") == "ready_for_devin"),
        "clarify": sum(1 for i in issues if i.get("devin_lane") == "needs_clarification"),
        "senior": sum(1 for i in issues if i.get("devin_lane") == "senior_review"),
        "fix_runs": sum(1 for s in sessions if s["session_type"] == "fix"),
    }
    return {"issues": issues, "sessions": sessions, "counts": counts}


@app.on_event("startup")
def startup() -> None:
    init_db()
    seed_issues()


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        "index.html",
        {"request": request, **get_dashboard(), "lane_labels": LANE_LABELS},
    )


@app.post("/reset")
def reset() -> RedirectResponse:
    success, message = reset_demo()
    status = "success" if success else "error"
    return RedirectResponse(f"/?status={status}&message={quote(message)}", status_code=303)


@app.post("/scope")
def scope() -> RedirectResponse:
    launch_scope_sessions()
    return RedirectResponse("/", status_code=303)


@app.post("/launch")
def launch(issue_ids: list[int] = Form(default=[])) -> RedirectResponse:
    if issue_ids:
        launch_fix_sessions(issue_ids)
    return RedirectResponse("/", status_code=303)


@app.post("/sync")
def sync() -> RedirectResponse:
    sync_sessions()
    return RedirectResponse("/", status_code=303)
