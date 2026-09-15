"""
Plain sqlite3 data layer for Jharkhand Samadhan — no ORM dependency, so the
whole app only needs Flask + Pillow to run.

Rows are hydrated into SimpleNamespace objects so templates can use normal
dot-attribute access (c.status, c.citizen.name, c.deadline.strftime(...)),
with computed fields like is_overdue attached in Python.
"""

import os
import random
import sqlite3
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from flask import g
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "jsamadhan.db")

ROLES = ("citizen", "officer", "admin", "university", "faculty", "student")
INFRA_CATEGORIES = {"Roads & Infrastructure"}

CATEGORIES = [
    "Roads & Infrastructure", "Water Resources", "Electricity",
    "Sanitation", "Healthcare", "Education", "Public Safety", "Other",
]

DISTRICTS = [
    "Ranchi", "Dhanbad", "Dumka", "Bokaro", "Gumla", "Deoghar",
    "Hazaribagh", "Giridih", "East Singhbhum", "West Singhbhum",
]

RESOLUTION_WINDOW_DAYS = 5

# SLAs (in days) keyed by AI-assessed urgency level.
URGENCY_SLA_DAYS = {
    "critical": 3,
    "high": 7,
    "normal": 14,
    "low": 30,
}
URGENCY_ORDER = {"critical": 0, "high": 1, "normal": 2, "low": 3, None: 4}

# Official Challenge lifecycle (Government Command Center).
# `status` is the full lifecycle; `validation_status` mirrors the government
# validation outcome (NEEDS_VALIDATION / VALIDATED / REJECTED). No future
# entities (university/project) exist yet, so ASSIGNED/IN_PROJECT/COMPLETED
# are reserved stages that stay at zero until those phases ship.
CHALLENGE_STATUSES = (
    "NEEDS_VALIDATION", "VALIDATED", "READY_FOR_MATCHING", "REJECTED",
    "ASSIGNED", "IN_PROJECT", "COMPLETED",
)
CHALLENGE_VALIDATION_STATUSES = ("NEEDS_VALIDATION", "VALIDATED", "REJECTED")
CHALLENGE_PRIORITY_ORDER = {"critical": 0, "high": 1, "normal": 2, "low": 3, None: 4}
CHALLENGE_AWAITING_MATCH = ("VALIDATED", "READY_FOR_MATCHING")

# University / institution ecosystem (Phase 3).
UNIVERSITY_VERIFICATION_STATUSES = ("PENDING", "VERIFIED", "SUSPENDED")
UNIVERSITY_TYPES = ("University", "Engineering College", "Research Institution",
                    "Polytechnic", "Other")
UNIVERSITY_MATCH_STATUSES = ("RECOMMENDED", "INVITED", "ACCEPTED", "DECLINED", "REMOVED")
UNIVERSITY_MATCH_ORDER = {
    "RECOMMENDED": 0, "INVITED": 1, "ACCEPTED": 2, "DECLINED": 3, "REMOVED": 4,
    None: 5,
}

# Phase 4 — teams, proposals and projects after university acceptance.
TEAM_STATUSES = ("FORMING", "ACTIVE", "SUBMITTED", "COMPLETED", "ARCHIVED")
TEAM_MEMBER_ROLES = ("FACULTY_LEAD", "FACULTY", "STUDENT", "TEAM_LEAD")
TEAM_MEMBER_STATUSES = ("ACTIVE", "REMOVED", "LEFT")
PROPOSAL_STATUSES = ("DRAFT", "SUBMITTED", "UNDER_REVIEW",
                     "REVISION_REQUESTED", "APPROVED", "REJECTED")
# Statuses that carry a government verdict + feedback comment.
PROPOSAL_FEEDBACK_STATUSES = ("REVISION_REQUESTED", "APPROVED", "REJECTED")
# Proposals that still need the reviewer's attention.
PROPOSAL_MARKER_STATUSES = ("SUBMITTED", "UNDER_REVIEW")
PROJECT_STATUSES = ("CREATED", "ACTIVE", "COMPLETED", "PAUSED", "CANCELLED")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    phone TEXT NOT NULL,
    role TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    alternate_phone TEXT,
    home_address TEXT,
    profile_photo TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    district TEXT NOT NULL,
    location_text TEXT,
    latitude REAL,
    longitude REAL,
    image_metadata TEXT,
    image_taken_at TEXT,
    image_latitude REAL,
    image_longitude REAL,
    location_address TEXT,
    location_city TEXT,
    location_state TEXT,
    pincode TEXT,
    photo_filename TEXT,
    is_photo_video INTEGER DEFAULT 0,
    citizen_id INTEGER NOT NULL,
    officer_id INTEGER,
    status TEXT NOT NULL DEFAULT 'Submitted',
    ai_confidence INTEGER,
    ai_note TEXT,
    ai_detail TEXT,
    severity INTEGER,
    urgency TEXT,
    accepted_at TEXT,
    deadline TEXT,
    resolution_filename TEXT,
    resolution_confidence REAL,
    resolution_note TEXT,
    resolved_at TEXT,
    notify_sent_at TEXT,
    action_due_at TEXT,
    escalated_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(citizen_id) REFERENCES users(id),
    FOREIGN KEY(officer_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS complaint_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    note TEXT,
    timestamp TEXT NOT NULL,
    FOREIGN KEY(complaint_id) REFERENCES complaints(id)
);

CREATE TABLE IF NOT EXISTS challenges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    subcategory TEXT,
    district TEXT NOT NULL,
    location_text TEXT,
    latitude REAL,
    longitude REAL,
    priority_score INTEGER NOT NULL DEFAULT 0,
    priority_level TEXT NOT NULL DEFAULT 'normal',
    ai_summary TEXT,
    ai_confidence INTEGER,
    validation_status TEXT NOT NULL DEFAULT 'NEEDS_VALIDATION',
    status TEXT NOT NULL DEFAULT 'NEEDS_VALIDATION',
    validated_by INTEGER,
    validated_at TEXT,
    rejection_reason TEXT,
    report_count INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(validated_by) REFERENCES users(id),
    FOREIGN KEY(created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS challenge_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    challenge_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    note TEXT,
    actor_id INTEGER,
    timestamp TEXT NOT NULL,
    FOREIGN KEY(challenge_id) REFERENCES challenges(id),
    FOREIGN KEY(actor_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS duplicate_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id INTEGER NOT NULL,
    candidate_complaint_id INTEGER,
    candidate_challenge_id INTEGER,
    confidence REAL NOT NULL,
    signals TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    reviewed_by INTEGER,
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(complaint_id) REFERENCES complaints(id),
    FOREIGN KEY(candidate_complaint_id) REFERENCES complaints(id),
    FOREIGN KEY(candidate_challenge_id) REFERENCES challenges(id),
    FOREIGN KEY(reviewed_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS universities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    short_name TEXT,
    email TEXT NOT NULL,
    phone TEXT,
    address TEXT,
    district TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'Jharkhand',
    website TEXT,
    description TEXT,
    institution_type TEXT NOT NULL DEFAULT 'University',
    verification_status TEXT NOT NULL DEFAULT 'PENDING',
    admin_user_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(admin_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS university_expertise (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id INTEGER NOT NULL,
    department TEXT NOT NULL,
    expertise TEXT NOT NULL,
    research_area TEXT,
    keywords TEXT,
    lab_capabilities TEXT,
    description TEXT,
    FOREIGN KEY(university_id) REFERENCES universities(id)
);

CREATE TABLE IF NOT EXISTS faculty (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    university_id INTEGER NOT NULL,
    department TEXT NOT NULL,
    designation TEXT,
    expertise TEXT,
    research_interests TEXT,
    verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(university_id) REFERENCES universities(id)
);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    university_id INTEGER NOT NULL,
    department TEXT NOT NULL,
    course TEXT,
    year TEXT,
    skills TEXT,
    interests TEXT,
    verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(university_id) REFERENCES universities(id)
);

CREATE TABLE IF NOT EXISTS challenge_university_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    challenge_id INTEGER NOT NULL,
    university_id INTEGER NOT NULL,
    score REAL NOT NULL,
    match_level TEXT NOT NULL,
    signals TEXT,
    status TEXT NOT NULL DEFAULT 'RECOMMENDED',
    recommended_at TEXT NOT NULL,
    reviewed_by INTEGER,
    reviewed_at TEXT,
    response_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    FOREIGN KEY(challenge_id) REFERENCES challenges(id),
    FOREIGN KEY(university_id) REFERENCES universities(id),
    FOREIGN KEY(reviewed_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    challenge_id INTEGER NOT NULL,
    university_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'FORMING',
    created_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(challenge_id) REFERENCES challenges(id),
    FOREIGN KEY(university_id) REFERENCES universities(id),
    FOREIGN KEY(created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS team_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    member_role TEXT NOT NULL,
    joined_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    UNIQUE(team_id, user_id),
    FOREIGN KEY(team_id) REFERENCES teams(id),
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    challenge_id INTEGER NOT NULL,
    university_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    problem_statement TEXT NOT NULL,
    proposed_solution TEXT NOT NULL,
    methodology TEXT NOT NULL,
    expected_outcome TEXT,
    required_resources TEXT,
    estimated_duration TEXT,
    submitted_by INTEGER,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    review_comment TEXT,
    reviewed_by INTEGER,
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(challenge_id) REFERENCES challenges(id),
    FOREIGN KEY(university_id) REFERENCES universities(id),
    FOREIGN KEY(team_id) REFERENCES teams(id),
    FOREIGN KEY(submitted_by) REFERENCES users(id),
    FOREIGN KEY(reviewed_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS proposal_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT,
    performed_by INTEGER,
    comment TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(proposal_id) REFERENCES proposals(id),
    FOREIGN KEY(performed_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    challenge_id INTEGER NOT NULL,
    university_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    proposal_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'CREATED',
    start_date TEXT,
    target_end_date TEXT,
    created_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(challenge_id) REFERENCES challenges(id),
    FOREIGN KEY(university_id) REFERENCES universities(id),
    FOREIGN KEY(team_id) REFERENCES teams(id),
    FOREIGN KEY(proposal_id) REFERENCES proposals(id),
    FOREIGN KEY(created_by) REFERENCES users(id)
);
"""


# ---------------------------------------------------------------------------
# connection management (one connection per request, via flask.g)
# ---------------------------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    complaint_columns = {row[1] for row in conn.execute("PRAGMA table_info(complaints)")}
    for column, column_type in (
        ("latitude", "REAL"), ("longitude", "REAL"),
        ("image_metadata", "TEXT"), ("image_taken_at", "TEXT"),
        ("image_latitude", "REAL"), ("image_longitude", "REAL"),
        ("location_address", "TEXT"), ("location_city", "TEXT"),
        ("location_state", "TEXT"), ("pincode", "TEXT"),
        ("severity", "INTEGER"), ("urgency", "TEXT"),
        ("ai_detail", "TEXT"),
        ("notify_sent_at", "TEXT"), ("action_due_at", "TEXT"), ("escalated_at", "TEXT"),
        ("challenge_id", "INTEGER"),
    ):
        if column not in complaint_columns:
            conn.execute(f"ALTER TABLE complaints ADD COLUMN {column} {column_type}")
    user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    for column, column_type in (
        ("alternate_phone", "TEXT"), ("home_address", "TEXT"), ("profile_photo", "TEXT"),
    ):
        if column not in user_columns:
            conn.execute(f"ALTER TABLE users ADD COLUMN {column} {column_type}")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# hydration helpers — turn sqlite3.Row into attribute-friendly objects
# ---------------------------------------------------------------------------

def _parse_dt(s):
    return datetime.fromisoformat(s) if s else None


def _now():
    return datetime.utcnow()


def hydrate_user(row):
    if row is None:
        return None
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    return ns


def hydrate_log(row):
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.timestamp = _parse_dt(d["timestamp"])
    return ns


def hydrate_complaint(conn, row, with_relations=True):
    if row is None:
        return None
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    ns.accepted_at = _parse_dt(d.get("accepted_at"))
    ns.deadline = _parse_dt(d.get("deadline"))
    ns.resolved_at = _parse_dt(d.get("resolved_at"))
    ns.notify_sent_at = _parse_dt(d.get("notify_sent_at"))
    ns.action_due_at = _parse_dt(d.get("action_due_at"))
    ns.escalated_at = _parse_dt(d.get("escalated_at"))
    ns.notified = bool(ns.notify_sent_at)
    ns.is_escalated = ns.status == "Escalated"
    ns.action_overdue = bool(ns.action_due_at) and ns.status not in ("Resolved","Rejected","Escalated") and _now() > ns.action_due_at
    ns.is_photo_video = bool(d.get("is_photo_video"))
    ns.is_infra = d["category"] in INFRA_CATEGORIES
    ns.is_overdue = bool(ns.deadline) and ns.status == "Accepted by Officer" and _now() > ns.deadline
    ns.days_left = (ns.deadline - _now()).days if ns.deadline else None
    ns.urgency_key = ns.urgency or "normal"

    ns.ai_data = None
    if d.get("ai_detail"):
        try:
            import json
            ns.ai_data = json.loads(d["ai_detail"])
        except (TypeError, ValueError):
            ns.ai_data = None

    if with_relations:
        ns.citizen = hydrate_user(get_user_by_id(conn, d["citizen_id"]))
        ns.officer = hydrate_user(get_user_by_id(conn, d["officer_id"])) if d.get("officer_id") else None
        ns.logs = [hydrate_log(r) for r in
                   conn.execute("SELECT * FROM complaint_logs WHERE complaint_id=? ORDER BY timestamp ASC",
                                (d["id"],)).fetchall()]
    return ns


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------

def create_user(conn, name, email, phone, password, role):
    ph = generate_password_hash(password)
    cur = conn.execute(
        "INSERT INTO users (name, email, phone, role, password_hash, created_at) VALUES (?,?,?,?,?,?)",
        (name, email, phone, role, ph, _now().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def get_user_by_id(conn, user_id):
    if user_id is None:
        return None
    return conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()


def get_user_by_email(conn, email):
    return conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()


def get_user_by_email_role(conn, email, role):
    return conn.execute("SELECT * FROM users WHERE email=? AND role=?", (email, role)).fetchone()


def verify_password(user_row, password):
    return check_password_hash(user_row["password_hash"], password)


def list_officers(conn):
    return [hydrate_user(r) for r in conn.execute("SELECT * FROM users WHERE role='officer' ORDER BY name").fetchall()]


def count_users(conn, role):
    return conn.execute("SELECT COUNT(*) c FROM users WHERE role=?", (role,)).fetchone()["c"]


def update_user_account(conn, user_id, name, email, phone, alternate_phone, home_address):
    conn.execute(
        "UPDATE users SET name=?, email=?, phone=?, alternate_phone=?, home_address=? WHERE id=?",
        (name, email, phone, alternate_phone, home_address, user_id),
    )
    conn.commit()


def set_profile_photo(conn, user_id, filename):
    conn.execute("UPDATE users SET profile_photo=? WHERE id=?", (filename, user_id))
    conn.commit()


def clear_profile_photo(conn, user_id):
    conn.execute("UPDATE users SET profile_photo=NULL WHERE id=?", (user_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# complaints
# ---------------------------------------------------------------------------

def new_complaint_code(conn):
    while True:
        code = f"JS-{random.randint(10000, 99999)}"
        if not conn.execute("SELECT 1 FROM complaints WHERE code=?", (code,)).fetchone():
            return code


def create_complaint(conn, **fields):
    fields.setdefault("created_at", _now().isoformat())
    fields.setdefault("status", "Submitted")
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    cur = conn.execute(f"INSERT INTO complaints ({cols}) VALUES ({placeholders})", tuple(fields.values()))
    conn.commit()
    return cur.lastrowid


def add_log(conn, complaint_id, status, note=""):
    conn.execute(
        "INSERT INTO complaint_logs (complaint_id, status, note, timestamp) VALUES (?,?,?,?)",
        (complaint_id, status, note, _now().isoformat()),
    )


def set_status(conn, complaint_id, status, note="", extra_fields=None):
    fields = dict(extra_fields or {})
    fields["status"] = status
    set_clause = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE complaints SET {set_clause} WHERE id=?", (*fields.values(), complaint_id))
    add_log(conn, complaint_id, status, note)
    conn.commit()


def get_complaint_row(conn, complaint_id=None, code=None):
    if code is not None:
        return conn.execute("SELECT * FROM complaints WHERE code=?", (code,)).fetchone()
    return conn.execute("SELECT * FROM complaints WHERE id=?", (complaint_id,)).fetchone()


def list_by_citizen(conn, citizen_id):
    rows = conn.execute("SELECT * FROM complaints WHERE citizen_id=? ORDER BY created_at DESC",
                         (citizen_id,)).fetchall()
    return [hydrate_complaint(conn, r, with_relations=True) for r in rows]


def list_recent_resolved(conn, limit=6):
    """Latest resolved complaints for the public gallery. Caller must not
    render reporter identity — anonymity is enforced in the template."""
    rows = conn.execute(
        "SELECT * FROM complaints WHERE status='Resolved' ORDER BY resolved_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [hydrate_complaint(conn, r, with_relations=False) for r in rows]


def list_queue(conn):
    rows = conn.execute(
        "SELECT * FROM complaints WHERE status IN ('Pending Officer Review','AI Verified') ORDER BY created_at ASC"
    ).fetchall()
    return [hydrate_complaint(conn, r, with_relations=True) for r in rows]


def list_my_cases(conn, officer_id):
    rows = conn.execute(
        "SELECT * FROM complaints WHERE officer_id=? AND status IN ('Accepted by Officer','Reopened') "
        "ORDER BY CASE WHEN urgency='critical' THEN 0 WHEN urgency='high' THEN 1 "
        "WHEN urgency='normal' THEN 2 ELSE 3 END, deadline ASC", (officer_id,)
    ).fetchall()
    return [hydrate_complaint(conn, r, with_relations=True) for r in rows]


def list_resolved_by(conn, officer_id, limit=10):
    rows = conn.execute(
        "SELECT * FROM complaints WHERE officer_id=? AND status='Resolved' ORDER BY resolved_at DESC LIMIT ?",
        (officer_id, limit)
    ).fetchall()
    return [hydrate_complaint(conn, r, with_relations=True) for r in rows]


def list_all_complaints(conn):
    rows = conn.execute("SELECT * FROM complaints ORDER BY created_at DESC").fetchall()
    return [hydrate_complaint(conn, r, with_relations=True) for r in rows]


def list_escalated(conn):
    rows = conn.execute(
        "SELECT * FROM complaints WHERE status='Escalated' ORDER BY escalated_at DESC"
    ).fetchall()
    return [hydrate_complaint(conn, r, with_relations=True) for r in rows]


OPEN_STATUS_CODES = ("Submitted", "AI Verified", "Pending Officer Review",
                     "Accepted by Officer", "Reopened")


def list_due_notifications(conn, before_ts):
    rows = conn.execute(
        "SELECT * FROM complaints WHERE status NOT IN ('Resolved','Rejected','Escalated') "
        "AND notify_sent_at IS NULL AND created_at <= ? ORDER BY created_at ASC",
        (before_ts,),
    ).fetchall()
    return rows


def list_overdue_actions(conn, before_ts):
    rows = conn.execute(
        f"SELECT * FROM complaints WHERE status IN {_sql_in(OPEN_STATUS_CODES)} "
        "AND action_due_at IS NOT NULL AND action_due_at < ? ORDER BY action_due_at ASC",
        (*OPEN_STATUS_CODES, before_ts),
    ).fetchall()
    return rows


def mark_notified(conn, complaint_id, timestamp):
    conn.execute("UPDATE complaints SET notify_sent_at=? WHERE id=?", (timestamp, complaint_id))
    add_log(conn, complaint_id, "Notification",
            "Citizen notified within 24 hours (demo SMS/call).")
    conn.commit()


def escalate_complaint(conn, complaint_id, note):
    conn.execute("UPDATE complaints SET status='Escalated', escalated_at=? WHERE id=?",
                 (_now().isoformat(), complaint_id))
    add_log(conn, complaint_id, "Escalated", note)
    conn.commit()


def _sql_in(items):
    return "(" + ",".join("?" * len(items)) + ")"


# ---------------------------------------------------------------------------
# official challenges (Government Command Center)
# ---------------------------------------------------------------------------

def new_challenge_code(conn):
    row = conn.execute("SELECT MAX(CAST(SUBSTR(code, 7) AS INTEGER)) m FROM challenges").fetchone()
    nxt = ((row["m"] if row["m"] is not None else 0) + 1) if (row and row["m"]) else 1
    while True:
        code = f"JS-CH-{nxt:04d}"
        if not conn.execute("SELECT 1 FROM challenges WHERE code=?", (code,)).fetchone():
            return code
        nxt += 1


def create_challenge(conn, **fields):
    fields.setdefault("created_at", _now().isoformat())
    fields.setdefault("updated_at", fields["created_at"])
    fields.setdefault("status", "NEEDS_VALIDATION")
    fields.setdefault("validation_status", "NEEDS_VALIDATION")
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    cur = conn.execute(f"INSERT INTO challenges ({cols}) VALUES ({placeholders})",
                       tuple(fields.values()))
    conn.commit()
    return cur.lastrowid


def get_challenge_row(conn, challenge_id=None, code=None):
    if code is not None:
        return conn.execute("SELECT * FROM challenges WHERE code=?", (code,)).fetchone()
    return conn.execute("SELECT * FROM challenges WHERE id=?", (challenge_id,)).fetchone()


def hydrate_challenge(conn, row, with_relations=True):
    if row is None:
        return None
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    ns.updated_at = _parse_dt(d.get("updated_at"))
    ns.validated_at = _parse_dt(d.get("validated_at"))
    ns.priority_key = ns.priority_level or "normal"
    ns.is_validated = ns.validation_status == "VALIDATED"
    ns.is_rejected = ns.validation_status == "REJECTED"
    ns.awaiting_match = ns.status in CHALLENGE_AWAITING_MATCH
    ns.status_key = ns.status

    if with_relations:
        ns.creator = hydrate_user(get_user_by_id(conn, d.get("created_by"))) if d.get("created_by") else None
        ns.validator = hydrate_user(get_user_by_id(conn, d.get("validated_by"))) if d.get("validated_by") else None
        ns.reports = [hydrate_complaint(conn, r, with_relations=False) for r in conn.execute(
            "SELECT * FROM complaints WHERE challenge_id=? ORDER BY created_at DESC",
            (d["id"],)).fetchall()]
        ns.logs = [hydrate_log(r) for r in
                   conn.execute("SELECT * FROM challenge_logs WHERE challenge_id=? "
                                "ORDER BY timestamp ASC", (d["id"],)).fetchall()]
        ns.log_count = len(ns.logs)
    return ns


def list_challenges(conn, status=None):
    if status:
        rows = conn.execute(
            "SELECT * FROM challenges WHERE status=? ORDER BY priority_level="
            "(CASE priority_level WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
            "WHEN 'normal' THEN 2 ELSE 3 END), updated_at DESC", (status,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM challenges ORDER BY "
            "CASE priority_level WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
            "WHEN 'normal' THEN 2 ELSE 3 END, updated_at DESC").fetchall()
    return [hydrate_challenge(conn, r, with_relations=False) for r in rows]


def update_challenge(conn, challenge_id, actor_id, **fields):
    fields["updated_at"] = _now().isoformat()
    set_clause = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE challenges SET {set_clause} WHERE id=?",
                 (*fields.values(), challenge_id))
    refresh_challenge_report_count(conn, challenge_id)
    add_challenge_log(conn, challenge_id, "Updated",
                      "Challenge details updated by officer.", actor_id)
    conn.commit()


def set_challenge_status(conn, challenge_id, status, note="", actor_id=None,
                         extra_fields=None):
    fields = dict(extra_fields or {})
    fields["status"] = status
    fields["updated_at"] = _now().isoformat()
    if status == "NEEDS_VALIDATION":
        fields["validation_status"] = "NEEDS_VALIDATION"
    elif status in ("VALIDATED", "READY_FOR_MATCHING"):
        fields["validation_status"] = "VALIDATED"
    elif status == "REJECTED":
        fields["validation_status"] = "REJECTED"
    set_clause = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE challenges SET {set_clause} WHERE id=?",
                 (*fields.values(), challenge_id))
    add_challenge_log(conn, challenge_id, status, note, actor_id)
    conn.commit()


def validate_challenge(conn, challenge_id, actor_id):
    now = _now().isoformat()
    conn.execute(
        "UPDATE challenges SET status='READY_FOR_MATCHING', validation_status='VALIDATED', "
        "validated_by=?, validated_at=?, updated_at=? WHERE id=?",
        (actor_id, now, now, challenge_id),
    )
    add_challenge_log(conn, challenge_id, "READY_FOR_MATCHING",
                      "Government validated this challenge. Notification log entry written for "
                      "government users; AI university matching can now be run for it.",
                      actor_id)
    conn.commit()


def reject_challenge(conn, challenge_id, reason, actor_id):
    reason = (reason or "").strip() or "Rejected by government."
    conn.execute(
        "UPDATE challenges SET status='REJECTED', validation_status='REJECTED', "
        "rejection_reason=?, updated_at=? WHERE id=?",
        (reason, _now().isoformat(), challenge_id),
    )
    add_challenge_log(conn, challenge_id, "REJECTED",
                      f"Challenge rejected by government. Reason: {reason}", actor_id)
    conn.commit()


def add_challenge_log(conn, challenge_id, status, note="", actor_id=None):
    conn.execute(
        "INSERT INTO challenge_logs (challenge_id, status, note, actor_id, timestamp) "
        "VALUES (?,?,?,?,?)",
        (challenge_id, status, note, actor_id, _now().isoformat()),
    )


def refresh_challenge_report_count(conn, challenge_id):
    count = conn.execute(
        "SELECT COUNT(*) c FROM complaints WHERE challenge_id=?", (challenge_id,)
    ).fetchone()["c"]
    conn.execute("UPDATE challenges SET report_count=? WHERE id=?",
                 (count, challenge_id))


def link_complaints_to_challenge(conn, challenge_id, complaint_ids):
    """Link validated complaint ids (that aren't already linked) to a challenge."""
    for cid in complaint_ids:
        conn.execute(
            "UPDATE complaints SET challenge_id=? WHERE id=? "
            "AND (challenge_id IS NULL OR challenge_id=?)",
            (challenge_id, cid, challenge_id),
        )
    refresh_challenge_report_count(conn, challenge_id)
    conn.commit()


def list_unlinked_complaints(conn):
    rows = conn.execute(
        "SELECT * FROM complaints WHERE challenge_id IS NULL "
        "ORDER BY created_at DESC").fetchall()
    return [hydrate_complaint(conn, r, with_relations=False) for r in rows]


def linked_complaints(conn, challenge_id):
    rows = conn.execute(
        "SELECT * FROM complaints WHERE challenge_id=? ORDER BY created_at DESC",
        (challenge_id,)).fetchall()
    return [hydrate_complaint(conn, r, with_relations=False) for r in rows]


def command_center_kpis(conn):
    """Live, real numbers for the Command Center KPI cards. Teams, proposals
    and projects now report from the Phase 4 tables; pilot/deployment cards
    still honestly read zero until those phases exist."""
    total = conn.execute("SELECT COUNT(*) c FROM complaints").fetchone()["c"]
    needs_validation = conn.execute(
        "SELECT COUNT(*) c FROM complaints WHERE status IN ('Pending Officer Review','AI Verified')"
    ).fetchone()["c"]
    validated = conn.execute(
        "SELECT COUNT(*) c FROM challenges WHERE validation_status='VALIDATED'"
    ).fetchone()["c"]
    critical = conn.execute(
        "SELECT COUNT(*) c FROM challenges WHERE priority_level='critical'"
    ).fetchone()["c"]
    awaiting = conn.execute(
        "SELECT COUNT(*) c FROM challenges WHERE status IN " + _sql_in(CHALLENGE_AWAITING_MATCH),
        (*CHALLENGE_AWAITING_MATCH,),
    ).fetchone()["c"]
    pending_duplicates = conn.execute(
        "SELECT COUNT(*) c FROM duplicate_matches WHERE status='PENDING'"
    ).fetchone()["c"]
    return {
        "citizen_reports": total,
        "needs_validation": needs_validation,
        "validated_challenges": validated,
        "critical_challenges": critical,
        "awaiting_institution": awaiting,
        "duplicate_alerts": pending_duplicates,
        "uni_matching_ready": count_matching_ready(conn),
        "uni_recommendations": count_recommendations_pending_review(conn),
        "active_teams": conn.execute("SELECT COUNT(*) c FROM teams").fetchone()["c"],
        "proposals_review": count_proposals_needing_review(conn),
        "active_projects": conn.execute(
            "SELECT COUNT(*) c FROM projects WHERE status IN ('CREATED','ACTIVE')"
        ).fetchone()["c"],
        "pilot_projects": 0,
        "deployed_solutions": 0,
    }


def command_center_actions(conn):
    """Action Required panel counts — every value derived from live data.
    Pilot/pilot-evaluation actions are future phases and honest zeros."""
    return {
        "reports_needing_validation": conn.execute(
            "SELECT COUNT(*) c FROM complaints WHERE status IN ('Pending Officer Review','AI Verified')"
        ).fetchone()["c"],
        "challenges_needing_review": conn.execute(
            "SELECT COUNT(*) c FROM challenges WHERE validation_status='NEEDS_VALIDATION'"
        ).fetchone()["c"],
        "challenges_needing_match": count_matching_ready(conn),
        "duplicate_matches_pending": conn.execute(
            "SELECT COUNT(*) c FROM duplicate_matches WHERE status='PENDING'"
        ).fetchone()["c"],
        "uni_recommendations_review": count_recommendations_pending_review(conn),
        "proposals_needing_approval": count_proposals_needing_review(conn),
        "projects_overdue": 0,
        "pilots_needing_evaluation": 0,
    }


# ---------------------------------------------------------------------------
# AI duplicate detection — PENDING matches awaiting government review
# ---------------------------------------------------------------------------

DUPLICATE_STATUSES = ("PENDING", "CONFIRMED", "NOT_DUPLICATE", "DISMISSED")


def create_duplicate_match(conn, complaint_id, candidate_complaint_id=None,
                           candidate_challenge_id=None, confidence=0.0,
                           signals=None, candidate_code=""):
    """Record a possible duplicate that the AI detected for a complaint.
    Existing PENDING matches for the same pair are left untouched (idempotent)."""
    if candidate_complaint_id and candidate_challenge_id:
        raise ValueError("One candidate at a time per match row.")
    if not candidate_complaint_id and not candidate_challenge_id:
        raise ValueError("A candidate complaint or challenge is required.")

    if candidate_complaint_id:
        existing = conn.execute(
            "SELECT id FROM duplicate_matches WHERE complaint_id=? "
            "AND candidate_complaint_id=?",
            (complaint_id, candidate_complaint_id)).fetchone()
    else:
        existing = conn.execute(
            "SELECT id FROM duplicate_matches WHERE complaint_id=? "
            "AND candidate_challenge_id=?",
            (complaint_id, candidate_challenge_id)).fetchone()
    if existing:
        # A pair that has already been scanned is never re-created: officers
        # can dismiss or confirm an alert and that decision sticks, even if
        # the AI re-scans the complaint later.
        return existing["id"]

    cur = conn.execute(
        "INSERT INTO duplicate_matches "
        "(complaint_id, candidate_complaint_id, candidate_challenge_id, "
        "confidence, signals, status, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (complaint_id, candidate_complaint_id, candidate_challenge_id,
         confidence, json.dumps(signals or [], ensure_ascii=False),
         "PENDING", _now().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def hydrate_duplicate_match(row):
    if row is None:
        return None
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    ns.reviewed_at = _parse_dt(d.get("reviewed_at"))
    ns.signal_list = []
    if d.get("signals"):
        try:
            ns.signal_list = json.loads(d["signals"])
        except (TypeError, ValueError):
            ns.signal_list = []
    ns.level = ("high" if ns.confidence >= 80 else
                "medium" if ns.confidence >= 65 else "low")
    return ns


def get_duplicate_match(conn, match_id):
    return hydrate_duplicate_match(
        conn.execute("SELECT * FROM duplicate_matches WHERE id=?",
                     (match_id,)).fetchone())


def list_pending_duplicates(conn):
    """PENDING matches with both the source complaint and candidate resolved
    to hydrated objects so command-center cards can show codes + links."""
    rows = conn.execute(
        "SELECT * FROM duplicate_matches WHERE status='PENDING' "
        "ORDER BY confidence DESC").fetchall()
    out = []
    for row in rows:
        ns = hydrate_duplicate_match(row)
        ns.complaint = hydrate_complaint(conn, get_complaint_row(conn, row["complaint_id"]),
                                         with_relations=False)
        if ns.complaint is None:
            continue
        if row["candidate_complaint_id"]:
            ns.candidate = hydrate_complaint(
                conn, get_complaint_row(conn, row["candidate_complaint_id"]),
                with_relations=False)
            ns.candidate_type = "complaint"
        elif row["candidate_challenge_id"]:
            ns.candidate = hydrate_challenge(
                conn, get_challenge_row(conn, row["candidate_challenge_id"]),
                with_relations=False)
            ns.candidate_type = "challenge"
        else:
            continue
        out.append(ns)
    return out


def list_duplicates_for_complaint(conn, complaint_id, status="PENDING"):
    """Candidate matches for one complaint, with hydrated candidates."""
    if status:
        rows = conn.execute(
            "SELECT * FROM duplicate_matches WHERE complaint_id=? AND status=? "
            "ORDER BY confidence DESC", (complaint_id, status)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM duplicate_matches WHERE complaint_id=? "
            "ORDER BY confidence DESC", (complaint_id,)).fetchall()
    out = []
    for row in rows:
        ns = hydrate_duplicate_match(row)
        if row["candidate_complaint_id"]:
            ns.candidate = hydrate_complaint(
                conn, get_complaint_row(conn, row["candidate_complaint_id"]),
                with_relations=False)
            ns.candidate_type = "complaint"
        elif row["candidate_challenge_id"]:
            ns.candidate = hydrate_challenge(
                conn, get_challenge_row(conn, row["candidate_challenge_id"]),
                with_relations=False)
            ns.candidate_type = "challenge"
        else:
            continue
        out.append(ns)
    return out


def possible_additional_for_challenge(conn, challenge_id):
    """Complaints AI flagged as possible members of a challenge (PENDING)
    that are not yet linked, for the 'Possible Additional Reports' section."""
    rows = conn.execute(
        "SELECT dm.* FROM duplicate_matches dm "
        "WHERE dm.candidate_challenge_id=? AND dm.status='PENDING' "
        "ORDER BY dm.confidence DESC", (challenge_id,)).fetchall()
    out = []
    for row in rows:
        ns = hydrate_duplicate_match(row)
        complaint = hydrate_complaint(conn, get_complaint_row(conn, row["complaint_id"]),
                                      with_relations=False)
        if complaint is None or complaint.challenge_id is not None:
            continue
        ns.complaint = complaint
        out.append(ns)
    return out


def review_duplicate_match(conn, match_id, status, reviewed_by, note=""):
    """Government review outcome for a duplicate match: CONFIRMED,
    NOT_DUPLICATE or DISMISSED. Logs the action on the source complaint."""
    status = status if status in DUPLICATE_STATUSES else "DISMISSED"
    conn.execute(
        "UPDATE duplicate_matches SET status=?, reviewed_by=?, reviewed_at=? "
        "WHERE id=?",
        (status, reviewed_by, _now().isoformat(), match_id),
    )
    match = get_duplicate_match(conn, match_id)
    if match:
        label = {"CONFIRMED": "Duplicate confirmed by government",
                 "NOT_DUPLICATE": "Marked as not a duplicate by government",
                 "DISMISSED": "Duplicate alert dismissed"}.get(status, "Duplicate alert updated")
        add_log(conn, match.complaint_id, label,
                (note or label) + (f" (AI confidence {match.confidence}%)."))
    conn.commit()


def dismiss_pending_for_complaint(conn, complaint_id):
    """Close any dangling PENDING alerts for a complaint (e.g. after it was
    linked/challenged elsewhere)."""
    conn.execute(
        "UPDATE duplicate_matches SET status='DISMISSED' "
        "WHERE complaint_id=? AND status='PENDING'", (complaint_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# universities / institutions (Phase 3)
# ---------------------------------------------------------------------------

def create_university(conn, **fields):
    fields.setdefault("created_at", _now().isoformat())
    fields.setdefault("updated_at", fields["created_at"])
    cols = ", ".join(fields.keys())
    placeholders = ", ".join("?" for _ in fields)
    cur = conn.execute(f"INSERT INTO universities ({cols}) VALUES ({placeholders})",
                       tuple(fields.values()))
    conn.commit()
    return cur.lastrowid


def get_university_row(conn, university_id):
    if university_id is None:
        return None
    return conn.execute("SELECT * FROM universities WHERE id=?",
                        (university_id,)).fetchone()


def get_university_by_admin(conn, user_id):
    return conn.execute("SELECT * FROM universities WHERE admin_user_id=?",
                        (user_id,)).fetchone()


def hydrate_university(row):
    if row is None:
        return None
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    ns.updated_at = _parse_dt(d.get("updated_at"))
    ns.is_verified = d.get("verification_status") == "VERIFIED"
    ns.is_pending = d.get("verification_status") == "PENDING"
    ns.is_suspended = d.get("verification_status") == "SUSPENDED"
    return ns


def hydrate_university_expertise(row):
    if row is None:
        return None
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.keywords_list = [k.strip() for k in (d.get("keywords") or "").split(",")
                        if k.strip()]
    ns.skills_tokens = " ".join(filter(None, [
        d.get("department"), d.get("expertise"), d.get("research_area"),
        d.get("keywords"), d.get("lab_capabilities")]))
    return ns


def update_university(conn, university_id, **fields):
    fields["updated_at"] = _now().isoformat()
    set_clause = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE universities SET {set_clause} WHERE id=?",
                 (*fields.values(), university_id))
    conn.commit()


def set_university_verification(conn, university_id, status):
    status = status if status in UNIVERSITY_VERIFICATION_STATUSES else "PENDING"
    update_university(conn, university_id, verification_status=status)


def list_universities(conn, verification_status=None):
    if verification_status:
        rows = conn.execute(
            "SELECT * FROM universities WHERE verification_status=? ORDER BY name",
            (verification_status,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM universities ORDER BY name").fetchall()
    return [hydrate_university(r) for r in rows]


def list_verified_universities(conn):
    return list_universities(conn, verification_status="VERIFIED")


def list_university_expertise(conn, university_id):
    rows = conn.execute(
        "SELECT * FROM university_expertise WHERE university_id=? "
        "ORDER BY department, id", (university_id,)).fetchall()
    return [hydrate_university_expertise(r) for r in rows]


def create_university_expertise(conn, university_id, department, expertise,
                                research_area=None, keywords=None,
                                lab_capabilities=None, description=None):
    cur = conn.execute(
        "INSERT INTO university_expertise "
        "(university_id, department, expertise, research_area, keywords, "
        " lab_capabilities, description) VALUES (?,?,?,?,?,?,?)",
        (university_id, department, expertise, research_area or "",
         keywords or "", lab_capabilities or "", description or ""),
    )
    conn.commit()
    return cur.lastrowid


def delete_university_expertise(conn, expertise_id, university_id):
    conn.execute(
        "DELETE FROM university_expertise WHERE id=? AND university_id=?",
        (expertise_id, university_id))
    conn.commit()


def create_faculty_profile(conn, user_id, university_id, department,
                           designation="", expertise="", research_interests="",
                           verified=1):
    cur = conn.execute(
        "INSERT INTO faculty (user_id, university_id, department, designation, "
        "expertise, research_interests, verified, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (user_id, university_id, department, designation, expertise,
         research_interests, int(bool(verified)), _now().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def get_faculty_profile(conn, user_id):
    row = conn.execute("SELECT * FROM faculty WHERE user_id=?", (user_id,)).fetchone()
    if row is None:
        return None
    ns = SimpleNamespace(**dict(row))
    ns.university = hydrate_university(get_university_row(conn, ns.university_id))
    return ns


def count_faculty(conn, university_id):
    return conn.execute("SELECT COUNT(*) c FROM faculty WHERE university_id=?",
                        (university_id,)).fetchone()["c"]


def create_student_profile(conn, user_id, university_id, department,
                           course="", year="", skills="", interests="", verified=1):
    cur = conn.execute(
        "INSERT INTO students (user_id, university_id, department, course, year, "
        "skills, interests, verified, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (user_id, university_id, department, course, year, skills, interests,
         int(bool(verified)), _now().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def get_student_profile(conn, user_id):
    row = conn.execute("SELECT * FROM students WHERE user_id=?", (user_id,)).fetchone()
    if row is None:
        return None
    ns = SimpleNamespace(**dict(row))
    ns.university = hydrate_university(get_university_row(conn, ns.university_id))
    return ns


def count_students(conn, university_id):
    return conn.execute("SELECT COUNT(*) c FROM students WHERE university_id=?",
                        (university_id,)).fetchone()["c"]


def get_university_for_user(conn, user):
    """The university a logged-in user belongs to, by their role:
    university admin -> universities.admin_user_id, faculty -> faculty.user_id,
    student -> students.user_id. Returns a hydrated university or None."""
    if user is None:
        return None
    if user.role == "university":
        return hydrate_university(get_university_by_admin(conn, user.id))
    if user.role == "faculty":
        prof = get_faculty_profile(conn, user.id)
        return prof.university if prof else None
    if user.role == "student":
        prof = get_student_profile(conn, user.id)
        return prof.university if prof else None
    return None


# ---------------------------------------------------------------------------
# AI-assisted university matching (Phase 3)
# ---------------------------------------------------------------------------

def create_university_match(conn, challenge_id, university_id, score,
                            match_level, signals):
    """Persist one AI recommendation. Idempotent per (challenge, university)
    pair: re-runs refresh the score/signals but never resurrect a row that
    government or the university has already acted on (INVITED / ACCEPTED /
    DECLINED / REMOVED stand as-is)."""
    existing = conn.execute(
        "SELECT id, status FROM challenge_university_matches "
        "WHERE challenge_id=? AND university_id=?",
        (challenge_id, university_id)).fetchone()
    if existing:
        if existing["status"] in ("INVITED", "ACCEPTED", "DECLINED", "REMOVED"):
            return existing["id"]
        conn.execute(
            "UPDATE challenge_university_matches SET score=?, match_level=?, "
            "signals=?, updated_at=? WHERE id=?",
            (score, match_level, json.dumps(signals or [], ensure_ascii=False),
             _now().isoformat(), existing["id"]))
        conn.commit()
        return existing["id"]
    cur = conn.execute(
        "INSERT INTO challenge_university_matches "
        "(challenge_id, university_id, score, match_level, signals, status, "
        " recommended_at, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (challenge_id, university_id, score, match_level,
         json.dumps(signals or [], ensure_ascii=False), "RECOMMENDED",
         _now().isoformat(), _now().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def hydrate_university_match(conn, row, with_university=True):
    if row is None:
        return None
    d = dict(row)
    ns = SimpleNamespace(**d)
    for key in ("recommended_at", "reviewed_at", "created_at", "updated_at"):
        setattr(ns, key, _parse_dt(d.get(key)))
    ns.signal_list = []
    if d.get("signals"):
        try:
            ns.signal_list = json.loads(d["signals"])
        except (TypeError, ValueError):
            ns.signal_list = []
    if with_university:
        ns.university = hydrate_university(
            get_university_row(conn, d["university_id"]))
    return ns


def get_university_match(conn, match_id):
    return hydrate_university_match(
        conn, conn.execute(
            "SELECT * FROM challenge_university_matches WHERE id=?",
            (match_id,)).fetchone())


def list_university_matches_for_challenge(conn, challenge_id, status=None):
    if status:
        rows = conn.execute(
            "SELECT * FROM challenge_university_matches WHERE challenge_id=? "
            "AND status=? ORDER BY score DESC", (challenge_id, status)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM challenge_university_matches WHERE challenge_id=? "
            "ORDER BY "
            "CASE status WHEN 'RECOMMENDED' THEN 0 WHEN 'INVITED' THEN 1 "
            "WHEN 'ACCEPTED' THEN 2 WHEN 'DECLINED' THEN 3 ELSE 4 END, "
            "score DESC", (challenge_id,)).fetchall()
    return [hydrate_university_match(conn, r) for r in rows]


def list_university_matches_for_institution(conn, university_id, status=None):
    if status:
        rows = conn.execute(
            "SELECT cum.* FROM challenge_university_matches cum "
            "WHERE cum.university_id=? AND cum.status=? ORDER BY cum.recommended_at DESC",
            (university_id, status)).fetchall()
    else:
        rows = conn.execute(
            "SELECT cum.* FROM challenge_university_matches cum "
            "WHERE cum.university_id=? ORDER BY "
            "CASE cum.status WHEN 'INVITED' THEN 0 WHEN 'ACCEPTED' THEN 1 "
            "WHEN 'DECLINED' THEN 2 WHEN 'RECOMMENDED' THEN 3 ELSE 4 END, "
            "cum.score DESC", (university_id,)).fetchall()
    out = []
    for row in rows:
        ns = hydrate_university_match(conn, row, with_university=False)
        ns.challenge = hydrate_challenge(
            conn, get_challenge_row(conn, row["challenge_id"]),
            with_relations=False)
        if ns.challenge is None:
            continue
        out.append(ns)
    return out


def challenge_acceptance_summary(conn, challenge_id):
    """Universe-facing summary for a challenge: which institutions are
    currently invited / accepted (short names), for the command-centre table
    and gov challenge detail."""
    rows = conn.execute(
        "SELECT cum.status, u.short_name, u.name FROM challenge_university_matches cum "
        "JOIN universities u ON u.id=cum.university_id "
        "WHERE cum.challenge_id=? AND cum.status IN ('INVITED','ACCEPTED','DECLINED') "
        "ORDER BY cum.status, cum.reviewed_at NULLS LAST",
        (challenge_id,)).fetchall()
    summary = {"accepted": [], "invited": [], "declined": []}
    for r in rows:
        label = r["short_name"] or r["name"]
        if r["status"] == "ACCEPTED":
            summary["accepted"].append(label)
        elif r["status"] == "INVITED":
            summary["invited"].append(label)
        else:
            summary["declined"].append(label)
    return summary


def invite_university_match(conn, match_id, reviewed_by):
    """Government invites the recommended institution (RECOMMENDED -> INVITED)."""
    conn.execute(
        "UPDATE challenge_university_matches SET status='INVITED', "
        "reviewed_by=?, reviewed_at=?, updated_at=? WHERE id=? "
        "AND status='RECOMMENDED'",
        (reviewed_by, _now().isoformat(), _now().isoformat(), match_id))
    match = get_university_match(conn, match_id)
    if match:
        add_challenge_log(conn, match.challenge_id, "Updated",
                          f"University invited by government: "
                          f"{match.university.name if match.university else 'Institution'}.",
                          reviewed_by)
    conn.commit()
    return match


def remove_university_match(conn, match_id, reviewed_by, note=""):
    """Government removes a recommendation (RECOMMENDED/INVITED -> REMOVED)."""
    conn.execute(
        "UPDATE challenge_university_matches SET status='REMOVED', "
        "reviewed_by=?, reviewed_at=?, response_note=?, updated_at=? WHERE id=? "
        "AND status IN ('RECOMMENDED','INVITED')",
        (reviewed_by, _now().isoformat(), note or "", _now().isoformat(), match_id))
    match = get_university_match(conn, match_id)
    if match:
        add_challenge_log(conn, match.challenge_id, "Updated",
                          f"University recommendation removed by government: "
                          f"{match.university.name if match.university else 'Institution'}.",
                          reviewed_by)
    conn.commit()
    return match


def respond_university_match(conn, match_id, accept, response_note, actor_id):
    """University accepts (status ACCEPTED) or declines (status DECLINED)
    an invitation. A declined match leaves the challenge open for other
    institutions. Must be the university that owns the invitation."""
    if accept:
        new_status, note = "ACCEPTED", "University accepted the challenge."
    else:
        new_status, note = "DECLINED", "University declined the challenge."
    conn.execute(
        "UPDATE challenge_university_matches SET status=?, response_note=?, "
        "reviewed_by=?, reviewed_at=?, updated_at=? WHERE id=? "
        "AND status='INVITED'",
        (new_status, response_note or "", actor_id, _now().isoformat(),
         _now().isoformat(), match_id))
    match = get_university_match(conn, match_id)
    if match:
        uni_name = match.university.name if match.university else "Institution"
        add_challenge_log(conn, match.challenge_id, "Updated",
                          f"{uni_name} {note}" +
                          (f" Note: {response_note}" if response_note else ""),
                          actor_id)
    conn.commit()
    return match


def count_matching_ready(conn):
    return conn.execute(
        "SELECT COUNT(*) c FROM challenges WHERE status IN "
        + _sql_in(CHALLENGE_AWAITING_MATCH) +
        " AND id NOT IN (SELECT DISTINCT challenge_id FROM challenge_university_matches)",
        (*CHALLENGE_AWAITING_MATCH,)).fetchone()["c"]


def count_recommendations_pending_review(conn):
    return conn.execute(
        "SELECT COUNT(*) c FROM challenge_university_matches WHERE status='RECOMMENDED'"
    ).fetchone()["c"]


# ---------------------------------------------------------------------------
# Phase 4 — teams, proposals and projects
# ---------------------------------------------------------------------------

def challenge_accepted_by_university(conn, challenge_id, university_id):
    """True only when this university's match for this challenge is ACCEPTED.
    The single gate that unlocks team creation and proposal work."""
    return conn.execute(
        "SELECT 1 FROM challenge_university_matches "
        "WHERE challenge_id=? AND university_id=? AND status='ACCEPTED'",
        (challenge_id, university_id)).fetchone() is not None


def create_team(conn, challenge_id, university_id, name, description, created_by):
    cur = conn.execute(
        "INSERT INTO teams (challenge_id, university_id, name, description, "
        "status, created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (challenge_id, university_id, name, description or "", "FORMING",
         created_by, _now().isoformat(), _now().isoformat()))
    conn.commit()
    return cur.lastrowid


def get_team_row(conn, team_id):
    if team_id is None:
        return None
    return conn.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()


def get_team(conn, team_id):
    return hydrate_team(conn, get_team_row(conn, team_id))


def hydrate_team(conn, row, with_relations=True):
    if row is None:
        return None
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    ns.updated_at = _parse_dt(d.get("updated_at"))
    if with_relations:
        ns.challenge = hydrate_challenge(
            conn, get_challenge_row(conn, d["challenge_id"]), with_relations=False)
        ns.university = hydrate_university(get_university_row(conn, d["university_id"]))
        ns.members = list_team_members(conn, d["id"])
        ns.member_count = len(ns.members)
        ns.creator = hydrate_user(get_user_by_id(conn, d.get("created_by")))
        ns.proposals = list_proposals_for_team(conn, d["id"])
        ns.latest_proposal = ns.proposals[0] if ns.proposals else None
        ns.projects = list_projects_for_team(conn, d["id"])
        ns.accepted = challenge_accepted_by_university(
            conn, d["challenge_id"], d["university_id"])
    return ns


def set_team_status(conn, team_id, status, actor_id, note=""):
    status = status if status in TEAM_STATUSES else "ACTIVE"
    conn.execute("UPDATE teams SET status=?, updated_at=? WHERE id=?",
                 (status, _now().isoformat(), team_id))
    team = get_team_row(conn, team_id)
    if team:
        add_challenge_log(conn, team["challenge_id"], "Updated",
                          f"Team \"{team['name']}\" status changed to {status}."
                          + (f" {note}" if note else ""), actor_id)
    conn.commit()


def auto_team_status_on_participation(conn, team):
    """Phase 4 lifecycle auto-progress: as soon as a team has a member it is
    ACTIVE; once any of its proposals is submitted the team is SUBMITTED;
    once any proposal is APPROVED the team is COMPLETED."""
    members = conn.execute(
        "SELECT 1 FROM team_members WHERE team_id=? AND status='ACTIVE'",
        (team["id"],)).fetchone()
    submitted = conn.execute(
        "SELECT 1 FROM proposals WHERE team_id=? AND status IN "
        "('SUBMITTED','UNDER_REVIEW','REVISION_REQUESTED','APPROVED')",
        (team["id"],)).fetchone()
    approved = conn.execute(
        "SELECT 1 FROM proposals WHERE team_id=? AND status='APPROVED'",
        (team["id"],)).fetchone()
    if approved:
        new_status = "COMPLETED"
    elif submitted:
        new_status = "SUBMITTED"
    elif members:
        new_status = "ACTIVE"
    else:
        new_status = "FORMING"
    if new_status != team["status"]:
        conn.execute("UPDATE teams SET status=?, updated_at=? WHERE id=?",
                     (new_status, _now().isoformat(), team["id"]))


def list_teams_for_university(conn, university_id):
    rows = conn.execute(
        "SELECT * FROM teams WHERE university_id=? ORDER BY updated_at DESC",
        (university_id,)).fetchall()
    return [hydrate_team(conn, r) for r in rows]


def list_teams_for_challenge(conn, challenge_id):
    rows = conn.execute(
        "SELECT * FROM teams WHERE challenge_id=? ORDER BY created_at ASC",
        (challenge_id,)).fetchall()
    return [hydrate_team(conn, r) for r in rows]


def list_teams_for_user(conn, user_id, university_id=None):
    """Teams the user is an active member of, newest first."""
    rows = conn.execute(
        "SELECT t.* FROM teams t JOIN team_members tm ON tm.team_id=t.id "
        "WHERE tm.user_id=? AND tm.status='ACTIVE' ORDER BY t.updated_at DESC",
        (user_id,)).fetchall()
    teams = [hydrate_team(conn, r) for r in rows]
    if not teams:
        return teams
    if university_id is not None:
        teams = [t for t in teams if t.university_id == university_id]
    return teams


# ---------------------------------------------------------------------------
# team members
# ---------------------------------------------------------------------------

def add_team_member(conn, team_id, user_id, member_role):
    """Idempotent membership: a user can never join the same team twice."""
    member_role = member_role if member_role in TEAM_MEMBER_ROLES else "STUDENT"
    existing = conn.execute(
        "SELECT id, status FROM team_members WHERE team_id=? AND user_id=?",
        (team_id, user_id)).fetchone()
    if existing:
        if existing["status"] != "ACTIVE":
            conn.execute("UPDATE team_members SET status='ACTIVE', "
                         "member_role=?, joined_at=? WHERE id=?",
                         (member_role, _now().isoformat(), existing["id"]))
        return existing["id"]
    cur = conn.execute(
        "INSERT INTO team_members (team_id, user_id, member_role, joined_at, status) "
        "VALUES (?,?,?,?,?)",
        (team_id, user_id, member_role, _now().isoformat(), "ACTIVE"))
    team = get_team_row(conn, team_id)
    if team:
        auto_team_status_on_participation(conn, team)
        member = hydrate_user(get_user_by_id(conn, user_id))
        add_challenge_log(conn, team["challenge_id"], "Updated",
                          f"{member.name if member else 'Member'} joined team "
                          f"\"{team['name']}\" as {member_role}.", None)
    conn.commit()
    return cur.lastrowid


def get_team_member(conn, team_id, user_id):
    return conn.execute(
        "SELECT * FROM team_members WHERE team_id=? AND user_id=?", 
        (team_id, user_id)).fetchone()


def update_team_member_role(conn, team_id, user_id, member_role):
    """Role change for an existing member (e.g. demoting a former faculty lead)."""
    if member_role not in TEAM_MEMBER_ROLES:
        return False
    cur = conn.execute(
        "UPDATE team_members SET member_role=? "
        "WHERE team_id=? AND user_id=? AND status='ACTIVE'",
        (member_role, team_id, user_id))
    conn.commit()
    return cur.rowcount > 0


def list_university_members(conn, university_id, team_id=None):
    """Faculty + students of an institution, for team building. Includes a
    convenience in_team flag when a team is given. Never leaks citizen data."""
    rows = conn.execute(
        "SELECT u.id AS user_id, u.name AS name, u.role AS role, u.email AS email, "
        "f.department AS department, f.designation AS designation, "
        "NULL AS course, f.expertise AS detail "
        "FROM faculty f JOIN users u ON u.id=f.user_id WHERE f.university_id=? "
        "UNION ALL "
        "SELECT u.id, u.name, u.role, u.email, s.department AS department, "
        "NULL AS designation, s.course AS course, s.skills AS detail "
        "FROM students s JOIN users u ON u.id=s.user_id WHERE s.university_id=? "
        "ORDER BY role, name",
        (university_id, university_id)).fetchall()
    out = []
    for r in rows:
        ns = SimpleNamespace(**dict(r))
        ns.in_team = bool(team_id and conn.execute(
            "SELECT 1 FROM team_members WHERE team_id=? AND user_id=? "
            "AND status='ACTIVE'", (team_id, r["user_id"])).fetchone())
        out.append(ns)
    return out


def list_team_members(conn, team_id):
    rows = conn.execute(
        "SELECT tm.*, u.name, u.email, u.role, "
        "COALESCE(f.department, s.department) AS department, "
        "s.course AS course "
        "FROM team_members tm "
        "JOIN users u ON u.id=tm.user_id "
        "LEFT JOIN faculty f ON f.user_id=tm.user_id "
        "LEFT JOIN students s ON s.user_id=tm.user_id "
        "WHERE tm.team_id=? AND tm.status='ACTIVE' "
        "ORDER BY CASE tm.member_role WHEN 'FACULTY_LEAD' THEN 0 "
        "WHEN 'TEAM_LEAD' THEN 1 WHEN 'FACULTY' THEN 2 ELSE 3 END, tm.joined_at",
        (team_id,)).fetchall()
    out = []
    for r in rows:
        ns = SimpleNamespace(**dict(r))
        ns.joined_at = _parse_dt(r["joined_at"])
        out.append(ns)
    return out


def remove_team_member(conn, team_id, user_id, actor_id):
    conn.execute("UPDATE team_members SET status='REMOVED' "
                 "WHERE team_id=? AND user_id=? AND status='ACTIVE'",
                 (team_id, user_id))
    team = get_team_row(conn, team_id)
    member = hydrate_user(get_user_by_id(conn, user_id))
    if team:
        add_challenge_log(conn, team["challenge_id"], "Updated",
                          f"{member.name if member else 'Member'} removed from team "
                          f"\"{team['name']}\".", actor_id)
    conn.commit()


# ---------------------------------------------------------------------------
# proposals
# ---------------------------------------------------------------------------

def create_proposal(conn, challenge_id, university_id, team_id, title,
                    problem_statement, proposed_solution, methodology,
                    expected_outcome="", required_resources="",
                    estimated_duration="", created_by=None):
    cur = conn.execute(
        "INSERT INTO proposals (challenge_id, university_id, team_id, title, "
        "problem_statement, proposed_solution, methodology, expected_outcome, "
        "required_resources, estimated_duration, submitted_by, status, "
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (challenge_id, university_id, team_id, title, problem_statement,
         proposed_solution, methodology, expected_outcome, required_resources,
         estimated_duration, created_by, "DRAFT",
         _now().isoformat(), _now().isoformat()))
    add_proposal_log(conn, cur.lastrowid, "CREATED", None, "DRAFT",
                     created_by, "Proposal draft created.")
    conn.commit()
    return cur.lastrowid


def get_proposal_row(conn, proposal_id):
    if proposal_id is None:
        return None
    return conn.execute("SELECT * FROM proposals WHERE id=?",
                        (proposal_id,)).fetchone()


def get_proposal(conn, proposal_id):
    return hydrate_proposal(conn, get_proposal_row(conn, proposal_id))


def hydrate_proposal(conn, row, with_relations=True):
    if row is None:
        return None
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    ns.updated_at = _parse_dt(d.get("updated_at"))
    ns.reviewed_at = _parse_dt(d.get("reviewed_at"))
    ns.is_draft = d.get("status") == "DRAFT"
    ns.is_marker = d.get("status") in PROPOSAL_MARKER_STATUSES
    ns.is_approved = d.get("status") == "APPROVED"
    if with_relations:
        ns.challenge = hydrate_challenge(
            conn, get_challenge_row(conn, d["challenge_id"]), with_relations=False)
        ns.university = hydrate_university(get_university_row(conn, d["university_id"]))
        ns.team = hydrate_team(
            conn, get_team_row(conn, d["team_id"]), with_relations=False)
        ns.submitter = hydrate_user(get_user_by_id(conn, d.get("submitted_by")))
        ns.reviewer = hydrate_user(get_user_by_id(conn, d.get("reviewed_by")))
        ns.logs = [hydrate_proposal_log(r) for r in conn.execute(
            "SELECT * FROM proposal_logs WHERE proposal_id=? ORDER BY created_at ASC",
            (d["id"],)).fetchall()]
        ns.projects = list_projects_for_proposal(conn, d["id"])
    return ns


def add_proposal_log(conn, proposal_id, action, old_status, new_status,
                     performed_by, comment=""):
    conn.execute(
        "INSERT INTO proposal_logs (proposal_id, action, old_status, new_status, "
        "performed_by, comment, created_at) VALUES (?,?,?,?,?,?,?)",
        (proposal_id, action, old_status, new_status, performed_by, comment or "",
         _now().isoformat()))


def hydrate_proposal_log(row):
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    return ns


def update_proposal(conn, proposal_id, actor_id, **fields):
    fields["updated_at"] = _now().isoformat()
    set_clause = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE proposals SET {set_clause} WHERE id=?",
                 (*fields.values(), proposal_id))
    add_proposal_log(conn, proposal_id, "UPDATED",
                     None, None, actor_id, "Proposal details updated.")
    conn.commit()


def submit_proposal(conn, proposal_id, actor_id):
    """DRAFT -> SUBMITTED. A REVISION_REQUESTED proposal goes straight back
    UNDER_REVIEW so the reviewer who already holds the context can re-check."""
    row = get_proposal_row(conn, proposal_id)
    if row is None:
        raise ValueError("Proposal not found.")
    if row["status"] == "DRAFT":
        old_status, new_status = "DRAFT", "SUBMITTED"
    elif row["status"] == "REVISION_REQUESTED":
        old_status, new_status = "REVISION_REQUESTED", "UNDER_REVIEW"
    else:
        raise ValueError("This proposal is not in a submittable state.")
    conn.execute("UPDATE proposals SET status=?, submitted_by=?, updated_at=? "
                 "WHERE id=?", (new_status, actor_id, _now().isoformat(), proposal_id))
    add_proposal_log(conn, proposal_id, "SUBMITTED", old_status, new_status,
                     actor_id, "Proposal submitted for government review.")
    team = get_team_row(conn, row["team_id"])
    if team:
        auto_team_status_on_participation(conn, team)
        add_challenge_log(conn, team["challenge_id"], "Updated",
                          f"Proposal submitted for team \"{team['name']}\".", actor_id)
    conn.commit()
    return new_status


def begin_proposal_review(conn, proposal_id, actor_id):
    """SUBMITTED -> UNDER_REVIEW (reviewer takes up the proposal)."""
    row = get_proposal_row(conn, proposal_id)
    if row is None or row["status"] != "SUBMITTED":
        raise ValueError("Only a submitted proposal can begin review.")
    conn.execute("UPDATE proposals SET status='UNDER_REVIEW', updated_at=? WHERE id=?",
                 (_now().isoformat(), proposal_id))
    add_proposal_log(conn, proposal_id, "REVIEW_STARTED",
                     "SUBMITTED", "UNDER_REVIEW", actor_id,
                     "Government reviewer began assessing the proposal.")
    conn.commit()
    return "UNDER_REVIEW"


def review_proposal(conn, proposal_id, decision, comment, actor_id):
    """Government verdict: REVISION_REQUESTED / APPROVED / REJECTED.
    Allowed from SUBMITTED or UNDER_REVIEW. Logs the transition."""
    decision = decision if decision in PROPOSAL_FEEDBACK_STATUSES else None
    if decision is None:
        raise ValueError("Unknown review decision.")
    row = get_proposal_row(conn, proposal_id)
    if row is None:
        raise ValueError("Proposal not found.")
    if row["status"] not in PROPOSAL_MARKER_STATUSES:
        raise ValueError("Review is only possible on a submitted proposal "
                         "that is currently under review.")
    old_status = row["status"]
    conn.execute(
        "UPDATE proposals SET status=?, review_comment=?, reviewed_by=?, "
        "reviewed_at=?, updated_at=? WHERE id=?",
        (decision, comment or "", actor_id, _now().isoformat(),
         _now().isoformat(), proposal_id))
    action = {"REVISION_REQUESTED": "REVISION_REQUESTED",
              "APPROVED": "APPROVED", "REJECTED": "REJECTED"}[decision]
    add_proposal_log(conn, proposal_id, action, old_status, decision, actor_id,
                     comment or "")
    team = get_team_row(conn, row["team_id"])
    if team:
        auto_team_status_on_participation(conn, team)
    conn.commit()
    return decision


def list_proposals_for_team(conn, team_id):
    rows = conn.execute(
        "SELECT * FROM proposals WHERE team_id=? ORDER BY updated_at DESC",
        (team_id,)).fetchall()
    return [hydrate_proposal(conn, r) for r in rows]


def list_proposals_for_challenge(conn, challenge_id):
    rows = conn.execute(
        "SELECT * FROM proposals WHERE challenge_id=? ORDER BY updated_at DESC",
        (challenge_id,)).fetchall()
    return [hydrate_proposal(conn, r) for r in rows]


def list_proposals_for_university(conn, university_id):
    rows = conn.execute(
        "SELECT * FROM proposals WHERE university_id=? ORDER BY updated_at DESC",
        (university_id,)).fetchall()
    return [hydrate_proposal(conn, r) for r in rows]


def list_proposals_for_mode(conn, mode):
    """Review-board lists keyed by phase: all / review / decided."""
    if mode == "review":
        q = ("SELECT * FROM proposals WHERE status IN "
             + _sql_in(PROPOSAL_MARKER_STATUSES) + " ORDER BY updated_at DESC")
        args = (*PROPOSAL_MARKER_STATUSES,)
    elif mode == "decided":
        q = ("SELECT * FROM proposals WHERE status IN "
             + _sql_in(PROPOSAL_FEEDBACK_STATUSES) + " ORDER BY reviewed_at DESC")
        args = (*PROPOSAL_FEEDBACK_STATUSES,)
    else:
        q = "SELECT * FROM proposals ORDER BY updated_at DESC"
        args = ()
    rows = conn.execute(q, args).fetchall()
    return [hydrate_proposal(conn, r) for r in rows]


def count_proposals_needing_review(conn):
    return conn.execute(
        "SELECT COUNT(*) c FROM proposals WHERE status IN "
        + _sql_in(PROPOSAL_MARKER_STATUSES),
        (*PROPOSAL_MARKER_STATUSES,)).fetchone()["c"]


def list_proposals_for_user(conn, user_id):
    """Every proposal belonging to teams the user is an active member of."""
    rows = conn.execute(
        "SELECT p.* FROM proposals p JOIN team_members tm ON tm.team_id=p.team_id "
        "WHERE tm.user_id=? AND tm.status='ACTIVE' ORDER BY p.updated_at DESC",
        (user_id,)).fetchall()
    return [hydrate_proposal(conn, r) for r in rows]


# ---------------------------------------------------------------------------
# projects
# ---------------------------------------------------------------------------

def create_project_from_proposal(conn, proposal, title, start_date,
                                 target_end_date, created_by, description=""):
    """Create a project only from an APPROVED proposal. Rows enforce the
    challenge / university / team chain; the proposal link keeps the audit."""
    if proposal is None:
        raise ValueError("Proposal not found.")
    if proposal.status != "APPROVED":
        raise ValueError("Only an approved proposal can become a project.")
    existing = conn.execute("SELECT 1 FROM projects WHERE proposal_id=?",
                            (proposal.id,)).fetchone()
    if existing:
        raise ValueError("A project already exists for this proposal.")
    cur = conn.execute(
        "INSERT INTO projects (challenge_id, university_id, team_id, proposal_id, "
        "title, description, status, start_date, target_end_date, created_by, "
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (proposal.challenge_id, proposal.university_id, proposal.team_id,
         proposal.id, title, description or "", "CREATED",
         start_date or _now().date().isoformat(), target_end_date or "",
         created_by, _now().isoformat(), _now().isoformat()))
    add_proposal_log(conn, proposal.id, "PROJECT_CREATED",
                     "APPROVED", "APPROVED", created_by,
                     f"Project created from approved proposal: {title}.")
    team = get_team_row(conn, proposal.team_id)
    if team:
        add_challenge_log(conn, team["challenge_id"], "IN_PROJECT",
                          f"Project \"{title}\" created for team "
                          f"\"{team['name']}\".", created_by)
        auto_team_status_on_participation(conn, team)
        row = get_challenge_row(conn, team["challenge_id"])
        if row and row["status"] in ("VALIDATED", "READY_FOR_MATCHING"):
            conn.execute(
                "UPDATE challenges SET status='IN_PROJECT', updated_at=? WHERE id=?",
                (_now().isoformat(), team["challenge_id"]))
    conn.commit()
    return cur.lastrowid


def get_project_row(conn, project_id):
    if project_id is None:
        return None
    return conn.execute("SELECT * FROM projects WHERE id=?",
                        (project_id,)).fetchone()


def get_project(conn, project_id):
    return hydrate_project(conn, get_project_row(conn, project_id))


def hydrate_project(conn, row, with_relations=True):
    if row is None:
        return None
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    ns.updated_at = _parse_dt(d.get("updated_at"))
    ns.start_date = _parse_dt(d.get("start_date"))
    ns.target_end_date = (_parse_dt(d.get("target_end_date"))
                          if d.get("target_end_date") else None)
    if with_relations:
        ns.challenge = hydrate_challenge(
            conn, get_challenge_row(conn, d["challenge_id"]), with_relations=False)
        ns.university = hydrate_university(get_university_row(conn, d["university_id"]))
        ns.team = hydrate_team(
            conn, get_team_row(conn, d["team_id"]), with_relations=False)
        ns.proposal = hydrate_proposal(
            conn, get_proposal_row(conn, d["proposal_id"]), with_relations=False)
    return ns


def set_project_status(conn, project_id, status, actor_id, note=""):
    status = status if status in PROJECT_STATUSES else "ACTIVE"
    conn.execute("UPDATE projects SET status=?, updated_at=? WHERE id=?",
                 (status, _now().isoformat(), project_id))
    project = get_project_row(conn, project_id)
    if project:
        add_challenge_log(conn, project["challenge_id"], "Updated",
                          f"Project \"{project['title']}\" status changed to "
                          f"{status}." + (f" {note}" if note else ""), actor_id)
    conn.commit()


def list_projects_for_team(conn, team_id):
    rows = conn.execute("SELECT * FROM projects WHERE team_id=? "
                        "ORDER BY created_at ASC", (team_id,)).fetchall()
    return [hydrate_project(conn, r) for r in rows]


def list_projects_for_university(conn, university_id):
    rows = conn.execute("SELECT * FROM projects WHERE university_id=? "
                        "ORDER BY created_at DESC", (university_id,)).fetchall()
    return [hydrate_project(conn, r) for r in rows]


def list_projects_for_challenge(conn, challenge_id):
    rows = conn.execute("SELECT * FROM projects WHERE challenge_id=? "
                        "ORDER BY created_at ASC", (challenge_id,)).fetchall()
    return [hydrate_project(conn, r) for r in rows]


def list_projects_for_proposal(conn, proposal_id):
    rows = conn.execute("SELECT * FROM projects WHERE proposal_id=? "
                        "ORDER BY created_at ASC", (proposal_id,)).fetchall()
    return [hydrate_project(conn, r, with_relations=False) for r in rows]


def list_projects_for_user(conn, user_id):
    rows = conn.execute(
        "SELECT p.* FROM projects p JOIN team_members tm ON tm.team_id=p.team_id "
        "WHERE tm.user_id=? AND tm.status='ACTIVE' ORDER BY p.created_at DESC",
        (user_id,)).fetchall()
    return [hydrate_project(conn, r) for r in rows]


def challenge_lifecycle(conn, challenge_id):
    """Phase 4 status snapshot for a challenge, used by the Command Center and
    the university portal: accepted institution, teams, proposals and projects
    in a single ordered structure."""
    matches = list_university_matches_for_challenge(conn, challenge_id)
    accepted = [m for m in matches if m.status == "ACCEPTED"]
    teams = list_teams_for_challenge(conn, challenge_id)
    proposals = list_proposals_for_challenge(conn, challenge_id)
    projects = list_projects_for_challenge(conn, challenge_id)
    return {
        "accepted": accepted,
        "teams": teams,
        "proposals": proposals,
        "projects": projects,
        "has_teams": bool(teams),
        "has_proposals": bool(proposals),
        "has_projects": bool(projects),
    }


def attach_lifecycle(conn, challenges):
    """Attach .lifecycle to a list of challenge objects (dashboard rows)."""
    for ch in challenges:
        ch.lifecycle = challenge_lifecycle(conn, ch.id)
