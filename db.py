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

ROLES = ("citizen", "officer", "admin", "university", "faculty", "student",
         "industry")
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

# Phase 5 — industry / startup / MSME collaboration & funding.
INDUSTRY_ORG_TYPES = ("INDUSTRY", "STARTUP", "MSME", "CSR", "RESEARCH_LAB",
                      "TECHNOLOGY_PROVIDER")
INDUSTRY_VERIFICATION_STATUSES = ("PENDING", "VERIFIED", "REJECTED")
COLLABORATION_TYPES = ("TECHNICAL_SUPPORT", "FUNDING", "MENTORSHIP", "EQUIPMENT",
                       "INFRASTRUCTURE", "DATA", "SOFTWARE", "TESTING_SUPPORT",
                       "INDUSTRY_EXPERTISE")
COLLABORATION_STATUSES = ("INTERESTED", "SUBMITTED", "UNDER_REVIEW",
                          "ACCEPTED", "REVISION_REQUESTED", "REJECTED")
# Collaboration requests that still need government attention.
COLLABORATION_MARKER_STATUSES = ("SUBMITTED", "UNDER_REVIEW")
# Collaboration statuses that carry a government verdict + feedback comment.
COLLABORATION_FEEDBACK_STATUSES = ("ACCEPTED", "REVISION_REQUESTED", "REJECTED")
COLLABORATION_ORDER = {
    "INTERESTED": 0, "SUBMITTED": 1, "UNDER_REVIEW": 2, "ACCEPTED": 3,
    "REVISION_REQUESTED": 4, "REJECTED": 5, None: 6,
}
FUNDING_TYPES = ("GRANT", "CSR", "SPONSORSHIP", "IN_KIND")
FUNDING_STATUSES = ("PROPOSED", "APPROVED", "DECLINED", "DISBURSEMENT_PENDING")
COLLABORATION_CONNECT_STATUSES = ("CONNECTED", "ACTIVE", "COMPLETED", "DISENGAGED")

# Phase 6 — project lifecycle: prototype → testing → pilot → deployment.
# Each stage follows the collaboration pattern: a government review verdict +
# feedback comment, an audit log table, and marker statuses that still need
# government attention. DEPLOYED is the terminal, honest platform state — it
# only ever means an authorized reviewer completed the deployment review.
PROTOTYPE_STATUSES = ("SUBMITTED", "UNDER_REVIEW", "APPROVED",
                      "REVISION_REQUESTED")
PROTOTYPE_MARKER_STATUSES = ("SUBMITTED", "UNDER_REVIEW")
PROTOTYPE_FEEDBACK_STATUSES = ("APPROVED", "REVISION_REQUESTED")
TESTING_STATUSES = ("SUBMITTED", "UNDER_REVIEW", "APPROVED",
                    "REVISION_REQUESTED")
TESTING_MARKER_STATUSES = ("SUBMITTED", "UNDER_REVIEW")
TESTING_FEEDBACK_STATUSES = ("APPROVED", "REVISION_REQUESTED")
TESTING_RESULT_STATUSES = ("PASS", "FAIL", "PENDING")
PILOT_STATUSES = ("PLANNED", "ACTIVE", "COMPLETED", "DEPLOYED")
PILOT_ACTIVE_STATUSES = ("PLANNED", "ACTIVE", "COMPLETED")

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

CREATE TABLE IF NOT EXISTS industry_organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,
    short_name TEXT,
    legal_entity_name TEXT,
    org_type TEXT NOT NULL DEFAULT 'INDUSTRY',
    sector TEXT,
    core_expertise TEXT,
    technologies TEXT,
    capabilities TEXT,
    email TEXT,
    phone TEXT,
    address TEXT,
    district TEXT,
    city TEXT,
    website TEXT,
    description TEXT,
    verification_status TEXT NOT NULL DEFAULT 'PENDING',
    verification_note TEXT,
    verified_by INTEGER,
    verified_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id),
    FOREIGN KEY(verified_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS collaboration_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    organization_id INTEGER NOT NULL,
    requested_by INTEGER NOT NULL,
    collaboration_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    expected_support TEXT,
    proposed_amount REAL,
    currency TEXT NOT NULL DEFAULT 'INR',
    funding_type TEXT,
    funding_description TEXT,
    status TEXT NOT NULL DEFAULT 'INTERESTED',
    review_comment TEXT,
    reviewed_by INTEGER,
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id),
    FOREIGN KEY(organization_id) REFERENCES industry_organizations(id),
    FOREIGN KEY(requested_by) REFERENCES users(id),
    FOREIGN KEY(reviewed_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS collaboration_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT,
    performed_by INTEGER,
    comment TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(request_id) REFERENCES collaboration_requests(id),
    FOREIGN KEY(performed_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS project_collaborations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    organization_id INTEGER NOT NULL,
    request_id INTEGER NOT NULL UNIQUE,
    agreed_support TEXT,
    approved_amount REAL,
    funding_status TEXT NOT NULL DEFAULT 'PROPOSED',
    start_date TEXT,
    target_end_date TEXT,
    status TEXT NOT NULL DEFAULT 'CONNECTED',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id),
    FOREIGN KEY(organization_id) REFERENCES industry_organizations(id),
    FOREIGN KEY(request_id) REFERENCES collaboration_requests(id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    ref_type TEXT,
    ref_id INTEGER,
    read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

-- Phase 6 — prototype / testing / pilot / deployment lifecycle. One record
-- per project keeps the stage linear; revisions are in-place resubmissions
-- that the government reviews again. All transitions are guarded in Python.
CREATE TABLE IF NOT EXISTS project_prototypes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL UNIQUE,
    description TEXT NOT NULL,
    progress_update TEXT NOT NULL DEFAULT '',
    version TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'SUBMITTED',
    submitted_by INTEGER NOT NULL,
    submitted_at TEXT NOT NULL,
    reviewer_comment TEXT,
    reviewed_by INTEGER,
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id),
    FOREIGN KEY(submitted_by) REFERENCES users(id),
    FOREIGN KEY(reviewed_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS prototype_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prototype_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT,
    performed_by INTEGER,
    comment TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(prototype_id) REFERENCES project_prototypes(id),
    FOREIGN KEY(performed_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS testing_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL UNIQUE,
    prototype_id INTEGER NOT NULL,
    objective TEXT NOT NULL,
    test_description TEXT NOT NULL,
    expected_result TEXT NOT NULL,
    actual_result TEXT NOT NULL,
    test_result TEXT NOT NULL DEFAULT 'PENDING',
    issues_findings TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'SUBMITTED',
    reviewer_comment TEXT,
    submitted_by INTEGER NOT NULL,
    submitted_at TEXT NOT NULL,
    reviewed_by INTEGER,
    reviewed_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id),
    FOREIGN KEY(prototype_id) REFERENCES project_prototypes(id),
    FOREIGN KEY(submitted_by) REFERENCES users(id),
    FOREIGN KEY(reviewed_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS pilot_deployments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL UNIQUE,
    district TEXT NOT NULL,
    location TEXT,
    target_community TEXT,
    objectives TEXT NOT NULL DEFAULT '',
    start_date TEXT,
    target_end_date TEXT,
    responsible_org TEXT,
    status TEXT NOT NULL DEFAULT 'PLANNED',
    progress_updates TEXT NOT NULL DEFAULT '',
    deployment_review_comment TEXT,
    reviewed_by INTEGER,
    reviewed_at TEXT,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(project_id) REFERENCES projects(id),
    FOREIGN KEY(reviewed_by) REFERENCES users(id),
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
    and projects report from the Phase 4 tables; prototype/testing/pilot/
    deployed counts report from Phase 6 tables as stages actually progress."""
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
        "prototype_reviews": conn.execute(
            "SELECT COUNT(*) c FROM project_prototypes WHERE status IN "
            + _sql_in(PROTOTYPE_MARKER_STATUSES),
            (*PROTOTYPE_MARKER_STATUSES,)).fetchone()["c"],
        "testing_reviews": conn.execute(
            "SELECT COUNT(*) c FROM testing_reports WHERE status IN "
            + _sql_in(TESTING_MARKER_STATUSES),
            (*TESTING_MARKER_STATUSES,)).fetchone()["c"],
        "pilot_projects": conn.execute(
            "SELECT COUNT(*) c FROM pilot_deployments WHERE status IN "
            + _sql_in(PILOT_ACTIVE_STATUSES),
            (*PILOT_ACTIVE_STATUSES,)).fetchone()["c"],
        "deployed_solutions": conn.execute(
            "SELECT COUNT(*) c FROM pilot_deployments WHERE status='DEPLOYED'"
        ).fetchone()["c"],
        "industry_organizations": count_industry_organizations(conn),
        "industry_verified": count_industry_organizations(conn, "VERIFIED"),
        "industry_pending": count_industry_organizations(conn, "PENDING"),
        "collab_reviews": count_collaborations_needing_review(conn),
        "collab_accepted": conn.execute(
            "SELECT COUNT(*) c FROM collaboration_requests "
            "WHERE status='ACCEPTED'").fetchone()["c"],
    }


def command_center_actions(conn):
    """Action Required panel counts — every value derived from live data.
    Phase 6 stages (prototype/testing approval, pilot evaluation, overdue
    pilot milestones) report from their tables; nothing is an empty future
    count anymore."""
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
        "industry_verifications_pending": count_industry_organizations(conn, "PENDING"),
        "collab_requests_review": count_collaborations_needing_review(conn),
        "prototypes_needing_review": conn.execute(
            "SELECT COUNT(*) c FROM project_prototypes WHERE status IN "
            + _sql_in(PROTOTYPE_MARKER_STATUSES),
            (*PROTOTYPE_MARKER_STATUSES,)).fetchone()["c"],
        "testing_needing_review": conn.execute(
            "SELECT COUNT(*) c FROM testing_reports WHERE status IN "
            + _sql_in(TESTING_MARKER_STATUSES),
            (*TESTING_MARKER_STATUSES,)).fetchone()["c"],
        "pilots_needing_evaluation": conn.execute(
            "SELECT COUNT(*) c FROM pilot_deployments WHERE status='COMPLETED'"
        ).fetchone()["c"],
        "pilots_overdue": conn.execute(
            "SELECT COUNT(*) c FROM pilot_deployments WHERE status IN "
            + _sql_in(("PLANNED", "ACTIVE"))
            + " AND target_end_date IS NOT NULL AND target_end_date < ?",
            (*("PLANNED", "ACTIVE"), _now().date().isoformat())).fetchone()["c"],
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


# ---------------------------------------------------------------------------
# Phase 5 — industry / startup / MSME organizations
# ---------------------------------------------------------------------------

def list_user_ids_by_role(conn, role):
    rows = conn.execute("SELECT id FROM users WHERE role=?",
                        (role,)).fetchall()
    return [r["id"] for r in rows]


def create_industry_organization(conn, user_id, name, org_type="INDUSTRY",
                                 short_name=None, legal_entity_name=None,
                                 sector=None, core_expertise=None,
                                 technologies=None, capabilities=None,
                                 email=None, phone=None, address=None,
                                 district=None, city=None, website=None,
                                 description=None):
    """One industry account owns exactly one organization profile."""
    cur = conn.execute(
        "INSERT INTO industry_organizations (user_id, name, short_name, "
        "legal_entity_name, org_type, sector, core_expertise, technologies, "
        "capabilities, email, phone, address, district, city, website, "
        "description, verification_status, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (user_id, name, short_name, legal_entity_name,
         org_type, sector, core_expertise, technologies, capabilities,
         email, phone, address, district, city, website, description,
         "PENDING", _now().isoformat(), _now().isoformat()))
    conn.commit()
    return cur.lastrowid


def get_industry_organization_row(conn, org_id):
    if org_id is None:
        return None
    return conn.execute("SELECT * FROM industry_organizations WHERE id=?",
                        (org_id,)).fetchone()


def hydrate_industry_organization(conn, row, with_relations=True):
    if row is None:
        return None
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    ns.updated_at = _parse_dt(d.get("updated_at"))
    ns.verified_at = _parse_dt(d.get("verified_at"))
    ns.is_verified = d.get("verification_status") == "VERIFIED"
    ns.is_pending = d.get("verification_status") == "PENDING"
    ns.is_rejected = d.get("verification_status") == "REJECTED"
    if with_relations:
        ns.owner = hydrate_user(get_user_by_id(conn, d.get("user_id")))
        ns.verifier = hydrate_user(get_user_by_id(conn, d.get("verified_by")))
        ns.collaborations = list_collaborations_for_org(conn, d["id"])
    return ns


def get_industry_organization(conn, org_id):
    return hydrate_industry_organization(
        conn, get_industry_organization_row(conn, org_id))


def get_organization_for_user(conn, user):
    """The industry profile linked to a logged-in industry account, or None."""
    if user is None or user.role != "industry":
        return None
    row = conn.execute(
        "SELECT * FROM industry_organizations WHERE user_id=?",
        (user.id,)).fetchone()
    return hydrate_industry_organization(conn, row)


ORG_EDITABLE_FIELDS = (
    "name", "short_name", "legal_entity_name", "org_type", "sector",
    "core_expertise", "technologies", "capabilities", "email", "phone",
    "address", "district", "city", "website", "description")


def update_industry_organization(conn, org_id, **fields):
    allowed = {k: v for k, v in fields.items() if k in ORG_EDITABLE_FIELDS}
    if not allowed:
        return
    allowed["updated_at"] = _now().isoformat()
    set_clause = ", ".join(f"{k}=?" for k in allowed)
    conn.execute(f"UPDATE industry_organizations SET {set_clause} WHERE id=?",
                 (*allowed.values(), org_id))
    conn.commit()


def list_industry_organizations(conn, verification=None, org_type=None):
    q = "SELECT * FROM industry_organizations"
    args = []
    conds = []
    if verification:
        conds.append("verification_status=?")
        args.append(verification)
    if org_type:
        conds.append("org_type=?")
        args.append(org_type)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY updated_at DESC"
    rows = conn.execute(q, args).fetchall()
    return [hydrate_industry_organization(conn, r) for r in rows]


def verify_industry_organization(conn, org_id, verdict, note, verifier_id):
    """Government verdict on an organization profile: PENDING -> VERIFIED
    or REJECTED. Only an un-reviewed profile can be actioned."""
    verdict = verdict if verdict in INDUSTRY_VERIFICATION_STATUSES else None
    if verdict in (None, "PENDING"):
        raise ValueError("Unknown verification verdict.")
    row = get_industry_organization_row(conn, org_id)
    if row is None:
        raise ValueError("Organization not found.")
    if row["verification_status"] != "PENDING":
        raise ValueError("Only a pending organization can be verified or rejected.")
    conn.execute(
        "UPDATE industry_organizations SET verification_status=?, "
        "verification_note=?, verified_by=?, verified_at=?, updated_at=? "
        "WHERE id=?",
        (verdict, note or "", verifier_id, _now().isoformat(),
         _now().isoformat(), org_id))
    add_notification(conn, row["user_id"], "organization",
                     ("notif_org_verified" if verdict == "VERIFIED"
                      else "notif_org_rejected"),
                     f"Government reviewed your organization profile."
                     + (f" Note: {note}" if note else ""),
                     "organization", org_id)
    conn.commit()
    return get_industry_organization_row(conn, org_id)


def count_industry_organizations(conn, verification=None):
    if verification:
        return conn.execute(
            "SELECT COUNT(*) c FROM industry_organizations "
            "WHERE verification_status=?", (verification,)).fetchone()["c"]
    return conn.execute(
        "SELECT COUNT(*) c FROM industry_organizations").fetchone()["c"]


# ---------------------------------------------------------------------------
# Phase 5 — notifications feed (industry / university / government)
# ---------------------------------------------------------------------------

def add_notification(conn, user_id, kind, title, body="",
                     ref_type=None, ref_id=None):
    conn.execute(
        "INSERT INTO notifications (user_id, kind, title, body, ref_type, "
        "ref_id, read, created_at) VALUES (?,?,?,?,?,?,0,?)",
        (user_id, kind, title, body or "", ref_type, ref_id, _now().isoformat()))


def hydrate_notification(row):
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    ns.is_read = bool(d.get("read"))
    return ns


def list_notifications(conn, user_id, limit=50):
    rows = conn.execute(
        "SELECT * FROM notifications WHERE user_id=? "
        "ORDER BY created_at DESC LIMIT ?", (user_id, limit)).fetchall()
    return [hydrate_notification(r) for r in rows]


def unread_notification_count(conn, user_id):
    return conn.execute(
        "SELECT COUNT(*) c FROM notifications WHERE user_id=? AND read=0",
        (user_id,)).fetchone()["c"]


def mark_notification_read(conn, notification_id, user_id):
    conn.execute("UPDATE notifications SET read=1 WHERE id=? AND user_id=?")
    conn.commit()


def mark_all_notifications_read(conn, user_id):
    conn.execute("UPDATE notifications SET read=1 WHERE user_id=? "
                 "AND read=0", (user_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Phase 5 — discovery, collaboration requests and accepted collaborations
# ---------------------------------------------------------------------------

def project_discoverable(project):
    """An industry partner can only collaborate on a project created from an
    APPROVED proposal (Academic Solution Ready) that is still in motion."""
    return (project is not None
            and project.proposal is not None
            and project.proposal.status == "APPROVED"
            and project.status in ("CREATED", "ACTIVE"))


def project_faculty_lead(conn, team_id):
    row = conn.execute(
        "SELECT u.name FROM team_members tm JOIN users u ON u.id=tm.user_id "
        "WHERE tm.team_id=? AND tm.status='ACTIVE' AND tm.member_role IN "
        "('FACULTY_LEAD','FACULTY') ORDER BY CASE tm.member_role "
        "WHEN 'FACULTY_LEAD' THEN 0 ELSE 1 END LIMIT 1",
        (team_id,)).fetchone()
    return row["name"] if row else None


def list_discoverable_projects(conn):
    """Every project that is ready for industry collaboration. Faithful to
    Phase 4: only projects born from APPROVED proposals, without student or
    citizen PII — the industry sees the institution, the team name and the
    faculty lead, never student phone/email details."""
    rows = conn.execute(
        "SELECT p.* FROM projects p JOIN proposals pr ON pr.id=p.proposal_id "
        "WHERE pr.status='APPROVED' AND p.status IN ('CREATED','ACTIVE') "
        "ORDER BY p.created_at DESC").fetchall()
    out = []
    for r in rows:
        project = hydrate_project(conn, r)
        ns = SimpleNamespace(
            id=project.id, title=project.title, description=project.description,
            status=project.status, start_date=project.start_date,
            target_end_date=project.target_end_date,
            challenge=project.challenge, university=project.university,
            team=project.team, proposal=project.proposal,
            faculty_lead=project_faculty_lead(conn, project.team_id),
        )
        ns.collaborations = list_project_collaborations(conn, project_id=ns.id)
        ns.academic_ready = True
        out.append(ns)
    return out


def get_collaboration_row(conn, request_id):
    if request_id is None:
        return None
    return conn.execute("SELECT * FROM collaboration_requests WHERE id=?",
                        (request_id,)).fetchone()


def hydrate_collaboration_log(row):
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    return ns


def add_collaboration_log(conn, request_id, action, old_status, new_status,
                          performed_by, comment=""):
    conn.execute(
        "INSERT INTO collaboration_logs (request_id, action, old_status, "
        "new_status, performed_by, comment, created_at) VALUES (?,?,?,?,?,?,?)",
        (request_id, action, old_status, new_status, performed_by,
         comment or "", _now().isoformat()))


def hydrate_collaboration(conn, row, with_relations=True):
    if row is None:
        return None
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    ns.updated_at = _parse_dt(d.get("updated_at"))
    ns.reviewed_at = _parse_dt(d.get("reviewed_at"))
    ns.is_accepted = d.get("status") == "ACCEPTED"
    ns.is_pending = d.get("status") in ("INTERESTED", "SUBMITTED", "UNDER_REVIEW")
    ns.is_interested = d.get("status") == "INTERESTED"
    if with_relations:
        ns.project = hydrate_project(
            conn, get_project_row(conn, d["project_id"]), with_relations=True)
        ns.organization = hydrate_industry_organization(
            conn, get_industry_organization_row(conn, d["organization_id"]),
            with_relations=False)
        ns.requester = hydrate_user(get_user_by_id(conn, d.get("requested_by")))
        ns.reviewer = hydrate_user(get_user_by_id(conn, d.get("reviewed_by")))
        ns.logs = [hydrate_collaboration_log(r) for r in conn.execute(
            "SELECT * FROM collaboration_logs WHERE request_id=? "
            "ORDER BY created_at ASC", (d["id"],)).fetchall()]
        ns.collaboration = get_project_collaboration(conn, d["id"],
                                                     by_request=True)
    return ns


def get_collaboration(conn, request_id):
    return hydrate_collaboration(conn, get_collaboration_row(conn, request_id))


def _open_duplicate(conn, project_id, org_id):
    statuses = ("INTERESTED", "SUBMITTED", "UNDER_REVIEW",
                "REVISION_REQUESTED")
    row = conn.execute(
        "SELECT id FROM collaboration_requests WHERE project_id=? AND "
        "organization_id=? AND status IN " + _sql_in(statuses),
        (project_id, org_id, *statuses)).fetchone()
    if row:
        return row
    return conn.execute(
        "SELECT 1 FROM project_collaborations WHERE project_id=? AND "
        "organization_id=? AND status IN ('CONNECTED','ACTIVE')",
        (project_id, org_id)).fetchone()


def express_interest(conn, project, org, requested_by, collaboration_type,
                     title, description, expected_support="", proposed_amount=None,
                     funding_type=None, funding_description=""):
    """Industry expresses initial interest (the INTERESTED state). Enforces
    verified-org eligibility, discoverable projects and a single open
    request per (project, organization) so interest can never be spammed."""
    if org is None or not org.is_verified:
        raise ValueError("Only a government-verified organization can "
                         "collaborate on a project.")
    if not project_discoverable(project):
        raise ValueError("This project is not open for collaboration.")
    if _open_duplicate(conn, project.id, org.id):
        raise ValueError("You already have an open request on this project.")
    collaboration_type = (collaboration_type
                          if collaboration_type in COLLABORATION_TYPES
                          else "TECHNICAL_SUPPORT")
    funding_type = (funding_type if funding_type in FUNDING_TYPES else None)
    if funding_type in ("GRANT", "CSR", "SPONSORSHIP") and not proposed_amount:
        proposed_amount = 0.0
    cur = conn.execute(
        "INSERT INTO collaboration_requests (project_id, organization_id, "
        "requested_by, collaboration_type, title, description, "
        "expected_support, proposed_amount, currency, funding_type, "
        "funding_description, status, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (project.id, org.id, requested_by, collaboration_type, title,
         description, expected_support, proposed_amount, "INR", funding_type,
         funding_description, "INTERESTED", _now().isoformat(),
         _now().isoformat()))
    add_collaboration_log(conn, cur.lastrowid, "INTERESTED",
                          None, "INTERESTED", requested_by,
                          "Organization expressed interest in the project.")
    conn.commit()
    add_notification(
        conn, org.user_id, "collaboration",
        "notif_collab_interest",
        f"Your interest on project \"{title[:60]}\" is saved. Submit it "
        "to send the request to the government review.",
        "collaboration", cur.lastrowid)
    return cur.lastrowid


def _project_university_recipients(conn, request_row):
    """University admin account + active faculty of the owning institution —
    the people who should know about collaboration events on their project."""
    pj = conn.execute(
        "SELECT university_id FROM projects WHERE id=?",
        (request_row["project_id"],)).fetchone()
    if pj is None:
        return []
    uni_id = pj["university_id"]
    recipients = []
    row = conn.execute(
        "SELECT admin_user_id FROM universities WHERE id=?",
        (uni_id,)).fetchone()
    if row and row["admin_user_id"]:
        recipients.append(row["admin_user_id"])
    for f in conn.execute(
            "SELECT user_id FROM faculty WHERE university_id=?",
            (uni_id,)).fetchall():
        recipients.append(f["user_id"])
    return list(dict.fromkeys(recipients))


def submit_collaboration(conn, request_id, actor_id):
    """INTERESTED -> SUBMITTED, or a REVISION_REQUESTED resubmission back to
    SUBMITTED so the government reviewer can re-check the updated request."""
    row = get_collaboration_row(conn, request_id)
    if row is None:
        raise ValueError("Collaboration request not found.")
    if row["status"] == "INTERESTED":
        old_status, new_status = "INTERESTED", "SUBMITTED"
    elif row["status"] == "REVISION_REQUESTED":
        old_status, new_status = "REVISION_REQUESTED", "SUBMITTED"
    else:
        raise ValueError("This request is not in a submittable state.")
    conn.execute("UPDATE collaboration_requests SET status=?, updated_at=? "
                 "WHERE id=?", (new_status, _now().isoformat(), request_id))
    add_collaboration_log(conn, request_id, "SUBMITTED", old_status,
                          new_status, actor_id,
                          "Collaboration request submitted for government review.")
    org = get_industry_organization_row(conn, row["organization_id"])
    for uid in list_user_ids_by_role(conn, "officer"):
        add_notification(conn, uid, "collaboration",
                         "notif_collab_submitted",
                         f"Organization "
                         f"\"{(org['name'] if org else 'Partner')}\" submitted "
                         f"a collaboration request on project #{row['project_id']}.",
                         "collaboration", request_id)
    for uid in list_user_ids_by_role(conn, "admin"):
        add_notification(conn, uid, "collaboration",
                         "notif_collab_submitted",
                         f"Organization "
                         f"\"{(org['name'] if org else 'Partner')}\" submitted "
                         f"a collaboration request on project #{row['project_id']}.",
                         "collaboration", request_id)
    for uid in _project_university_recipients(conn, row):
        add_notification(conn, uid, "collaboration",
                         "notif_collab_submitted_uni",
                         "An industry partner has submitted a collaboration "
                         f"request on your project #{row['project_id']}.",
                         "collaboration", request_id)
    conn.commit()
    return new_status


def begin_collaboration_review(conn, request_id, actor_id):
    """SUBMITTED -> UNDER_REVIEW (reviewer takes up the request)."""
    row = get_collaboration_row(conn, request_id)
    if row is None or row["status"] != "SUBMITTED":
        raise ValueError("Only a submitted request can begin review.")
    conn.execute("UPDATE collaboration_requests SET status='UNDER_REVIEW', "
                 "updated_at=? WHERE id=?", (_now().isoformat(), request_id))
    add_collaboration_log(conn, request_id, "REVIEW_STARTED",
                          "SUBMITTED", "UNDER_REVIEW", actor_id,
                          "Government reviewer began assessing the request.")
    org = get_industry_organization_row(conn, row["organization_id"])
    if org:
        add_notification(conn, org["user_id"], "collaboration",
                         "notif_collab_reviewing",
                         "The government is now reviewing your collaboration "
                         "request.",
                         "collaboration", request_id)
    conn.commit()
    return "UNDER_REVIEW"


def review_collaboration(conn, request_id, decision, comment, actor_id):
    """Government verdict on a collaboration request: ACCEPTED /
    REVISION_REQUESTED / REJECTED. Accepting creates the tracked
    project_collaborations record (Industry Collaboration Connected) with a
    PROPOSED funding line — no money ever moves in this platform."""
    decision = (decision if decision in COLLABORATION_FEEDBACK_STATUSES
                else None)
    if decision is None:
        raise ValueError("Unknown review decision.")
    row = get_collaboration_row(conn, request_id)
    if row is None:
        raise ValueError("Collaboration request not found.")
    if row["status"] != "UNDER_REVIEW":
        raise ValueError("A verdict is only possible while the request is "
                         "under review.")
    old_status = row["status"]
    conn.execute(
        "UPDATE collaboration_requests SET status=?, review_comment=?, "
        "reviewed_by=?, reviewed_at=?, updated_at=? WHERE id=?",
        (decision, comment or "", actor_id, _now().isoformat(),
         _now().isoformat(), request_id))
    add_collaboration_log(conn, request_id, decision, old_status,
                          decision, actor_id, comment or "")
    org = get_industry_organization_row(conn, row["organization_id"])
    if org:
        add_notification(conn, org["user_id"], "collaboration",
                         {
                             "ACCEPTED": "notif_collab_accepted",
                             "REVISION_REQUESTED": "notif_collab_revision",
                             "REJECTED": "notif_collab_rejected",
                         }[decision],
                         (comment or "The government reviewed your "
                          "collaboration request."),
                         "collaboration", request_id)
    if decision == "ACCEPTED":
        existing = conn.execute(
            "SELECT 1 FROM project_collaborations WHERE request_id=?",
            (request_id,)).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO project_collaborations (project_id, "
                "organization_id, request_id, agreed_support, approved_amount, "
                "funding_status, start_date, target_end_date, status, "
                "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (row["project_id"], row["organization_id"], request_id,
                 row["expected_support"] or "", row["proposed_amount"] or 0,
                 "PROPOSED", _now().date().isoformat(), "", "CONNECTED",
                 _now().isoformat(), _now().isoformat()))
        add_collaboration_log(conn, request_id, "CONNECTED",
                              decision, "CONNECTED", actor_id,
                              "Industry collaboration connected to the project.")
        for uid in _project_university_recipients(conn, row):
            add_notification(conn, uid, "collaboration",
                             "notif_collab_accepted_uni",
                             "An industry partner is now connected to your "
                             f"project #{row['project_id']}.",
                             "collaboration", request_id)
    conn.commit()
    return decision


def get_project_collaboration(conn, pc_id, by_request=False):
    q = ("SELECT * FROM project_collaborations WHERE "
         + ("request_id=?" if by_request else "id=?"))
    row = conn.execute(q, (pc_id,)).fetchone()
    if row is None:
        return None
    return hydrate_project_collaboration(conn, row)


def hydrate_project_collaboration(conn, row):
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    ns.updated_at = _parse_dt(d.get("updated_at"))
    ns.start_date = _parse_dt(d.get("start_date"))
    ns.target_end_date = _parse_dt(d.get("target_end_date"))
    ns.organization = hydrate_industry_organization(
        conn, get_industry_organization_row(conn, d["organization_id"]),
        with_relations=False)
    ns.request = hydrate_collaboration(
        conn, get_collaboration_row(conn, d["request_id"]),
        with_relations=False)
    return ns


def list_project_collaborations(conn, project_id=None, organization_id=None):
    q = "SELECT * FROM project_collaborations"
    args = []
    conds = []
    if project_id is not None:
        conds.append("project_id=?")
        args.append(project_id)
    if organization_id is not None:
        conds.append("organization_id=?")
        args.append(organization_id)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY created_at DESC"
    rows = conn.execute(q, args).fetchall()
    return [hydrate_project_collaboration(conn, r) for r in rows]


def update_collaboration_funding(conn, request_id, funding_status, comment,
                                 actor_id):
    """Funding representation only: an ACCEPTED collaboration's funding line
    moves PROPOSED -> APPROVED / DECLINED, and APPROVED ->
    DISBURSEMENT_PENDING. No payment ever happens."""
    if funding_status not in FUNDING_STATUSES or funding_status == "PROPOSED":
        raise ValueError("Unknown funding state.")
    row = get_collaboration_row(conn, request_id)
    if row is None or row["status"] != "ACCEPTED":
        raise ValueError("Only an accepted collaboration carries funding.")
    pc = get_project_collaboration(conn, request_id, by_request=True)
    if pc is None:
        raise ValueError("No connected collaboration for this request.")
    if funding_status == "DISBURSEMENT_PENDING" and \
            pc.funding_status != "APPROVED":
        raise ValueError("Funding must be approved before disbursement "
                         "is pending.")
    conn.execute(
        "UPDATE project_collaborations SET funding_status=?, updated_at=? "
        "WHERE id=?", (funding_status, _now().isoformat(), pc.id))
    add_collaboration_log(conn, request_id, "FUNDING_" + funding_status,
                          pc.funding_status, funding_status, actor_id,
                          comment or "")
    org = get_industry_organization_row(conn, row["organization_id"])
    if org:
        add_notification(conn, org["user_id"], "funding",
                         "notif_funding_status",
                         f"Proposed funding is now marked "
                         f"{funding_status.lower().replace('_', ' ')}.",
                         "collaboration", request_id)
    conn.commit()
    return funding_status


def list_collaborations_for_org(conn, org_id):
    rows = conn.execute(
        "SELECT * FROM collaboration_requests WHERE organization_id=? "
        "ORDER BY updated_at DESC", (org_id,)).fetchall()
    return [hydrate_collaboration(conn, r) for r in rows]


def list_collaborations_for_project(conn, project_id):
    rows = conn.execute(
        "SELECT * FROM collaboration_requests WHERE project_id=? "
        "ORDER BY updated_at DESC", (project_id,)).fetchall()
    return [hydrate_collaboration(conn, r) for r in rows]


def list_collaborations_for_university(conn, university_id):
    rows = conn.execute(
        "SELECT cr.* FROM collaboration_requests cr JOIN projects p "
        "ON p.id=cr.project_id WHERE p.university_id=? "
        "ORDER BY cr.updated_at DESC", (university_id,)).fetchall()
    return [hydrate_collaboration(conn, r) for r in rows]


def list_collaborations_for_mode(conn, mode):
    if mode == "review":
        q = ("SELECT * FROM collaboration_requests WHERE status IN "
             + _sql_in(COLLABORATION_MARKER_STATUSES)
             + " ORDER BY updated_at DESC")
        args = (*COLLABORATION_MARKER_STATUSES,)
    elif mode == "decided":
        q = ("SELECT * FROM collaboration_requests WHERE status IN "
             + _sql_in(COLLABORATION_FEEDBACK_STATUSES)
             + " ORDER BY reviewed_at DESC")
        args = (*COLLABORATION_FEEDBACK_STATUSES,)
    else:
        q = "SELECT * FROM collaboration_requests ORDER BY updated_at DESC"
        args = ()
    rows = conn.execute(q, args).fetchall()
    return [hydrate_collaboration(conn, r) for r in rows]


def count_collaborations_needing_review(conn):
    return conn.execute(
        "SELECT COUNT(*) c FROM collaboration_requests WHERE status IN "
        + _sql_in(COLLABORATION_MARKER_STATUSES),
        (*COLLABORATION_MARKER_STATUSES,)).fetchone()["c"]


def get_connected_collaboration(conn, project_id):
    """The accepted, industry-connected collaboration on a project, if any."""
    row = conn.execute(
        "SELECT * FROM project_collaborations WHERE project_id=? "
        "ORDER BY id ASC LIMIT 1", (project_id,)).fetchone()
    return hydrate_project_collaboration(conn, row) if row else None


def project_readiness(conn, project):
    """Honest readiness stage. The label advances only on government-approved
    milestones: Academic Solution Ready → Industry Collaboration Connected →
    Prototype Ready → Testing Completed → Pilot In Progress / Completed →
    Deployed. "Deployed" only ever means an authorized reviewer completed the
    platform's deployment review — never independent real-world verification."""
    academic = project is not None and (
        getattr(project, "proposal", None) is not None
        and project.proposal.status == "APPROVED")
    connected = (get_connected_collaboration(conn, project.id) is not None
                 if project is not None else False)
    prototype = None
    testing = None
    pilot = None
    if project is not None:
        prototype = get_prototype_for_project(conn, project.id)
        testing = get_testing_report_for_project(conn, project.id)
        pilot = get_pilot_for_project(conn, project.id)
    prototype_ready = bool(prototype and prototype.status == "APPROVED")
    testing_completed = bool(testing and testing.status == "APPROVED")
    pilot_label = None
    if pilot is not None:
        if pilot.status == "DEPLOYED":
            pilot_label = "deployed"
        elif pilot.status == "COMPLETED":
            pilot_label = "pilot_completed"
        elif pilot.status in ("PLANNED", "ACTIVE"):
            pilot_label = "pilot_active"
    if pilot_label:
        label = pilot_label
    elif testing_completed:
        label = "testing_completed"
    elif prototype_ready:
        label = "prototype_ready"
    elif connected:
        label = "industry_connected"
    elif academic:
        label = "academic_ready"
    else:
        label = "not_ready"
    return {
        "academic_ready": academic,
        "industry_connected": connected,
        "prototype_ready": prototype_ready,
        "testing_completed": testing_completed,
        "pilot_active": pilot is not None and pilot.status in ("PLANNED", "ACTIVE"),
        "pilot_completed": pilot is not None and pilot.status == "COMPLETED",
        "deployed": pilot is not None and pilot.status == "DEPLOYED",
        "label": label,
        "prototype": prototype,
        "testing": testing,
        "pilot": pilot,
    }


def industry_dashboard_kpis(conn):
    return {
        "orgs_total": count_industry_organizations(conn),
        "orgs_verified": count_industry_organizations(conn, "VERIFIED"),
        "orgs_pending": count_industry_organizations(conn, "PENDING"),
        "orgs_rejected": count_industry_organizations(conn, "REJECTED"),
        "collab_reviews": count_collaborations_needing_review(conn),
        "collab_accepted": conn.execute(
            "SELECT COUNT(*) c FROM collaboration_requests "
            "WHERE status='ACCEPTED'").fetchone()["c"],
        "collab_connected": conn.execute(
            "SELECT COUNT(*) c FROM project_collaborations").fetchone()["c"],
        "funding_approved": conn.execute(
            "SELECT COALESCE(SUM(approved_amount),0) s FROM "
            "project_collaborations WHERE funding_status='APPROVED'"
        ).fetchone()["s"],
        "funding_proposed": conn.execute(
            "SELECT COALESCE(SUM(approved_amount),0) s FROM "
            "project_collaborations WHERE funding_status IN "
            "('PROPOSED','DISBURSEMENT_PENDING')").fetchone()["s"],
    }


# ---------------------------------------------------------------------------
# Phase 6 — project lifecycle: prototype → testing → pilot → deployment
# ---------------------------------------------------------------------------

def _project_university_recipients_for(conn, project_id):
    """University admin + faculty accounts of the project's owning institution
    (Phase 6 counterpart of the collaboration recipient helper)."""
    return _project_university_recipients(conn, {"project_id": project_id})


def _gov_user_ids(conn):
    uids = list(list_user_ids_by_role(conn, "admin"))
    for uid in list_user_ids_by_role(conn, "officer"):
        if uid not in uids:
            uids.append(uid)
    return uids


def _team_user_ids(conn, team_id):
    rows = conn.execute(
        "SELECT user_id FROM team_members WHERE team_id=? AND status='ACTIVE'",
        (team_id,)).fetchall()
    return [r["user_id"] for r in rows]


def _connected_industry_users(conn, project_id):
    """user_ids of the industry organization owners connected to a project
    through an accepted collaboration (CONNECTED/ACTIVE). No student PII is
    ever attached here — industry only reads project-level lifecycle info."""
    rows = conn.execute(
        "SELECT DISTINCT io.user_id FROM project_collaborations pc "
        "JOIN industry_organizations io ON io.id=pc.organization_id "
        "WHERE pc.project_id=? AND pc.status IN ('CONNECTED','ACTIVE')",
        (project_id,)).fetchall()
    return [r["user_id"] for r in rows]


def _clean_evidence(evidence):
    """Normalize evidence from any accepted shape (JSON string or a list of
    {name, path} / plain filename strings) into a list of {name, path}."""
    if not evidence:
        return []
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except (ValueError, TypeError):
            return [{"name": evidence, "path": evidence}]
    out = []
    for item in (evidence if isinstance(evidence, list) else [evidence]):
        if isinstance(item, str) and item.strip():
            out.append({"name": item.strip(), "path": item.strip()})
        elif isinstance(item, dict) and item.get("path"):
            out.append({"name": item.get("name") or item["path"],
                        "path": item["path"]})
    return out


def add_prototype_log(conn, prototype_id, action, old_status, new_status,
                      performed_by, comment=""):
    conn.execute(
        "INSERT INTO prototype_logs (prototype_id, action, old_status, "
        "new_status, performed_by, comment, created_at) VALUES (?,?,?,?,?,?,?)",
        (prototype_id, action, old_status, new_status, performed_by,
         comment or "", _now().isoformat()))


def hydrate_prototype_log(row):
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    return ns


def get_prototype_row(conn, prototype_id):
    if prototype_id is None:
        return None
    return conn.execute("SELECT * FROM project_prototypes WHERE id=?",
                        (prototype_id,)).fetchone()


def get_prototype_for_project(conn, project_id):
    row = conn.execute("SELECT * FROM project_prototypes WHERE project_id=?",
                       (project_id,)).fetchone()
    return hydrate_prototype(conn, row) if row else None


def hydrate_prototype(conn, row):
    if row is None:
        return None
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    ns.updated_at = _parse_dt(d.get("updated_at"))
    ns.submitted_at = _parse_dt(d.get("submitted_at"))
    ns.reviewed_at = _parse_dt(d.get("reviewed_at"))
    ns.evidence = _clean_evidence(d.get("evidence_json"))
    ns.is_approved = d.get("status") == "APPROVED"
    ns.is_revision = d.get("status") == "REVISION_REQUESTED"
    ns.project = hydrate_project(
        conn, get_project_row(conn, d["project_id"]), with_relations=False)
    ns.submitter = hydrate_user(get_user_by_id(conn, d.get("submitted_by")))
    ns.reviewer = hydrate_user(get_user_by_id(conn, d.get("reviewed_by")))
    ns.logs = [hydrate_prototype_log(r) for r in conn.execute(
        "SELECT * FROM prototype_logs WHERE prototype_id=? "
        "ORDER BY created_at ASC", (d["id"],)).fetchall()]
    return ns


def get_prototype(conn, prototype_id):
    return hydrate_prototype(conn, get_prototype_row(conn, prototype_id))


def create_prototype(conn, project_id, description, version, submitted_by,
                     progress_update="", evidence=None):
    """Team submits the prototype (stage 1). Exactly one record per project and
    only a live project (born from an APPROVED proposal) can carry one."""
    project = get_project_row(conn, project_id)
    if project is None:
        raise ValueError("Project not found.")
    if project["status"] not in ("CREATED", "ACTIVE"):
        raise ValueError("Only a live project can have a prototype.")
    if get_prototype_for_project(conn, project_id) is not None:
        raise ValueError("A prototype already exists for this project.")
    evidence = _clean_evidence(evidence)
    cur = conn.execute(
        "INSERT INTO project_prototypes (project_id, description, "
        "progress_update, version, evidence_json, status, submitted_by, "
        "submitted_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (project_id, description or "", progress_update or "", version or "v1",
         json.dumps(evidence), "SUBMITTED", submitted_by,
         _now().isoformat(), _now().isoformat(), _now().isoformat()))
    add_prototype_log(conn, cur.lastrowid, "SUBMITTED", None, "SUBMITTED",
                      submitted_by,
                      "Prototype submitted for government review.")
    for uid in _gov_user_ids(conn):
        add_notification(conn, uid, "prototype", "notif_prototype_submitted",
                         f"Team submitted a prototype on project #{project_id} "
                         f"\"{project['title'][:60]}\".",
                         "prototype", cur.lastrowid)
    add_challenge_log(conn, project["challenge_id"], "PROTOTYPE_SUBMITTED",
                      f"Prototype submitted for project "
                      f"\"{project['title'][:60]}\".", submitted_by)
    conn.commit()
    return cur.lastrowid


def update_prototype_details(conn, prototype_id, description=None,
                             version=None, progress_update=None,
                             evidence=None):
    """Edits the working content while the prototype is in the revision state.
    The state machine itself is untouched — a resubmission re-enters review."""
    row = get_prototype_row(conn, prototype_id)
    if row is None:
        raise ValueError("Prototype not found.")
    if row["status"] != "REVISION_REQUESTED":
        raise ValueError("Only a revision-requested prototype can be edited.")
    d = dict(row)
    if description is not None:
        d["description"] = description
    if version is not None:
        d["version"] = version
    if progress_update is not None:
        d["progress_update"] = progress_update
    if evidence is not None:
        d["evidence_json"] = json.dumps(_clean_evidence(evidence))
    d["updated_at"] = _now().isoformat()
    conn.execute(
        "UPDATE project_prototypes SET description=?, progress_update=?, "
        "version=?, evidence_json=?, updated_at=? WHERE id=?",
        (d["description"], d["progress_update"], d["version"],
         d["evidence_json"], d["updated_at"], prototype_id))
    add_prototype_log(conn, prototype_id, "UPDATED", row["status"],
                      row["status"], row["submitted_by"],
                      "Prototype draft updated.")
    conn.commit()


def resubmit_prototype(conn, prototype_id, actor_id):
    """REVISION_REQUESTED -> SUBMITTED so the government re-checks the update."""
    row = get_prototype_row(conn, prototype_id)
    if row is None or row["status"] != "REVISION_REQUESTED":
        raise ValueError("Only a revision-requested prototype can be "
                         "resubmitted.")
    conn.execute("UPDATE project_prototypes SET status='SUBMITTED', "
                 "reviewer_comment=NULL, updated_at=? WHERE id=?",
                 (_now().isoformat(), prototype_id))
    add_prototype_log(conn, prototype_id, "SUBMITTED",
                      "REVISION_REQUESTED", "SUBMITTED", actor_id,
                      "Prototype resubmitted after revision.")
    for uid in _gov_user_ids(conn):
        add_notification(conn, uid, "prototype", "notif_prototype_submitted",
                         f"Prototype #{prototype_id} was resubmitted after "
                         "revision.", "prototype", prototype_id)
    conn.commit()
    return "SUBMITTED"


def begin_prototype_review(conn, prototype_id, actor_id):
    """SUBMITTED -> UNDER_REVIEW (reviewer takes up the prototype)."""
    row = get_prototype_row(conn, prototype_id)
    if row is None or row["status"] != "SUBMITTED":
        raise ValueError("Only a submitted prototype can begin review.")
    conn.execute("UPDATE project_prototypes SET status='UNDER_REVIEW', "
                 "updated_at=? WHERE id=?", (_now().isoformat(), prototype_id))
    add_prototype_log(conn, prototype_id, "REVIEW_STARTED",
                      "SUBMITTED", "UNDER_REVIEW", actor_id,
                      "Government reviewer began assessing the prototype.")
    conn.commit()
    return "UNDER_REVIEW"


def review_prototype(conn, prototype_id, decision, comment, actor_id):
    """Government verdict on the prototype: APPROVED / REVISION_REQUESTED.
    Approval notifies the team, the university and connected industry
    partners (project-level info only — never student or citizen PII)."""
    decision = (decision if decision in PROTOTYPE_FEEDBACK_STATUSES else None)
    if decision is None:
        raise ValueError("Unknown review decision.")
    row = get_prototype_row(conn, prototype_id)
    if row is None:
        raise ValueError("Prototype not found.")
    if row["status"] != "UNDER_REVIEW":
        raise ValueError("A verdict is only possible while under review.")
    old_status = row["status"]
    conn.execute(
        "UPDATE project_prototypes SET status=?, reviewer_comment=?, "
        "reviewed_by=?, reviewed_at=?, updated_at=? WHERE id=?",
        (decision, comment or "", actor_id, _now().isoformat(),
         _now().isoformat(), prototype_id))
    add_prototype_log(conn, prototype_id, decision, old_status, decision,
                      actor_id, comment or "")
    project = get_project_row(conn, row["project_id"])
    if project:
        for uid in _team_user_ids(conn, project["team_id"]):
            add_notification(conn, uid, "prototype",
                             ("notif_prototype_approved"
                              if decision == "APPROVED"
                              else "notif_prototype_revision"),
                             (comment or (("Your prototype was approved by "
                                           "the government.") if decision
                                           == "APPROVED"
                                           else "Your prototype needs "
                                                "revision.")),
                             "prototype", prototype_id)
        for uid in _project_university_recipients_for(conn, row["project_id"]):
            add_notification(conn, uid, "prototype",
                             ("notif_prototype_approved"
                              if decision == "APPROVED"
                              else "notif_prototype_revision"),
                             f"Prototype on project "
                             f"\"{project['title'][:60]}\" "
                             + ("was approved." if decision == "APPROVED"
                                else "needs revision."),
                             "prototype", prototype_id)
        for uid in _connected_industry_users(conn, row["project_id"]):
            add_notification(conn, uid, "prototype",
                             ("notif_prototype_approved_partner"
                              if decision == "APPROVED"
                              else "notif_prototype_revision_partner"),
                             f"Prototype on project "
                             f"\"{project['title'][:60]}\" "
                             + ("was approved." if decision == "APPROVED"
                                else "was returned for revision."),
                             "prototype", prototype_id)
    conn.commit()
    return decision


def list_prototypes(conn, mode="all"):
    if mode == "review":
        q = ("SELECT * FROM project_prototypes WHERE status IN "
             + _sql_in(PROTOTYPE_MARKER_STATUSES)
             + " ORDER BY submitted_at DESC")
        args = (*PROTOTYPE_MARKER_STATUSES,)
    elif mode == "decided":
        q = ("SELECT * FROM project_prototypes WHERE status IN "
             + _sql_in(PROTOTYPE_FEEDBACK_STATUSES)
             + " ORDER BY reviewed_at DESC")
        args = (*PROTOTYPE_FEEDBACK_STATUSES,)
    else:
        q = "SELECT * FROM project_prototypes ORDER BY submitted_at DESC"
        args = ()
    return [hydrate_prototype(conn, r)
            for r in conn.execute(q, args).fetchall()]


def count_prototypes_needing_review(conn):
    return conn.execute(
        "SELECT COUNT(*) c FROM project_prototypes WHERE status IN "
        + _sql_in(PROTOTYPE_MARKER_STATUSES),
        (*PROTOTYPE_MARKER_STATUSES,)).fetchone()["c"]


def get_testing_report_row(conn, report_id):
    if report_id is None:
        return None
    return conn.execute("SELECT * FROM testing_reports WHERE id=?",
                        (report_id,)).fetchone()


def get_testing_report_for_project(conn, project_id):
    row = conn.execute("SELECT * FROM testing_reports WHERE project_id=?",
                       (project_id,)).fetchone()
    return hydrate_testing_report(conn, row) if row else None


def hydrate_testing_report(conn, row):
    if row is None:
        return None
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    ns.updated_at = _parse_dt(d.get("updated_at"))
    ns.submitted_at = _parse_dt(d.get("submitted_at"))
    ns.reviewed_at = _parse_dt(d.get("reviewed_at"))
    ns.evidence = _clean_evidence(d.get("evidence_json"))
    ns.is_approved = d.get("status") == "APPROVED"
    ns.is_revision = d.get("status") == "REVISION_REQUESTED"
    ns.project = hydrate_project(
        conn, get_project_row(conn, d["project_id"]), with_relations=False)
    ns.submitter = hydrate_user(get_user_by_id(conn, d.get("submitted_by")))
    ns.reviewer = hydrate_user(get_user_by_id(conn, d.get("reviewed_by")))
    return ns


def get_testing_report(conn, report_id):
    return hydrate_testing_report(conn, get_testing_report_row(conn, report_id))


def create_testing_report(conn, project_id, objective, test_description,
                          expected_result, actual_result, test_result,
                          submitted_by, issues_findings="", evidence=None):
    """Team submits the structured testing report (stage 2). Requires the
    prototype to have been APPROVED by the government first. test_result
    carries the PASS / FAIL / PENDING outcome the team measured."""
    project = get_project_row(conn, project_id)
    if project is None:
        raise ValueError("Project not found.")
    prototype = get_prototype_for_project(conn, project_id)
    if prototype is None or prototype.status != "APPROVED":
        raise ValueError("Testing requires an approved prototype first.")
    if get_testing_report_for_project(conn, project_id) is not None:
        raise ValueError("A testing report already exists for this project.")
    test_result = (test_result if test_result in TESTING_RESULT_STATUSES
                   else "PENDING")
    evidence = _clean_evidence(evidence)
    cur = conn.execute(
        "INSERT INTO testing_reports (project_id, prototype_id, objective, "
        "test_description, expected_result, actual_result, test_result, "
        "issues_findings, evidence_json, status, submitted_by, submitted_at, "
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (project_id, prototype.id, objective or "", test_description or "",
         expected_result or "", actual_result or "", test_result,
         issues_findings or "", json.dumps(evidence), "SUBMITTED",
         submitted_by, _now().isoformat(), _now().isoformat(),
         _now().isoformat()))
    for uid in _gov_user_ids(conn):
        add_notification(conn, uid, "testing", "notif_testing_submitted",
                         f"Team submitted a testing report on project "
                         f"#{project_id} \"{project['title'][:60]}\".",
                         "testing", cur.lastrowid)
    add_challenge_log(conn, project["challenge_id"], "TESTING_SUBMITTED",
                      f"Testing report submitted for project "
                      f"\"{project['title'][:60]}\".", submitted_by)
    conn.commit()
    return cur.lastrowid


def resubmit_testing_report(conn, report_id, actor_id):
    """REVISION_REQUESTED -> SUBMITTED so the government re-checks the fixes."""
    row = get_testing_report_row(conn, report_id)
    if row is None or row["status"] != "REVISION_REQUESTED":
        raise ValueError("Only a revision-requested report can be resubmitted.")
    conn.execute("UPDATE testing_reports SET status='SUBMITTED', "
                 "reviewer_comment=NULL, updated_at=? WHERE id=?",
                 (_now().isoformat(), report_id))
    for uid in _gov_user_ids(conn):
        add_notification(conn, uid, "testing", "notif_testing_submitted",
                         f"Testing report #{report_id} was resubmitted after "
                         "revision.", "testing", report_id)
    conn.commit()
    return "SUBMITTED"


def update_testing_report(conn, report_id, objective=None,
                          test_description=None, expected_result=None,
                          actual_result=None, test_result=None,
                          issues_findings=None, evidence=None):
    """Edits the working content while the report is in the revision state.
    The state machine itself is untouched — a resubmission re-enters review."""
    row = get_testing_report_row(conn, report_id)
    if row is None:
        raise ValueError("Testing report not found.")
    if row["status"] != "REVISION_REQUESTED":
        raise ValueError("Only a revision-requested report can be edited.")
    d = dict(row)
    if objective is not None:
        d["objective"] = objective
    if test_description is not None:
        d["test_description"] = test_description
    if expected_result is not None:
        d["expected_result"] = expected_result
    if actual_result is not None:
        d["actual_result"] = actual_result
    if test_result is not None:
        d["test_result"] = (test_result if test_result
                            in TESTING_RESULT_STATUSES else row["test_result"])
    if issues_findings is not None:
        d["issues_findings"] = issues_findings
    if evidence is not None:
        d["evidence_json"] = json.dumps(_clean_evidence(evidence))
    d["updated_at"] = _now().isoformat()
    conn.execute(
        "UPDATE testing_reports SET objective=?, test_description=?, "
        "expected_result=?, actual_result=?, test_result=?, issues_findings=?, "
        "evidence_json=?, updated_at=? WHERE id=?",
        (d["objective"], d["test_description"], d["expected_result"],
         d["actual_result"], d["test_result"], d["issues_findings"],
         d["evidence_json"], d["updated_at"], report_id))
    for uid in _gov_user_ids(conn):
        add_notification(conn, uid, "testing", "notif_testing_revision",
                         f"Team updated testing report #{report_id} after "
                         "revision.", "testing", report_id)
    conn.commit()
    return "UPDATED"


def begin_testing_review(conn, report_id, actor_id):
    """SUBMITTED -> UNDER_REVIEW."""
    row = get_testing_report_row(conn, report_id)
    if row is None or row["status"] != "SUBMITTED":
        raise ValueError("Only a submitted report can begin review.")
    conn.execute("UPDATE testing_reports SET status='UNDER_REVIEW', "
                 "updated_at=? WHERE id=?", (_now().isoformat(), report_id))
    conn.commit()
    return "UNDER_REVIEW"


def review_testing_report(conn, report_id, decision, comment, actor_id):
    """Government verdict: APPROVED / REVISION_REQUESTED. Approval notifies
    the team and connected industry partners."""
    decision = (decision if decision in TESTING_FEEDBACK_STATUSES else None)
    if decision is None:
        raise ValueError("Unknown review decision.")
    row = get_testing_report_row(conn, report_id)
    if row is None:
        raise ValueError("Testing report not found.")
    if row["status"] != "UNDER_REVIEW":
        raise ValueError("A verdict is only possible while under review.")
    old_status = row["status"]
    conn.execute(
        "UPDATE testing_reports SET status=?, reviewer_comment=?, reviewed_by=?, "
        "reviewed_at=?, updated_at=? WHERE id=?",
        (decision, comment or "", actor_id, _now().isoformat(),
         _now().isoformat(), report_id))
    project = get_project_row(conn, row["project_id"])
    if project:
        for uid in _team_user_ids(conn, project["team_id"]):
            add_notification(conn, uid, "testing",
                             ("notif_testing_approved"
                              if decision == "APPROVED"
                              else "notif_testing_revision"),
                             comment or "Your testing report was reviewed by "
                             "the government.",
                             "testing", report_id)
        for uid in _connected_industry_users(conn, row["project_id"]):
            add_notification(conn, uid, "testing",
                             ("notif_testing_approved_partner"
                              if decision == "APPROVED"
                              else "notif_testing_revision_partner"),
                             f"Testing results for project "
                             f"\"{project['title'][:60]}\" "
                             + ("were approved." if decision == "APPROVED"
                                else "were returned for revision."),
                             "testing", report_id)
    conn.commit()
    return decision


def list_testing_reports(conn, mode="all"):
    if mode == "review":
        q = ("SELECT * FROM testing_reports WHERE status IN "
             + _sql_in(TESTING_MARKER_STATUSES)
             + " ORDER BY submitted_at DESC")
        args = (*TESTING_MARKER_STATUSES,)
    elif mode == "decided":
        q = ("SELECT * FROM testing_reports WHERE status IN "
             + _sql_in(TESTING_FEEDBACK_STATUSES)
             + " ORDER BY reviewed_at DESC")
        args = (*TESTING_FEEDBACK_STATUSES,)
    else:
        q = "SELECT * FROM testing_reports ORDER BY submitted_at DESC"
        args = ()
    return [hydrate_testing_report(conn, r)
            for r in conn.execute(q, args).fetchall()]


def count_testing_needing_review(conn):
    return conn.execute(
        "SELECT COUNT(*) c FROM testing_reports WHERE status IN "
        + _sql_in(TESTING_MARKER_STATUSES),
        (*TESTING_MARKER_STATUSES,)).fetchone()["c"]


def get_pilot_row(conn, pilot_id):
    if pilot_id is None:
        return None
    return conn.execute("SELECT * FROM pilot_deployments WHERE id=?",
                        (pilot_id,)).fetchone()


def get_pilot_for_project(conn, project_id):
    row = conn.execute("SELECT * FROM pilot_deployments WHERE project_id=?",
                       (project_id,)).fetchone()
    return hydrate_pilot(conn, row) if row else None


def hydrate_pilot(conn, row):
    if row is None:
        return None
    d = dict(row)
    ns = SimpleNamespace(**d)
    ns.created_at = _parse_dt(d.get("created_at"))
    ns.updated_at = _parse_dt(d.get("updated_at"))
    ns.start_date = _parse_dt(d.get("start_date"))
    ns.target_end_date = _parse_dt(d.get("target_end_date"))
    ns.reviewed_at = _parse_dt(d.get("reviewed_at"))
    ns.updates = []
    for line in (d.get("progress_updates") or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            ns.updates.append(SimpleNamespace(
                created_at=_parse_dt(parts[0].strip()),
                by=parts[1].strip(),
                text=parts[2].strip()))
    ns.is_deployed = d.get("status") == "DEPLOYED"
    ns.is_overdue = bool(ns.target_end_date) and ns.status in (
        "PLANNED", "ACTIVE") and _now() > ns.target_end_date
    ns.project = hydrate_project(
        conn, get_project_row(conn, d["project_id"]), with_relations=False)
    ns.creator = hydrate_user(get_user_by_id(conn, d.get("created_by")))
    ns.reviewer = hydrate_user(get_user_by_id(conn, d.get("reviewed_by")))
    return ns


def get_pilot(conn, pilot_id):
    return hydrate_pilot(conn, get_pilot_row(conn, pilot_id))


def _require_approved_stages(conn, project_id):
    prototype = get_prototype_for_project(conn, project_id)
    testing = get_testing_report_for_project(conn, project_id)
    if prototype is None or prototype.status != "APPROVED":
        raise ValueError("Pilot requires an approved prototype first.")
    if testing is None or testing.status != "APPROVED":
        raise ValueError("Pilot requires an approved testing report first.")
    return prototype, testing


def create_pilot(conn, project_id, district, created_by, location=None,
                 target_community=None, objectives="", start_date=None,
                 target_end_date=None, responsible_org=None):
    """Government opens the pilot (stage 3) once both the prototype and the
    testing report are approved. One pilot record per project."""
    project = get_project_row(conn, project_id)
    if project is None:
        raise ValueError("Project not found.")
    if project["status"] not in ("CREATED", "ACTIVE"):
        raise ValueError("Only a live project can have a pilot.")
    if district not in DISTRICTS:
        raise ValueError("Unknown district.")
    if get_pilot_for_project(conn, project_id) is not None:
        raise ValueError("A pilot already exists for this project.")
    _require_approved_stages(conn, project_id)
    cur = conn.execute(
        "INSERT INTO pilot_deployments (project_id, district, location, "
        "target_community, objectives, start_date, target_end_date, "
        "responsible_org, status, progress_updates, created_by, created_at, "
        "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (project_id, district, location or "", target_community or "",
         objectives or "", start_date or _now().date().isoformat(),
         target_end_date or "", responsible_org or "", "PLANNED", "",
         created_by, _now().isoformat(), _now().isoformat()))
    for uid in _team_user_ids(conn, project["team_id"]):
        add_notification(conn, uid, "pilot", "notif_pilot_opened",
                         f"A pilot was opened for project "
                         f"\"{project['title'][:60]}\" in {district}.",
                         "pilot", cur.lastrowid)
    for uid in _project_university_recipients_for(conn, project_id):
        add_notification(conn, uid, "pilot", "notif_pilot_opened",
                         f"A pilot was opened for project "
                         f"\"{project['title'][:60]}\".",
                         "pilot", cur.lastrowid)
    for uid in _connected_industry_users(conn, project_id):
        add_notification(conn, uid, "pilot", "notif_pilot_opened",
                         f"A pilot was opened for the project you collaborate "
                         f"on: \"{project['title'][:60]}\".",
                         "pilot", cur.lastrowid)
    add_challenge_log(conn, project["challenge_id"], "PILOT_OPENED",
                      f"Pilot opened for project \"{project['title'][:60]}\" "
                      f"in {district}.", created_by)
    conn.commit()
    return cur.lastrowid


def add_pilot_progress(conn, pilot_id, text, actor_id):
    """Append a dated progress update for a live pilot (PLANNED/ACTIVE/
    COMPLETED). Each line stores timestamp | author | text."""
    row = get_pilot_row(conn, pilot_id)
    if row is None:
        raise ValueError("Pilot not found.")
    if row["status"] not in PILOT_ACTIVE_STATUSES:
        raise ValueError("Progress can only be logged for a live pilot.")
    actor = get_user_by_id(conn, actor_id)
    by = actor["name"] if actor else str(actor_id)
    line = f"{_now().isoformat()}|{by}|{(text or '').strip()}"
    updates = (row["progress_updates"] or "").strip()
    updates = updates + ("\n" if updates else "") + line
    conn.execute("UPDATE pilot_deployments SET progress_updates=?, "
                 "updated_at=? WHERE id=?",
                 (updates, _now().isoformat(), pilot_id))
    project = get_project_row(conn, row["project_id"])
    if project:
        for uid in _team_user_ids(conn, project["team_id"]):
            add_notification(conn, uid, "pilot", "notif_pilot_updated",
                             f"A pilot progress update was logged for project "
                             f"\"{project['title'][:60]}\".",
                             "pilot", pilot_id)
        for uid in _connected_industry_users(conn, row["project_id"]):
            add_notification(conn, uid, "pilot", "notif_pilot_updated",
                             f"A pilot progress update was logged for the "
                             f"project you collaborate on: "
                             f"\"{project['title'][:60]}\".",
                             "pilot", pilot_id)
    conn.commit()


def set_pilot_status(conn, pilot_id, status, actor_id, comment=""):
    """PLANNED -> ACTIVE -> COMPLETED -> DEPLOYED. DEPLOYED is the terminal,
    honest state: an authorized reviewer completed the platform's deployment
    review — never an independent real-world verification claim."""
    if status not in PILOT_STATUSES:
        raise ValueError("Unknown pilot status.")
    row = get_pilot_row(conn, pilot_id)
    if row is None:
        raise ValueError("Pilot not found.")
    order = {"PLANNED": 0, "ACTIVE": 1, "COMPLETED": 2, "DEPLOYED": 3}
    if order.get(row["status"], 0) + 1 != order[status]:
        raise ValueError(f"Cannot move pilot from {row['status']} to {status}.")
    if status == "DEPLOYED":
        conn.execute(
            "UPDATE pilot_deployments SET status=?, deployment_review_comment=?, "
            "reviewed_by=?, reviewed_at=?, updated_at=? WHERE id=?",
            (status, comment or "", actor_id, _now().isoformat(),
             _now().isoformat(), pilot_id))
    else:
        conn.execute("UPDATE pilot_deployments SET status=?, updated_at=? "
                     "WHERE id=?", (status, _now().isoformat(), pilot_id))
    project = get_project_row(conn, row["project_id"])
    if project:
        notif_key = {
            "ACTIVE": "notif_pilot_active",
            "COMPLETED": "notif_pilot_completed",
            "DEPLOYED": "notif_pilot_deployed",
        }.get(status, "notif_pilot_updated")
        for uid in _team_user_ids(conn, project["team_id"]):
            add_notification(conn, uid, "pilot", notif_key,
                             f"The pilot for project "
                             f"\"{project['title'][:60]}\" is now "
                             f"{status.lower()}.",
                             "pilot", pilot_id)
        if status == "DEPLOYED":
            for uid in _connected_industry_users(conn, row["project_id"]):
                add_notification(conn, uid, "pilot", "notif_pilot_deployed",
                                 f"The solution you collaborate on — "
                                 f"\"{project['title'][:60]}\" — is marked "
                                 "deployed after the government deployment "
                                 "review.",
                                 "pilot", pilot_id)
            add_challenge_log(conn, project["challenge_id"], "DEPLOYED",
                              f"Solution for project "
                              f"\"{project['title'][:60]}\" marked deployed "
                              "after the deployment review.", actor_id)
    conn.commit()
    return status


def list_pilots(conn, mode="all"):
    if mode == "evaluation":
        q = ("SELECT * FROM pilot_deployments WHERE status='COMPLETED' "
             "ORDER BY updated_at DESC")
        args = ()
    elif mode == "overdue":
        q = ("SELECT * FROM pilot_deployments WHERE status IN "
             "('PLANNED','ACTIVE') ORDER BY target_end_date ASC")
        args = ()
    else:
        q = "SELECT * FROM pilot_deployments ORDER BY updated_at DESC"
        args = ()
    return [hydrate_pilot(conn, r)
            for r in conn.execute(q, args).fetchall()]


def list_pilots_for_university(conn, university_id):
    rows = conn.execute(
        "SELECT pd.* FROM pilot_deployments pd JOIN projects p "
        "ON p.id=pd.project_id WHERE p.university_id=? "
        "ORDER BY pd.updated_at DESC", (university_id,)).fetchall()
    return [hydrate_pilot(conn, r) for r in rows]


def list_pilots_for_org(conn, org_id):
    rows = conn.execute(
        "SELECT pd.* FROM pilot_deployments pd "
        "JOIN project_collaborations pc ON pc.project_id=pd.project_id "
        "WHERE pc.organization_id=? AND pc.status IN ('CONNECTED','ACTIVE') "
        "ORDER BY pd.updated_at DESC", (org_id,)).fetchall()
    return [hydrate_pilot(conn, r) for r in rows]


def count_pilots_needing_evaluation(conn):
    return conn.execute(
        "SELECT COUNT(*) c FROM pilot_deployments WHERE status='COMPLETED'"
    ).fetchone()["c"]


def count_pilots_overdue(conn):
    return conn.execute(
        "SELECT COUNT(*) c FROM pilot_deployments WHERE status IN "
        + _sql_in(("PLANNED", "ACTIVE"))
        + " AND target_end_date IS NOT NULL AND target_end_date < ?",
        (*("PLANNED", "ACTIVE"), _now().date().isoformat())).fetchone()["c"]


def list_pilot_eligible_projects(conn):
    """Live projects (born from APPROVED proposals) with both an APPROVED
    prototype and an APPROVED testing report and no pilot record yet — the
    only projects a government user may open a pilot for."""
    rows = conn.execute(
        "SELECT p.* FROM projects p JOIN proposals pr ON pr.id=p.proposal_id "
        "JOIN project_prototypes prot ON prot.project_id=p.id "
        "JOIN testing_reports tr ON tr.project_id=p.id "
        "WHERE pr.status='APPROVED' AND p.status IN ('CREATED','ACTIVE') "
        "AND prot.status='APPROVED' AND tr.status='APPROVED' "
        "AND NOT EXISTS (SELECT 1 FROM pilot_deployments pd "
        "               WHERE pd.project_id=p.id) "
        "ORDER BY p.created_at DESC").fetchall()
    return [hydrate_project(conn, r) for r in rows]
