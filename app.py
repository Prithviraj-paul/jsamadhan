"""
Jharkhand Samadhan — AI-Verified Citizen Complaint Platform.

Flask application entry point. Owns HTTP routes, session auth, file uploads,
EXIF GPS extraction, and the i18n language switcher. All persistence lives in
db.py (plain sqlite3); the "AI" verification lives in ai_engine.py (one real
Pillow-based before/after comparator + a deterministic simulated satellite
screen that is honesty-labelled in its own module).

Run:  python app.py    (Flask dev server on http://127.0.0.1:5000)
"""

import hashlib
import json
import os
import uuid
from collections import Counter
from datetime import datetime, timedelta

from flask import (
    Flask, render_template, request, redirect, url_for, session,
    flash, send_from_directory, g, jsonify,
)
from werkzeug.utils import secure_filename
from PIL import Image as PILImage
from PIL.ExifTags import TAGS

import db
import i18n
from ai_engine import (
    satellite_screen, compare_before_after, analyze_severity,
    verify_image_against_problem, detect_duplicates,
    match_challenge_to_university, industry_project_fit,
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
PROFILE_DIR = os.path.join(BASE_DIR, "static", "profile")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PROFILE_DIR, exist_ok=True)

ALLOWED_PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_VIDEO_EXT = {".mp4", ".mov"}
ALLOWED_EXT = ALLOWED_PHOTO_EXT | ALLOWED_VIDEO_EXT
PROFILE_EXT = {"png", "jpg", "jpeg", "webp", "gif"}

app = Flask(__name__)
app.secret_key = "jsamadhan-demo-secret-key"  # rotate in production
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

GOVERNMENT = ("admin", "officer")


def _photo_passes_content_check(path):
    """Reject files whose extension lies — Pillow must really decode them."""
    try:
        with PILImage.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


@app.errorhandler(413)
def _upload_too_large(_error):
    flash("File is too large — the maximum upload size is 50 MB. Please upload a smaller photo.", "error")
    return redirect(request.referrer or url_for("landing"))


# ---------------------------------------------------------------------------
# profile photo helpers
# ---------------------------------------------------------------------------

def save_profile_photo(file_storage):
    """Validate + resize an uploaded profile photo to a small square PNG."""
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in PROFILE_EXT:
        raise ValueError("Unsupported photo type. Please upload an image (JPG, PNG, WEBP or GIF).")
    try:
        file_storage.stream.seek(0)
        with PILImage.open(file_storage.stream) as image:
            image.thumbnail((256, 256))
            if image.mode in ("RGBA", "LA", "P"):
                image = image.convert("RGBA")
            else:
                image = image.convert("RGB")
            filename = f"{uuid.uuid4().hex}.png"
            image.save(os.path.join(PROFILE_DIR, filename), "PNG")
    except Exception:
        raise ValueError("The photo could not be read. Please choose a valid image.") from ValueError
    finally:
        file_storage.stream.seek(0)
    return filename


def _remove_profile_file(filename):
    if not filename:
        return
    try:
        os.remove(os.path.join(PROFILE_DIR, filename))
    except OSError:
        pass


def profile_photo_url(user):
    """Uploaded profile photo, or a Gravatar derived from the user's email."""
    photo = getattr(user, "profile_photo", None)
    if photo:
        return url_for("static", filename="profile/" + photo)
    email = (getattr(user, "email", "") or "").strip().lower()
    if not email:
        return None
    digest = hashlib.md5(email.encode("utf-8")).hexdigest()
    return f"https://www.gravatar.com/avatar/{digest}?d=identicon&s=128"


# i18n helpers must be Jinja *globals* so macros imported without
# "with context" can still call t()/cat_label()/dist_label().
app.jinja_env.globals.update({
    "t": i18n.t,
    "cat_label": i18n.cat_label,
    "dist_label": i18n.dist_label,
    "profile_photo_url": profile_photo_url,
})


def _run_duplicate_detection(conn, complaint_id):
    """AI-assisted duplicate scan for a complaint: compare it against every
    other report and every Official Challenge, then persist PENDING matches.
    Deterministic and fast (no external calls); called on citizen submission
    and when government opens a complaint that has no pending matches yet."""
    complaint_row = db.get_complaint_row(conn, complaint_id)
    if complaint_row is None:
        return []
    matches = detect_duplicates(complaint_row, conn, UPLOAD_DIR)
    stored = []
    for match in matches[:6]:
        if match["candidate_type"] == "complaint":
            mid = db.create_duplicate_match(
                conn, complaint_id,
                candidate_complaint_id=match["candidate_id"],
                confidence=match["confidence"], signals=match["signals"])
        else:
            mid = db.create_duplicate_match(
                conn, complaint_id,
                candidate_challenge_id=match["candidate_id"],
                confidence=match["confidence"], signals=match["signals"])
        stored.append((mid, match))
    return stored


def _run_university_matching(conn, challenge_id):
    """AI-assisted university matching for one Official Challenge: score every
    VERIFIED institution against the challenge, persist RECOMMENDED matches
    (idempotent), and return them ranked by score. Runs on government trigger
    or automatically when a challenge first becomes ready for matching."""
    challenge_row = db.get_challenge_row(conn, challenge_id)
    if challenge_row is None:
        return []
    universities = db.list_verified_universities(conn)
    stored = []
    for uni in universities:
        expertise = db.list_university_expertise(conn, uni.id)
        result = match_challenge_to_university(challenge_row, uni, expertise)
        mid = db.create_university_match(
            conn, challenge_id, uni.id, result["score"], result["level"],
            result["signals"])
        stored.append((mid, result))
    stored.sort(key=lambda item: item[1]["score"], reverse=True)
    return stored


def _ensure_university_matching_ready(conn):
    """Seed/start-up: run matching once for every validated challenge that has
    no university-match rows yet, so the Command Center shows live numbers."""
    rows = conn.execute(
        "SELECT id FROM challenges WHERE status IN ('VALIDATED','READY_FOR_MATCHING')"
    ).fetchall()
    for ch in rows:
        if not db.list_university_matches_for_challenge(conn, ch["id"]):
            _run_university_matching(conn, ch["id"])

# ---------------------------------------------------------------------------
# request lifecycle
# ---------------------------------------------------------------------------

@app.before_request
def _load_helpers():
    lang = session.get("lang", i18n.DEFAULT_LANG)
    if lang not in i18n.LANGUAGE_CODES:
        lang = i18n.DEFAULT_LANG
    g.lang = lang
    g.user = None
    uid = session.get("user_id")
    if uid:
        conn = db.get_db()
        g.user = db.hydrate_user(db.get_user_by_id(conn, uid))


@app.teardown_appcontext
def _close_db(exc):
    db.close_db(exc)


@app.context_processor
def _inject_helpers():
    nav_unread = 0
    if g.get("user") is not None:
        try:
            nav_unread = db.unread_notification_count(db.get_db(), g.user.id)
        except Exception:
            nav_unread = 0
    return {
        "t": i18n.t,
        "cat_label": i18n.cat_label,
        "dist_label": i18n.dist_label,
        "LANGS": i18n.LANGUAGES,
        "CUR_LANG": i18n.current_lang(),
        "current_lang_code": i18n.current_lang(),
        "CATEGORIES": db.CATEGORIES,
        "DISTRICTS": db.DISTRICTS,
        "user": g.get("user"),
        "current_user": g.get("user"),
        "now": datetime.utcnow,
        "nav_unread": nav_unread,
        "INDUSTRY_ORG_TYPES": db.INDUSTRY_ORG_TYPES,
        "COLLABORATION_TYPES": db.COLLABORATION_TYPES,
        "FUNDING_TYPES": db.FUNDING_TYPES,
    }


# ---------------------------------------------------------------------------
# auth helpers
# ---------------------------------------------------------------------------

def login_required(role=None):
    allowed = set(role) if isinstance(role, (tuple, set, list)) else ({role} if role else None)
    def deco(fn):
        from functools import wraps
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if g.get("user") is None:
                flash("Please log in first.", "error")
                return redirect(url_for("landing"))
            if allowed and g.user.role not in allowed:
                flash("You don't have access to that page.", "error")
                return redirect(url_for("landing"))
            return fn(*args, **kwargs)
        return wrapper
    return deco


# ---------------------------------------------------------------------------
# language switcher
# ---------------------------------------------------------------------------

@app.post("/set_lang")
def set_lang():
    lang = request.form.get("lang", i18n.DEFAULT_LANG)
    if lang in i18n.LANGUAGE_CODES:
        session["lang"] = lang
    return redirect(request.referrer or url_for("landing"))


# ---------------------------------------------------------------------------
# public pages
# ---------------------------------------------------------------------------

@app.route("/")
def landing():
    conn = db.get_db()
    total = conn.execute("SELECT COUNT(*) c FROM complaints").fetchone()["c"]
    open_ = conn.execute("SELECT COUNT(*) c FROM complaints WHERE status IN "
                          "('Submitted','Pending Officer Review','AI Verified',"
                          "'Accepted by Officer','Reopened','Escalated')").fetchone()["c"]
    resolved = conn.execute("SELECT COUNT(*) c FROM complaints WHERE status='Resolved'").fetchone()["c"]
    resolved_cases = db.list_recent_resolved(conn)
    return render_template("landing.html", stats={
        "total": total, "open": open_, "resolved": resolved,
    }, resolved_cases=resolved_cases)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        if not (name and email and phone and password):
            flash("Please fill in all fields.", "error")
            return redirect(url_for("register"))

        conn = db.get_db()
        if db.get_user_by_email(conn, email):
            flash("An account with that email already exists.", "error")
            return redirect(url_for("register"))

        user_id = db.create_user(conn, name, email, phone, password, "citizen")
        session["user_id"] = user_id
        session["role"] = "citizen"
        return redirect(url_for("citizen_dashboard"))

    role_param = request.args.get("role", "citizen")
    return render_template("register.html", role=role_param)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "citizen")

        conn = db.get_db()
        user_row = db.get_user_by_email_role(conn, email, role)
        user = db.hydrate_user(user_row)
        if user is None or not db.verify_password(user_row, password):
            flash("Invalid email, role, or password.", "error")
            return redirect(url_for("login"))

        session["user_id"] = user.id
        session["role"] = user.role
        return redirect(user.role == "citizen" and url_for("citizen_dashboard")
                        or user.role == "officer" and url_for("officer_dashboard")
                        or user.role == "university" and url_for("university_dashboard")
                        or user.role == "faculty" and url_for("faculty_dashboard")
                        or user.role == "student" and url_for("student_dashboard")
                        or user.role == "industry" and url_for("industry_dashboard")
                        or url_for("admin_dashboard"))

    return render_template("login.html", role=request.args.get("role"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


# ---------------------------------------------------------------------------
# citizens
# ---------------------------------------------------------------------------

@app.route("/citizen")
@login_required(role="citizen")
def citizen_dashboard():
    complaints = db.list_by_citizen(db.get_db(), g.user.id)
    return render_template("citizen_dashboard.html", complaints=complaints)


@app.route("/citizen/complaints")
@login_required(role="citizen")
def my_complaints():
    conn = db.get_db()
    complaints = db.list_by_citizen(conn, g.user.id)
    return render_template("my_complaints.html", complaints=complaints)


@app.route("/account", methods=["GET", "POST"])
@login_required()
def account():
    conn = db.get_db()
    user = g.user

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        alternate_phone = request.form.get("alternate_phone", "").strip()
        home_address = request.form.get("home_address", "").strip()

        errors = []
        if not (name and email and phone):
            errors.append("Please fill in your name, email and phone number.")
        existing = db.get_user_by_email(conn, email)
        if existing and existing["id"] != user.id:
            errors.append("That email is already used by another account.")

        action = request.form.get("action", "")
        photo = request.files.get("profile_photo")
        new_photo = None
        if photo and photo.filename:
            try:
                new_photo = save_profile_photo(photo)
            except ValueError as error:
                errors.append(str(error))

        if not errors:
            db.update_user_account(conn, user.id, name, email, phone,
                                   alternate_phone, home_address)
            if action == "remove_photo":
                _remove_profile_file(user.profile_photo)
                db.clear_profile_photo(conn, user.id)
            elif new_photo:
                _remove_profile_file(user.profile_photo)
                db.set_profile_photo(conn, user.id, new_photo)

        for message in errors:
            flash(message, "error")
        if not errors:
            flash(i18n.t("photo_removed") if action == "remove_photo"
                  else i18n.t("account_updated"), "success")

        user = db.hydrate_user(db.get_user_by_id(conn, user.id))
        g.user = user

    return render_template("account.html", user=user)


@app.route("/citizen/report", methods=["GET", "POST"])
@login_required(role="citizen")
def report_problem():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", db.CATEGORIES[0])
        district = request.form.get("district", db.DISTRICTS[0])
        location_text = request.form.get("location", "").strip()

        if not (title and description):
            flash("Please provide a title and description.", "error")
            return redirect(url_for("report_problem"))

        photo = request.files.get("evidence")
        photo_filename = None
        is_photo_video = 0
        ext = None
        if photo and photo.filename:
            ext = os.path.splitext(photo.filename)[1].lower()
            if ext not in ALLOWED_EXT:
                flash("Only JPG, PNG, WEBP, MP4 or MOV files are allowed.", "error")
                return redirect(url_for("report_problem"))
            safe = secure_filename(photo.filename)
            photo_filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{safe}"
            photo.save(os.path.join(UPLOAD_DIR, photo_filename))
            is_photo_video = 1 if ext in ALLOWED_VIDEO_EXT else 0
            if not is_photo_video and not _photo_passes_content_check(os.path.join(UPLOAD_DIR, photo_filename)):
                os.remove(os.path.join(UPLOAD_DIR, photo_filename))
                photo_filename = None
                flash("The photo could not be read. Please upload a valid image file (JPG, PNG or WEBP).", "error")
                return redirect(url_for("report_problem"))

        conn = db.get_db()
        code = db.new_complaint_code(conn)

        # Simulated GPS metadata for the uploaded evidence (Pillow EXIF hook).
        image_metadata = None
        image_taken_at = None
        image_lat = image_lon = None
        if ext and ext in ALLOWED_PHOTO_EXT:
            try:
                exif = PILImage.open(os.path.join(UPLOAD_DIR, photo_filename))._getexif()
                if exif:
                    md = {}
                    for tag, value in exif.items():
                        d = TAGS.get(tag, tag)
                        if isinstance(value, (str, int, float)):
                            md[str(d)] = str(value)
                    image_metadata = str(md)[:2000]
                    if "DateTimeOriginal" in md:
                        image_taken_at = md.get("DateTimeOriginal")
                    lat, lon = _extract_gps(exif, TAGS)
                    image_lat, image_lon = lat, lon
            except Exception:
                pass
        
        # Real AI: severity assessment from the uploaded evidence photo.
        result = analyze_severity(
            os.path.join(UPLOAD_DIR, photo_filename)
            if photo_filename and ext in ALLOWED_PHOTO_EXT else None,
            category,
        )
        severity = result["score"]
        urgency = result["urgency"]
        severity_note = result["note"]

        # Real AI: cross-check the photo against the reported problem.
        verify = None
        if photo_filename and ext in ALLOWED_PHOTO_EXT:
            verify = verify_image_against_problem(
                os.path.join(UPLOAD_DIR, photo_filename),
                title, description, category,
            )
        ai_detail = None
        if verify:
            ai_detail = json.dumps({k: verify[k] for k in
                                    ("confidence", "verified", "note", "signals",
                                     "warnings", "category", "threshold")},
                                   ensure_ascii=False)
        ai_confidence = verify["confidence"] if verify else None

        problem_id = db.create_complaint(
            conn,
            code=code,
            title=title,
            description=description,
            category=category,
            district=district,
            location_text=location_text,
            latitude=float(request.form.get("lat")) if request.form.get("lat") else None,
            longitude=float(request.form.get("lng")) if request.form.get("lng") else None,
            image_metadata=image_metadata,
            image_taken_at=image_taken_at,
            image_latitude=image_lat,
            image_longitude=image_lon,
            photo_filename=photo_filename,
            is_photo_video=is_photo_video,
            citizen_id=g.user.id,
            status="Submitted",
            severity=int(severity),
            urgency=urgency,
            ai_confidence=int(ai_confidence) if ai_confidence is not None else None,
            ai_note=(verify["note"] if verify else None),
            ai_detail=ai_detail,
            action_due_at=(datetime.utcnow() + timedelta(days=3)).isoformat(),
        )

        db.add_log(conn, problem_id, "Submitted", f"Complaint registered by citizen. {severity_note}")
        db.add_log(conn, problem_id, "Committed",
                   "Citizen will be notified within 24 hours. Officials will take action within 2\u20133 days, else the complaint is escalated to higher authority.")

        # AI-assisted duplicate detection: check against other reports and
        # existing Official Challenges; PENDING matches go to the Command
        # Center for government review. The AI never merges anything.
        _run_duplicate_detection(conn, problem_id)

        # Automated screening. For photos the REAL photo-vs-problem check runs;
        # for road/infrastructure complaints a satellite pass adds a second signal.
        photo_verified = bool(verify and verify.get("verified"))
        if category in db.INFRA_CATEGORIES:
            sat_conf, sat_note = satellite_screen(code, category, description)
            note = (f"Automated satellite screening (confidence {sat_conf}%). {sat_note}")
            if photo_verified:
                new_status = "AI Verified"
                note = f"{verify['note']} {note}"
            elif sat_conf >= 65:
                new_status = "AI Verified"
            else:
                new_status = "Pending Officer Review"
            db.set_status(conn, problem_id, new_status, note)
        else:
            new_status = "AI Verified" if photo_verified else "Pending Officer Review"
            if photo_verified:
                db.set_status(conn, problem_id, new_status, verify["note"])
            else:
                db.set_status(conn, problem_id, new_status,
                              (verify["note"] if verify else
                               "Awaiting manual verification by an officer."))

        return redirect(url_for("track_complaint", code=code))

    return render_template("report_problem.html")


@app.route("/track/<code>")
def track_complaint(code):
    conn = db.get_db()
    complaint = db.hydrate_complaint(conn, db.get_complaint_row(conn, code=code))
    if complaint is None:
        flash("Complaint not found.", "error")
        return redirect(url_for("landing"))
    return render_template("track_complaint.html", complaint=complaint, history=complaint.logs)


# ---------------------------------------------------------------------------
# officers
# ---------------------------------------------------------------------------

@app.route("/officer")
@login_required(role="officer")
def officer_dashboard():
    conn = db.get_db()
    queue = db.list_queue(conn)
    my_cases = db.list_my_cases(conn, g.user.id)
    resolved = db.list_resolved_by(conn, g.user.id)
    challenges = db.list_challenges(conn)
    for ch in challenges:
        ch.uni_summary = db.challenge_acceptance_summary(conn, ch.id)
    db.attach_lifecycle(conn, challenges)
    return render_template(
        "officer_dashboard.html",
        queue=queue, my_cases=my_cases, resolved=resolved,
        kpis=db.command_center_kpis(conn),
        actions=db.command_center_actions(conn),
        challenges=challenges,
        duplicate_alerts=db.list_pending_duplicates(conn),
    )


@app.route("/officer/complaint/<int:complaint_id>")
@login_required(role="officer")
def officer_complaint(complaint_id):
    conn = db.get_db()
    complaint = db.hydrate_complaint(conn, db.get_complaint_row(conn, complaint_id))
    if complaint is None:
        flash("Complaint not found.", "error")
        return redirect(url_for("officer_dashboard"))
    # Lazily scan a complaint that has never been duplicated-scaned before
    # (any prior outcome — CONFIRMED / NOT_DUPLICATE / DISMISSED — stands).
    if not db.list_duplicates_for_complaint(conn, complaint_id, status=None):
        _run_duplicate_detection(conn, complaint_id)
    pending = db.list_duplicates_for_complaint(conn, complaint_id, status="PENDING")
    return render_template("officer_complaint.html", complaint=complaint,
                           duplicate_matches=pending)


@app.route("/officer/accept/<int:complaint_id>", methods=["POST"])
@login_required(role="officer")
def officer_accept(complaint_id):
    conn = db.get_db()
    complaint = db.hydrate_complaint(conn, db.get_complaint_row(conn, complaint_id))
    if complaint is None or complaint.status not in ("Pending Officer Review", "AI Verified", "Reopened"):
        flash("This case can no longer be accepted here.", "error")
        return redirect(url_for("officer_dashboard"))

    sla_days = db.URGENCY_SLA_DAYS.get(complaint.urgency_key, db.RESOLUTION_WINDOW_DAYS)
    deadline = datetime.utcnow() + timedelta(days=sla_days)
    db.set_status(conn, complaint_id, "Accepted by Officer",
                  f"Accepted by {g.user.name}. Resolution due by {deadline:%Y-%m-%d} "
                  f"(SLA: {sla_days} days for {complaint.urgency_key} urgency).",
                  {"officer_id": g.user.id, "accepted_at": datetime.utcnow().isoformat(),
                   "deadline": deadline.isoformat()})
    return redirect(url_for("officer_complaint", complaint_id=complaint_id))


@app.route("/officer/reject/<int:complaint_id>", methods=["POST"])
@login_required(role="officer")
def officer_reject(complaint_id):
    conn = db.get_db()
    complaint = db.hydrate_complaint(conn, db.get_complaint_row(conn, complaint_id))
    reason = request.form.get("reason", "").strip()
    if complaint is None or complaint.status not in ("Pending Officer Review", "AI Verified"):
        flash("This case can no longer be rejected.", "error")
        return redirect(url_for("officer_dashboard"))
    db.set_status(conn, complaint_id, "Rejected", reason or "Rejected by officer.")
    return redirect(url_for("officer_complaint", complaint_id=complaint_id))


@app.route("/officer/resolve/<int:complaint_id>", methods=["POST"])
@login_required(role="officer")
def officer_resolve(complaint_id):
    conn = db.get_db()
    complaint = db.hydrate_complaint(conn, db.get_complaint_row(conn, complaint_id))
    if complaint is None or complaint.status not in ("Accepted by Officer", "Reopened"):
        flash("This case is not awaiting your resolution.", "error")
        return redirect(url_for("officer_dashboard"))

    photo = request.files.get("resolution")
    if not photo or not photo.filename:
        flash("Please upload a resolution photo.", "error")
        return redirect(url_for("officer_complaint", complaint_id=complaint_id))

    ext = os.path.splitext(photo.filename)[1].lower()
    if ext not in ALLOWED_PHOTO_EXT:
        flash("Resolution evidence must be a JPG, PNG, or WEBP image.", "error")
        return redirect(url_for("officer_complaint", complaint_id=complaint_id))

    safe = secure_filename(photo.filename)
    resolution_filename = f"res_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{safe}"
    photo.save(os.path.join(UPLOAD_DIR, resolution_filename))
    if not _photo_passes_content_check(os.path.join(UPLOAD_DIR, resolution_filename)):
        os.remove(os.path.join(UPLOAD_DIR, resolution_filename))
        flash("The resolution photo could not be read. Please upload a valid image file.", "error")
        return redirect(url_for("officer_complaint", complaint_id=complaint_id))

    # Real AI: compare before/after photos.
    before_path = os.path.join(UPLOAD_DIR, complaint.photo_filename) if complaint.photo_filename else None
    after_path = os.path.join(UPLOAD_DIR, resolution_filename)
    change_score, note = compare_before_after(before_path, after_path)

    if change_score is not None and change_score >= 10.0:
        db.set_status(conn, complaint_id, "Resolved",
                      f"{g.user.name} uploaded resolution evidence. {note}",
                      {"resolution_filename": resolution_filename,
                       "resolution_confidence": change_score,
                       "resolution_note": note,
                       "resolved_at": datetime.utcnow().isoformat()})
    else:
        db.set_status(conn, complaint_id, "Reopened",
                      f"{g.user.name} uploaded resolution evidence but {note}",
                      {"resolution_filename": resolution_filename,
                       "resolution_confidence": change_score,
                       "resolution_note": note})
    return redirect(url_for("officer_complaint", complaint_id=complaint_id))


# ---------------------------------------------------------------------------
# admin
# ---------------------------------------------------------------------------

@app.route("/admin")
@login_required(role="admin")
def admin_dashboard():
    conn = db.get_db()
    complaints = db.list_all_complaints(conn)
    officers = db.list_officers(conn)
    open_statuses = ("Submitted", "Pending Officer Review", "AI Verified",
                     "Accepted by Officer", "Reopened", "Escalated")
    kpis = {
        "total": len(complaints),
        "open": sum(1 for c in complaints if c.status in open_statuses),
        "resolved": sum(1 for c in complaints if c.status == "Resolved"),
        "overdue": sum(1 for c in complaints if c.is_overdue),
        "escalated": sum(1 for c in complaints if c.is_escalated),
        "critical": sum(1 for c in complaints if c.urgency == "critical"),
    }
    escalated = db.list_escalated(conn)
    return render_template("admin_dashboard.html", complaints=complaints,
                           officers=officers, kpis=kpis, escalated=escalated)


@app.route("/admin/complaint/<int:complaint_id>")
@login_required(role="admin")
def admin_complaint(complaint_id):
    conn = db.get_db()
    complaint = db.hydrate_complaint(conn, db.get_complaint_row(conn, complaint_id))
    if complaint is None:
        flash("Complaint not found.", "error")
        return redirect(url_for("admin_dashboard"))
    officers = db.list_officers(conn)
    if not db.list_duplicates_for_complaint(conn, complaint_id, status=None):
        _run_duplicate_detection(conn, complaint_id)
    pending = db.list_duplicates_for_complaint(conn, complaint_id, status="PENDING")
    return render_template("admin_complaint.html", complaint=complaint,
                           officers=officers, duplicate_matches=pending)


@app.route("/admin/assign/<int:complaint_id>", methods=["POST"])
@login_required(role="admin")
def admin_assign(complaint_id):
    conn = db.get_db()
    complaint = db.hydrate_complaint(conn, db.get_complaint_row(conn, complaint_id))
    officer_id = request.form.get("officer_id")
    if complaint is None or not officer_id:
        flash("Invalid assignment.", "error")
        return redirect(url_for("admin_dashboard"))

    sla_days = db.URGENCY_SLA_DAYS.get(complaint.urgency_key, db.RESOLUTION_WINDOW_DAYS)
    deadline = datetime.utcnow() + timedelta(days=sla_days)
    db.set_status(conn, complaint_id, "Accepted by Officer",
                  f"Assigned to officer by admin. Resolution due by {deadline:%Y-%m-%d} "
                  f"(SLA: {sla_days} days for {complaint.urgency_key} urgency).",
                  {"officer_id": int(officer_id), "accepted_at": datetime.utcnow().isoformat(),
                   "deadline": deadline.isoformat()})
    return redirect(url_for("admin_complaint", complaint_id=complaint_id))


@app.route("/admin/create_officer", methods=["POST"])
@login_required(role="admin")
def admin_create_officer():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "")

    if not (name and email and phone and password):
        flash("Please fill in all fields.", "error")
        return redirect(url_for("admin_dashboard"))

    conn = db.get_db()
    if db.get_user_by_email(conn, email):
        flash("An account with that email already exists.", "error")
        return redirect(url_for("admin_dashboard"))

    db.create_user(conn, name, email, phone, password, "officer")
    flash(f"Officer account created for {name}.", "success")
    return redirect(url_for("admin_dashboard"))


# ---------------------------------------------------------------------------
# Government Command Center — Official Challenges
# ---------------------------------------------------------------------------

def _challenge_ai_recommendation(complaints):
    """Deterministic, fully-local recommendation computed from the REAL linked
    citizen reports. AI proposes a priority — government validates the decision.
    complaints may be sqlite3.Row or hydrated complaint objects."""
    rows = list(complaints)
    n = len(rows)
    severities = [c["severity"] for c in rows if c["severity"] is not None]
    max_sev = max(severities) if severities else None
    evidence = sum(1 for c in rows if c["photo_filename"])
    cats = Counter(c["category"] for c in rows if c["category"])

    score = 15
    if max_sev is not None:
        score += int(max_sev * 0.55)
    score += min(n, 12)
    score = max(5, min(95, score))
    level = ("critical" if score >= 75 else "high" if score >= 50 else
             "normal" if score >= 25 else "low")
    confidence = int(max(55.0, min(95.0, 58 + (n - 1) * 5 + (4 if evidence else 0))))

    reasons = []
    if max_sev is not None:
        reasons.append(f"peak AI severity {max_sev}/100")
    reasons.append("1 citizen report" if n == 1 else f"{n} citizen reports")
    if evidence:
        reasons.append(f"{evidence} piece(s) of photo/video evidence")
    if not reasons:
        reasons.append("manual government review recommended")

    summary = (
        f"{n} citizen report(s) consolidate a single {level}-priority problem "
        f"(AI score {score}/100). {'; '.join(reasons)}. "
        "Government validation decides whether this challenge proceeds."
    )

    return {
        "score": score, "level": level, "confidence": confidence,
        "reason": "; ".join(reasons), "summary": summary,
        "category": cats.most_common(1)[0][0] if cats else db.CATEGORIES[0],
    }


@app.route("/admin/command-center")
@login_required(role="admin")
def admin_command_center():
    conn = db.get_db()
    challenges = db.list_challenges(conn)
    for ch in challenges:
        ch.uni_summary = db.challenge_acceptance_summary(conn, ch.id)
    db.attach_lifecycle(conn, challenges)
    return render_template(
        "officer_dashboard.html",
        queue=db.list_queue(conn),
        kpis=db.command_center_kpis(conn),
        actions=db.command_center_actions(conn),
        challenges=challenges,
        duplicate_alerts=db.list_pending_duplicates(conn),
    )


@app.route("/command-center")
@login_required(role=GOVERNMENT)
def command_center():
    if g.user.role == "admin":
        return redirect(url_for("admin_command_center"))
    return redirect(url_for("officer_dashboard"))


@app.route("/command-center/challenges/new", methods=["GET", "POST"])
@login_required(role=GOVERNMENT)
def new_challenge():
    conn = db.get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", db.CATEGORIES[0])
        subcategory = request.form.get("subcategory", "").strip() or None
        district = request.form.get("district", db.DISTRICTS[0])
        location_text = request.form.get("location", "").strip() or None
        lat = request.form.get("lat")
        lng = request.form.get("lng")

        if not (title and description):
            flash("Please provide a title and description for the challenge.", "error")
            return redirect(url_for("new_challenge"))

        complaint_ids = [int(x) for x in request.form.getlist("complaint_ids")
                         if x.strip().isdigit()]
        ids = list(dict.fromkeys(complaint_ids))
        confirmed = request.form.get("confirm_relink") == "1"

        rows = []
        conflicts = []
        for cid in ids:
            row = db.get_complaint_row(conn, cid)
            if row is None:
                continue
            if row["challenge_id"] is None or confirmed:
                rows.append(row)
            else:
                conflicts.append((row, db.get_challenge_row(conn, row["challenge_id"])))

        # Do not silently move complaints between challenges — the government
        # must explicitly confirm before reports already in another Official
        # Challenge are consolidated here.
        if conflicts:
            return _render_new_challenge_form(
                conn,
                preselect=ids,
                relink_warning=[{
                    "complaint_id": c["id"], "complaint_code": c["code"],
                    "complaint_title": c["title"],
                    "challenge_id": ch["id"], "challenge_code": ch["code"],
                    "challenge_title": ch["title"],
                } for c, ch in conflicts],
                form=request.form,
            )

        rec = _challenge_ai_recommendation(rows)
        priority_score, priority_level = rec["score"], rec["level"]
        if request.form.get("use_ai_priority") != "1":
            picked = request.form.get("priority_level", "").strip()
            if picked in ("critical", "high", "normal", "low"):
                priority_level = picked
            raw = request.form.get("priority_score", "").strip()
            if raw.isdigit():
                priority_score = max(0, min(100, int(raw)))

        challenge_id = db.create_challenge(
            conn,
            code=db.new_challenge_code(conn),
            title=title,
            description=description,
            category=category,
            subcategory=subcategory,
            district=district,
            location_text=location_text,
            latitude=float(lat) if lat else None,
            longitude=float(lng) if lng else None,
            priority_score=priority_score,
            priority_level=priority_level,
            ai_summary=rec["summary"],
            ai_confidence=rec["confidence"],
            created_by=g.user.id,
        )
        if rows:
            db.link_complaints_to_challenge(conn, challenge_id, [r["id"] for r in rows])
        db.add_challenge_log(conn, challenge_id, "NEEDS_VALIDATION",
                             f"Challenge created by {g.user.name}. "
                             "Government users notified via the command feed.", g.user.id)
        conn.commit()
        flash("Official challenge created — it is awaiting government validation.", "success")
        return redirect(url_for("challenge_detail", challenge_id=challenge_id))

    return _render_new_challenge_form(conn)


def _render_new_challenge_form(conn, preselect=None, relink_warning=None, form=None):
    seed = None
    preselect = preselect or []
    seed_id = request.args.get("complaint_id", type=int)
    if seed_id and seed_id not in preselect:
        seed_row = db.get_complaint_row(conn, seed_id)
        if seed_row and seed_row["challenge_id"] is None:
            seed = db.hydrate_complaint(conn, seed_row, with_relations=False)
            preselect = [seed_id] + preselect
    unlinked = db.list_unlinked_complaints(conn)
    seed_rows = [db.get_complaint_row(conn, cid) for cid in preselect]
    seed_rows = [r for r in seed_rows if r is not None]
    rec = _challenge_ai_recommendation(seed_rows)
    return render_template(
        "challenge_form.html",
        challenge=None, editing=False,
        unlinked=unlinked, preselect=preselect, seed=seed, ai=rec,
        relink_warning=relink_warning, form=form,
    )


@app.route("/command-center/challenges/<int:challenge_id>")
@login_required(role=GOVERNMENT)
def challenge_detail(challenge_id):
    conn = db.get_db()
    challenge = db.hydrate_challenge(conn, db.get_challenge_row(conn, challenge_id))
    if challenge is None:
        flash("Challenge not found.", "error")
        return redirect(url_for("command_center"))
    return render_template(
        "challenge_detail.html",
        challenge=challenge,
        unlinked=db.list_unlinked_complaints(conn),
        possible_reports=db.possible_additional_for_challenge(conn, challenge_id),
        uni_matches=db.list_university_matches_for_challenge(conn, challenge_id),
        uni_summary=db.challenge_acceptance_summary(conn, challenge_id),
        lifecycle=db.challenge_lifecycle(conn, challenge_id),
        proposals_review=db.list_proposals_for_challenge(conn, challenge_id),
    )


@app.route("/command-center/challenges/<int:challenge_id>/edit", methods=["GET", "POST"])
@login_required(role=GOVERNMENT)
def challenge_edit(challenge_id):
    conn = db.get_db()
    row = db.get_challenge_row(conn, challenge_id)
    if row is None:
        flash("Challenge not found.", "error")
        return redirect(url_for("command_center"))
    challenge = db.hydrate_challenge(conn, row, with_relations=False)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", db.CATEGORIES[0])
        subcategory = request.form.get("subcategory", "").strip() or None
        district = request.form.get("district", db.DISTRICTS[0])
        location_text = request.form.get("location", "").strip() or None
        lat = request.form.get("lat")
        lng = request.form.get("lng")
        if not (title and description):
            flash("Please provide a title and description.", "error")
            return redirect(url_for("challenge_edit", challenge_id=challenge_id))

        picked = request.form.get("priority_level", "").strip()
        priority_level = picked if picked in ("critical", "high", "normal", "low") else challenge.priority_level
        raw = request.form.get("priority_score", "").strip()
        priority_score = max(0, min(100, int(raw))) if raw.isdigit() else challenge.priority_score

        db.update_challenge(conn, challenge_id, g.user.id,
                            title=title, description=description,
                            category=category, subcategory=subcategory,
                            district=district, location_text=location_text,
                            latitude=float(lat) if lat else None,
                            longitude=float(lng) if lng else None,
                            priority_level=priority_level,
                            priority_score=priority_score)
        flash("Challenge updated.", "success")
        return redirect(url_for("challenge_detail", challenge_id=challenge_id))

    return render_template("challenge_form.html", challenge=challenge, editing=True,
                           unlinked=db.list_unlinked_complaints(conn),
                           preselect=[], seed=None, ai=None)


@app.post("/command-center/challenges/<int:challenge_id>/validate")
@login_required(role=GOVERNMENT)
def challenge_validate(challenge_id):
    conn = db.get_db()
    row = db.get_challenge_row(conn, challenge_id)
    if row is None:
        flash("Challenge not found.", "error")
        return redirect(url_for("command_center"))
    if row["validation_status"] != "NEEDS_VALIDATION":
        flash("This challenge has already gone through validation.", "error")
        return redirect(url_for("challenge_detail", challenge_id=challenge_id))
    db.validate_challenge(conn, challenge_id, g.user.id)
    flash("Challenge validated and ready for institution matching.", "success")
    return redirect(url_for("challenge_detail", challenge_id=challenge_id))


@app.post("/command-center/challenges/<int:challenge_id>/reject")
@login_required(role=GOVERNMENT)
def challenge_reject(challenge_id):
    conn = db.get_db()
    row = db.get_challenge_row(conn, challenge_id)
    if row is None:
        flash("Challenge not found.", "error")
        return redirect(url_for("command_center"))
    if row["validation_status"] != "NEEDS_VALIDATION":
        flash("This challenge can no longer be rejected.", "error")
        return redirect(url_for("challenge_detail", challenge_id=challenge_id))
    reason = request.form.get("reason", "").strip()
    db.reject_challenge(conn, challenge_id, reason, g.user.id)
    flash("Challenge rejected.", "success")
    return redirect(url_for("challenge_detail", challenge_id=challenge_id))


@app.post("/command-center/challenges/<int:challenge_id>/link")
@login_required(role=GOVERNMENT)
def challenge_link(challenge_id):
    conn = db.get_db()
    row = db.get_challenge_row(conn, challenge_id)
    if row is None:
        flash("Challenge not found.", "error")
        return redirect(url_for("command_center"))
    ids = [int(x) for x in request.form.getlist("complaint_ids") if x.strip().isdigit()]
    confirmed = request.form.get("confirm_relink") == "1"
    match_id = request.form.get("match_id", type=int)
    valid, skipped = [], []
    for cid in dict.fromkeys(ids):
        cr = db.get_complaint_row(conn, cid)
        if cr and cr["challenge_id"] is None:
            valid.append(cid)
        elif cr and confirmed:
            valid.append(cid)
        elif cr:
            skipped.append(cr)
    if valid:
        db.link_complaints_to_challenge(conn, challenge_id, valid)
        db.add_challenge_log(conn, challenge_id, "Updated",
                             f"Linked {len(valid)} citizen report(s) to this challenge.",
                             g.user.id)
        conn.commit()
        if match_id:
            db.review_duplicate_match(conn, match_id, "CONFIRMED", g.user.id,
                                      "Duplicate confirmed — report linked to the Official Challenge.")
            conn.commit()
        flash(f"Linked {len(valid)} citizen report(s) to this challenge.", "success")
    if skipped:
        flash(f"{len(skipped)} report(s) already belong to another Official Challenge "
              "and were not moved (re-select with the confirm option to override).", "error")
    if not valid and not skipped:
        flash("No new unlinked reports were selected.", "error")
    return redirect(url_for("challenge_detail", challenge_id=challenge_id))


@app.post("/command-center/challenges/<int:challenge_id>/match")
@login_required(role=GOVERNMENT)
def challenge_run_matching(challenge_id):
    """Government explicitly triggers AI university matching for a validated
    challenge. The AI recommends — government decides who gets invited."""
    conn = db.get_db()
    row = db.get_challenge_row(conn, challenge_id)
    if row is None:
        flash("Challenge not found.", "error")
        return redirect(url_for("command_center"))
    if row["validation_status"] != "VALIDATED":
        flash("Only government-validated challenges can be matched to institutions.", "error")
        return redirect(url_for("challenge_detail", challenge_id=challenge_id))
    results = _run_university_matching(conn, challenge_id)
    db.add_challenge_log(conn, challenge_id, "READY_FOR_MATCHING",
                         f"AI university matching run across "
                         f"{len(results)} verified institution(s).", g.user.id)
    conn.commit()
    flash(f"University matching complete — "
          f"{len(results)} AI recommendation(s) generated.", "success")
    return redirect(url_for("challenge_detail", challenge_id=challenge_id))


@app.post("/command-center/matches/<int:match_id>/invite")
@login_required(role=GOVERNMENT)
def uni_match_invite(match_id):
    """Government invites a recommended university. Only a RECOMMENDED match
    can become INVITED."""
    conn = db.get_db()
    match = db.get_university_match(conn, match_id)
    if match is None:
        flash("University recommendation not found.", "error")
        return redirect(url_for("officer_dashboard"))
    if match.status != "RECOMMENDED":
        flash("This recommendation can no longer be invited.", "error")
        return redirect(url_for("challenge_detail", challenge_id=match.challenge_id))
    db.invite_university_match(conn, match_id, g.user.id)
    conn.commit()
    uni_name = match.university.name if match.university else "the institution"
    flash(f"Invitation sent to {uni_name}.", "success")
    return redirect(url_for("challenge_detail", challenge_id=match.challenge_id))


@app.post("/command-center/matches/<int:match_id>/remove")
@login_required(role=GOVERNMENT)
def uni_match_remove(match_id):
    conn = db.get_db()
    match = db.get_university_match(conn, match_id)
    if match is None:
        flash("University recommendation not found.", "error")
        return redirect(url_for("officer_dashboard"))
    if match.status not in ("RECOMMENDED", "INVITED"):
        flash("A decided invitation can no longer be removed here.", "error")
        return redirect(url_for("challenge_detail", challenge_id=match.challenge_id))
    db.remove_university_match(conn, match_id, g.user.id)
    conn.commit()
    flash("Recommendation removed.", "success")
    return redirect(url_for("challenge_detail", challenge_id=match.challenge_id))


@app.route("/duplicate/<int:match_id>/dismiss", methods=["POST"])
@app.route("/duplicate/<int:match_id>/not-related", methods=["POST"])
@login_required(role=GOVERNMENT)
def review_duplicate(match_id):
    conn = db.get_db()
    match = db.get_duplicate_match(conn, match_id)
    if match is None:
        flash("Duplicate alert not found.", "error")
        return redirect(url_for("officer_dashboard"))
    if request.form.get("not-related"):
        status = "NOT_DUPLICATE"
        msg = "Marked as NOT a duplicate — flagged report is a separate problem."
    else:
        status = "DISMISSED"
        msg = "Duplicate alert dismissed (no further action)."
    db.review_duplicate_match(conn, match_id, status, g.user.id, msg)
    conn.commit()
    flash(msg, "success")
    back = request.form.get("next") or url_for("officer_dashboard")
    return redirect(back)


@app.route("/duplicate/<int:match_id>/link", methods=["POST"])
@login_required(role=GOVERNMENT)
def duplicate_link_to_challenge(match_id):
    """Government confirms an AI match and consolidates the flagged report
    into the matched Official Challenge."""
    conn = db.get_db()
    match = db.get_duplicate_match(conn, match_id)
    if match is None:
        flash("Duplicate alert not found.", "error")
        return redirect(url_for("officer_dashboard"))
    if match.candidate_challenge_id is None:
        flash("This alert compares two citizen reports — group them into a new "
              "Official Challenge instead.", "error")
        return redirect(url_for("officer_dashboard"))
    challenge = db.hydrate_challenge(
        conn, db.get_challenge_row(conn, match.candidate_challenge_id))
    complaint = db.hydrate_complaint(
        conn, db.get_complaint_row(conn, match.complaint_id), with_relations=False)
    if challenge is None or complaint is None:
        flash("Alert references data that no longer exists.", "error")
        return redirect(url_for("officer_dashboard"))

    # Already linked? Nothing to move — just confirm the match.
    if complaint.challenge_id != challenge.id:
        if complaint.challenge_id is not None:
            flash(f"Report {complaint.code} belongs to another Official "
                  f"Challenge already — link it from there to confirm.", "error")
            return redirect(url_for("officer_dashboard"))
        db.link_complaints_to_challenge(conn, challenge.id, [complaint.id])
        db.add_challenge_log(
            conn, challenge.id, "Updated",
            f"Linked {complaint.code} to this challenge during AI duplicate review.",
            g.user.id)
    db.review_duplicate_match(conn, match_id, "CONFIRMED", g.user.id,
                              "Duplicate confirmed — report consolidated into the Official Challenge.")
    conn.commit()
    flash(f"Report {complaint.code} consolidated into {challenge.code}.", "success")
    back = request.form.get("next") or url_for("officer_dashboard")
    return redirect(back)


@app.route("/duplicate/<int:match_id>/confirm", methods=["POST"])
@login_required(role=GOVERNMENT)
def duplicate_confirm(match_id):
    """Government confirms that the flagged pair ARE the same problem.
    Used for report-vs-challenge matches when the officer prefers to keep
    reviewing before linking, and for report-vs-report matches."""
    conn = db.get_db()
    match = db.get_duplicate_match(conn, match_id)
    if match is None:
        flash("Duplicate alert not found.", "error")
        return redirect(url_for("officer_dashboard"))
    db.review_duplicate_match(conn, match_id, "CONFIRMED", g.user.id,
                              "Duplicate confirmed by government review.")
    conn.commit()
    flash("Match confirmed as a duplicate.", "success")
    back = request.form.get("next") or url_for("officer_dashboard")
    return redirect(back)


# ---------------------------------------------------------------------------
# University / institution portal (Phase 3)
# ---------------------------------------------------------------------------

def _require_university(conn):
    """Hydrated university for the logged-in user, or None. Role-guarded: a
    university admin only ever reaches their own institution."""
    uni = db.get_university_for_user(conn, g.user)
    if uni is None:
        flash("No institution profile is linked to your account.", "error")
        return None
    return uni


@app.route("/university")
@login_required(role="university")
def university_dashboard():
    conn = db.get_db()
    uni = _require_university(conn)
    if uni is None:
        return redirect(url_for("landing"))
    matches = db.list_university_matches_for_institution(conn, uni.id)
    kpis = {
        "matched": len(matches),
        "pending_review": sum(1 for m in matches if m.status == "INVITED"),
        "accepted": sum(1 for m in matches if m.status == "ACCEPTED"),
        "declined": sum(1 for m in matches if m.status == "DECLINED"),
        "active_participation": sum(1 for m in matches if m.status == "ACCEPTED"),
        "faculty": db.count_faculty(conn, uni.id),
        "students": db.count_students(conn, uni.id),
    }
    teams = db.list_teams_for_university(conn, uni.id)
    proposals = db.list_proposals_for_university(conn, uni.id)
    projects = db.list_projects_for_university(conn, uni.id)
    collaborations = db.list_collaborations_for_university(conn, uni.id)
    kpis["future_projects"] = len(projects)
    kpis["teams"] = len(teams)
    kpis["proposals"] = len(proposals)
    return render_template("university_dashboard.html", uni=uni, matches=matches,
                           teams=teams, proposals=proposals, projects=projects,
                           kpis=kpis, collaborations=collaborations)


@app.route("/university/profile", methods=["GET", "POST"])
@login_required(role="university")
def university_profile():
    conn = db.get_db()
    uni = _require_university(conn)
    if uni is None:
        return redirect(url_for("landing"))
    if request.method == "POST":
        try:
            db.update_university(conn, uni.id,
                name=request.form.get("name", "").strip() or uni.name,
                short_name=request.form.get("short_name", "").strip() or None,
                phone=request.form.get("phone", "").strip() or None,
                address=request.form.get("address", "").strip() or None,
                district=request.form.get("district") or uni.district,
                website=request.form.get("website", "").strip() or None,
                description=request.form.get("description", "").strip() or None,
                institution_type=request.form.get("institution_type") or uni.institution_type)
            flash("University profile updated.", "success")
        except Exception as exc:
            flash(f"Could not update profile: {exc}", "error")
        return redirect(url_for("university_profile"))
    return render_template("university_profile.html", uni=uni,
                           uni_types=db.UNIVERSITY_TYPES)


@app.route("/university/expertise", methods=["GET", "POST"])
@login_required(role="university")
def university_expertise():
    conn = db.get_db()
    uni = _require_university(conn)
    if uni is None:
        return redirect(url_for("landing"))
    if request.method == "POST":
        department = request.form.get("department", "").strip()
        expertise = request.form.get("expertise", "").strip()
        if not (department and expertise):
            flash("Department and expertise are required.", "error")
            return redirect(url_for("university_expertise"))
        db.create_university_expertise(conn, uni.id, department, expertise,
            research_area=request.form.get("research_area", "").strip(),
            keywords=request.form.get("keywords", "").strip(),
            lab_capabilities=request.form.get("lab_capabilities", "").strip(),
            description=request.form.get("description", "").strip())
        flash("Expertise area added — it improves AI matching.", "success")
        return redirect(url_for("university_expertise"))
    return render_template("university_expertise.html", uni=uni,
                           expertise=db.list_university_expertise(conn, uni.id))


@app.post("/university/expertise/<int:expertise_id>/delete")
@login_required(role="university")
def university_expertise_delete(expertise_id):
    conn = db.get_db()
    uni = _require_university(conn)
    if uni is None:
        return redirect(url_for("landing"))
    db.delete_university_expertise(conn, expertise_id, uni.id)
    flash("Expertise area deleted.", "success")
    return redirect(url_for("university_expertise"))


@app.route("/university/challenges")
@login_required(role="university")
def university_challenges():
    conn = db.get_db()
    uni = _require_university(conn)
    if uni is None:
        return redirect(url_for("landing"))
    matches = db.list_university_matches_for_institution(conn, uni.id)
    return render_template("university_challenges.html", uni=uni, matches=matches)


@app.route("/university/challenges/<int:match_id>")
@login_required(role=("university", "faculty", "student"))
def university_challenge_detail(match_id):
    conn = db.get_db()
    uni = db.get_university_for_user(conn, g.user)
    match = db.get_university_match(conn, match_id)
    if uni is None or match is None or match.university_id != uni.id:
        flash("This challenge is not accessible to your account.", "error")
        back = {"university": "university_challenges",
                "faculty": "faculty_dashboard",
                "student": "student_dashboard"}.get(g.user.role, "landing")
        return redirect(url_for(back))
    challenge = db.hydrate_challenge(conn, db.get_challenge_row(conn, match.challenge_id),
                                     with_relations=False)
    if challenge is None:
        flash("Challenge not found.", "error")
        return redirect(url_for("university_challenges"))
    my_team = next((t for t in db.list_teams_for_challenge(
        conn, challenge.id) if t.university_id == uni.id), None)
    return render_template("university_challenge_detail.html", uni=uni, match=match,
                           challenge=challenge, my_team=my_team,
                           lifecycle=db.challenge_lifecycle(conn, challenge.id))


@app.post("/university/challenges/<int:match_id>/accept")
@login_required(role="university")
def university_accept(match_id):
    return _university_respond(match_id, accept=True)


@app.post("/university/challenges/<int:match_id>/decline")
@login_required(role="university")
def university_decline(match_id):
    return _university_respond(match_id, accept=False)


def _university_respond(match_id, accept):
    conn = db.get_db()
    uni = _require_university(conn)
    if uni is None:
        return redirect(url_for("landing"))
    match = db.get_university_match(conn, match_id)
    if match is None or match.university_id != uni.id:
        flash("Invitation not found or not accessible.", "error")
        return redirect(url_for("university_challenges"))
    if match.status != "INVITED":
        flash("This invitation is no longer awaiting a response.", "error")
        return redirect(url_for("university_challenge_detail", match_id=match_id))
    note = request.form.get("response_note", "").strip()
    if not accept and not note:
        flash("Please provide a short reason for declining.", "error")
        return redirect(url_for("university_challenge_detail", match_id=match_id))
    db.respond_university_match(conn, match_id, accept, note, g.user.id)
    conn.commit()
    flash("Challenge accepted — thank you for taking it on." if accept
          else "Challenge declined.", "success")
    return redirect(url_for("university_challenge_detail", match_id=match_id))


# ---------------------------------------------------------------------------
# Phase 4 — teams, proposals and projects after university acceptance
# ---------------------------------------------------------------------------

def _uni_context(conn):
    """Institution linked to the logged-in user for any portal role."""
    return db.get_university_for_user(conn, g.user)


def _team_guard(conn, team_id):
    """Server-side team gate. Allows: the owning university's admin account,
    government readers, and faculty/student accounts of the SAME institution
    (members see full detail; non-members see the team for joining). Denies
    citizens and every other institution. Never trusts URL/form IDs."""
    team = db.get_team(conn, team_id)
    if team is None:
        flash("Team not found.", "error")
        return None
    if g.user.role == "citizen":
        flash("You don't have access to that page.", "error")
        return None
    uni = _uni_context(conn)
    same_uni = uni is not None and team.university_id == uni.id
    is_gov = g.user.role in GOVERNMENT
    is_uni_admin = g.user.role == "university" and same_uni
    is_portal_member = g.user.role in ("faculty", "student") and same_uni
    if not (is_gov or is_uni_admin or is_portal_member):
        flash("This team is not accessible to your account.", "error")
        return None
    member = (db.get_team_member(conn, team_id, g.user.id)
              if g.user.role in ("faculty", "student") else None)
    return {
        "team": team, "uni": uni,
        "is_gov": is_gov,
        "is_admin": is_uni_admin,
        "is_member": bool(member) and member["status"] == "ACTIVE",
        "member": member,
    }


def _proposal_guard(conn, proposal_id):
    """Server-side proposal gate: government reviewers, the owning university
    admin, or an active member of the proposing team. Everything else denied."""
    proposal = db.get_proposal(conn, proposal_id)
    if proposal is None:
        flash("Proposal not found.", "error")
        return None
    if g.user.role == "citizen":
        flash("You don't have access to that page.", "error")
        return None
    uni = _uni_context(conn)
    is_gov = g.user.role in GOVERNMENT
    is_own_uni = uni is not None and proposal.university_id == uni.id
    is_admin = g.user.role == "university" and is_own_uni
    member = None
    if g.user.role in ("faculty", "student") and is_own_uni:
        member = db.get_team_member(conn, proposal.team_id, g.user.id)
    is_member = bool(member) and member["status"] == "ACTIVE"
    if not (is_gov or is_admin or is_member):
        flash("This proposal is not accessible to your account.", "error")
        return None
    return {
        "proposal": proposal, "uni": uni,
        "is_gov": is_gov, "is_admin": is_admin, "is_member": is_member,
        "member": member,
    }


def _portal_back(g):
    return {"university": "university_dashboard", "faculty": "faculty_dashboard",
            "student": "student_dashboard", "admin": "admin_command_center",
            "officer": "officer_dashboard"}.get(g.user.role, "landing")


@app.route("/university/teams")
@login_required(role=("university", "faculty", "student"))
def university_teams():
    conn = db.get_db()
    uni = _uni_context(conn)
    if uni is None:
        flash("No institution profile is linked to your account.", "error")
        return redirect(url_for("landing"))
    teams = db.list_teams_for_university(conn, uni.id)
    return render_template("university_teams.html", uni=uni, teams=teams)


@app.route("/university/challenges/<int:match_id>/team/new", methods=["GET", "POST"])
@login_required(role="university")
def team_new(match_id):
    conn = db.get_db()
    uni = _uni_context(conn)
    if uni is None:
        flash("No institution profile is linked to your account.", "error")
        return redirect(url_for("landing"))
    match = db.get_university_match(conn, match_id)
    if match is None or match.university_id != uni.id:
        flash("Challenge invitation not found.", "error")
        return redirect(url_for("university_challenges"))
    if match.status != "ACCEPTED":
        flash("A team can only be created for a challenge your institution "
              "has accepted.", "error")
        return redirect(url_for("university_challenge_detail", match_id=match_id))
    challenge = db.hydrate_challenge(
        conn, db.get_challenge_row(conn, match.challenge_id), with_relations=False)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        if not name:
            flash("A team name is required.", "error")
            return render_template("team_new.html", uni=uni, match=match,
                                   challenge=challenge, form=request.form)
        team_id = db.create_team(conn, match.challenge_id, uni.id,
                                 name, description, g.user.id)
        flash("Team created — add faculty and students, then build your "
              "proposal.", "success")
        return redirect(url_for("team_details", team_id=team_id))
    return render_template("team_new.html", uni=uni, match=match,
                           challenge=challenge, form=None)


@app.route("/university/teams/<int:team_id>")
@login_required(role=("university", "faculty", "student", "admin", "officer"))
def team_details(team_id):
    conn = db.get_db()
    ctx = _team_guard(conn, team_id)
    if ctx is None:
        return redirect(url_for(_portal_back(g)))
    candidates = []
    if ctx["is_admin"]:
        candidates = db.list_university_members(conn, ctx["team"].university_id,
                                                team_id)
    return render_template("team_detail.html", **ctx, candidates=candidates)


@app.post("/university/teams/<int:team_id>/members/add")
@login_required(role="university")
def team_add_member(team_id):
    conn = db.get_db()
    team = db.get_team_row(conn, team_id)
    if team is None:
        flash("Team not found.", "error")
        return redirect(url_for("university_teams"))
    uni = db.get_university_by_admin(conn, g.user.id)
    if uni is None or uni["id"] != team["university_id"]:
        flash("You are not the administrator of this team's institution.", "error")
        return redirect(url_for("university_teams"))
    if not db.challenge_accepted_by_university(
            conn, team["challenge_id"], team["university_id"]):
        flash("This challenge is no longer accepted by your institution.", "error")
        return redirect(url_for("team_details", team_id=team_id))
    user_id = request.form.get("user_id", type=int)
    member_role = request.form.get("member_role", "").strip()
    if not user_id or member_role not in db.TEAM_MEMBER_ROLES:
        flash("Select a member and a valid team role.", "error")
        return redirect(url_for("team_details", team_id=team_id))
    member = db.hydrate_user(db.get_user_by_id(conn, user_id))
    if member is None:
        flash("Member not found.", "error")
        return redirect(url_for("team_details", team_id=team_id))
    if member.role == "faculty" and member_role not in ("FACULTY", "FACULTY_LEAD"):
        flash("A faculty member can only be added as Faculty or Faculty Lead.", "error")
        return redirect(url_for("team_details", team_id=team_id))
    if member.role == "student" and member_role not in ("STUDENT", "TEAM_LEAD"):
        flash("A student can only be added as Student or Team Lead.", "error")
        return redirect(url_for("team_details", team_id=team_id))
    if db.get_team_member(conn, team_id, user_id):
        flash("That person is already a member of this team.", "error")
        return redirect(url_for("team_details", team_id=team_id))
    if member_role == "FACULTY_LEAD":
        current = conn.execute(
            "SELECT user_id FROM team_members WHERE team_id=? AND member_role="
            "'FACULTY_LEAD' AND status='ACTIVE'", (team_id,)).fetchone()
        if current:
            db.update_team_member_role(conn, team_id, current["user_id"], "FACULTY")
            flash("Previous faculty lead moved to Faculty.", "success")
    db.add_team_member(conn, team_id, user_id, member_role)
    flash(f"{member.name} added to the team as {member_role}.", "success")
    return redirect(url_for("team_details", team_id=team_id))


@app.post("/university/teams/<int:team_id>/members/<int:user_id>/remove")
@login_required(role="university")
def team_remove_member(team_id, user_id):
    conn = db.get_db()
    team = db.get_team_row(conn, team_id)
    if team is None:
        flash("Team not found.", "error")
        return redirect(url_for("university_teams"))
    uni = db.get_university_by_admin(conn, g.user.id)
    if uni is None or uni["id"] != team["university_id"]:
        flash("You are not the administrator of this team's institution.", "error")
        return redirect(url_for("university_teams"))
    db.remove_team_member(conn, team_id, user_id, g.user.id)
    flash("Member removed from the team.", "success")
    return redirect(url_for("team_details", team_id=team_id))


@app.post("/university/teams/<int:team_id>/join")
@login_required(role=("faculty", "student"))
def team_join(team_id):
    conn = db.get_db()
    team = db.get_team(conn, team_id)
    uni = _uni_context(conn)
    if team is None or uni is None or team.university_id != uni.id:
        flash("This team is not open to your account.", "error")
        return redirect(url_for(_portal_back(g)))
    if not team.accepted:
        flash("This team belongs to a challenge your institution no longer "
              "accepts.", "error")
        return redirect(url_for(_portal_back(g)))
    if db.get_team_member(conn, team_id, g.user.id):
        flash("You are already a member of this team.", "error")
        return redirect(url_for("team_details", team_id=team_id))
    self_role = "FACULTY" if g.user.role == "faculty" else "STUDENT"
    db.add_team_member(conn, team_id, g.user.id, self_role)
    flash("You joined the team.", "success")
    return redirect(url_for("team_details", team_id=team_id))


@app.route("/university/teams/<int:team_id>/proposals/new", methods=["GET", "POST"])
@login_required(role=("university", "faculty", "student"))
def proposal_new(team_id):
    conn = db.get_db()
    team = db.get_team(conn, team_id)
    if team is None:
        flash("Team not found.", "error")
        return redirect(url_for("university_teams"))
    uni = _uni_context(conn)
    if uni is None or team.university_id != uni.id or not team.accepted:
        flash("This team is not open to your account.", "error")
        return redirect(url_for(_portal_back(g)))
    if g.user.role == "university":
        if db.get_university_by_admin(conn, g.user.id) is None or \
                db.get_university_by_admin(conn, g.user.id)["id"] != uni.id:
            flash("You are not the administrator of this institution.", "error")
            return redirect(url_for(_portal_back(g)))
    elif not db.get_team_member(conn, team_id, g.user.id):
        flash("Only team members can create a proposal for this team.", "error")
        return redirect(url_for(_portal_back(g)))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        problem = request.form.get("problem_statement", "").strip()
        solution = request.form.get("proposed_solution", "").strip()
        method = request.form.get("methodology", "").strip()
        outcome = request.form.get("expected_outcome", "").strip()
        resources = request.form.get("required_resources", "").strip()
        duration = request.form.get("estimated_duration", "").strip()
        if not (title and problem and solution and method):
            flash("Title, problem statement, proposed solution and methodology "
                  "are required.", "error")
            return render_template(
                "proposal_new.html", team=team, uni=uni,
                form={"title": title, "problem_statement": problem,
                      "proposed_solution": solution, "methodology": method,
                      "expected_outcome": outcome,
                      "required_resources": resources,
                      "estimated_duration": duration})
        proposal_id = db.create_proposal(
            conn, team.challenge_id, team.university_id, team_id, title,
            problem, solution, method, outcome, resources, duration, g.user.id)
        flash("Proposal draft created.", "success")
        return redirect(url_for("proposal_detail", proposal_id=proposal_id))
    return render_template("proposal_new.html", team=team, uni=uni, form=None)


@app.route("/university/proposals/<int:proposal_id>")
@login_required(role=("university", "faculty", "student", "admin", "officer"))
def proposal_detail(proposal_id):
    conn = db.get_db()
    ctx = _proposal_guard(conn, proposal_id)
    if ctx is None:
        return redirect(url_for(_portal_back(g)))
    return render_template("proposal_detail.html", **ctx)


@app.post("/university/proposals/<int:proposal_id>/edit")
@login_required(role=("university", "faculty", "student"))
def proposal_edit(proposal_id):
    conn = db.get_db()
    ctx = _proposal_guard(conn, proposal_id)
    if ctx is None or not (ctx["is_admin"] or ctx["is_member"]):
        flash("You cannot edit this proposal.", "error")
        return redirect(url_for(_portal_back(g)))
    if ctx["proposal"].status not in ("DRAFT", "REVISION_REQUESTED"):
        flash("Only a draft or a revision-requested proposal can be edited.", "error")
        return redirect(url_for("proposal_detail", proposal_id=proposal_id))
    title = request.form.get("title", "").strip()
    problem = request.form.get("problem_statement", "").strip()
    solution = request.form.get("proposed_solution", "").strip()
    method = request.form.get("methodology", "").strip()
    outcome = request.form.get("expected_outcome", "").strip()
    resources = request.form.get("required_resources", "").strip()
    duration = request.form.get("estimated_duration", "").strip()
    if not (title and problem and solution and method):
        flash("Title, problem statement, proposed solution and methodology "
              "are required.", "error")
        return redirect(url_for("proposal_detail", proposal_id=proposal_id))
    db.update_proposal(conn, proposal_id, g.user.id,
                       title=title, problem_statement=problem,
                       proposed_solution=solution, methodology=method,
                       expected_outcome=outcome,
                       required_resources=resources,
                       estimated_duration=duration)
    conn.commit()
    flash("Proposal updated.", "success")
    return redirect(url_for("proposal_detail", proposal_id=proposal_id))


@app.post("/university/proposals/<int:proposal_id>/submit")
@login_required(role=("university", "faculty", "student"))
def proposal_submit(proposal_id):
    conn = db.get_db()
    ctx = _proposal_guard(conn, proposal_id)
    if ctx is None or not (ctx["is_admin"] or ctx["is_member"]):
        flash("You cannot submit this proposal.", "error")
        return redirect(url_for(_portal_back(g)))
    try:
        new_status = db.submit_proposal(conn, proposal_id, g.user.id)
        conn.commit()
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("proposal_detail", proposal_id=proposal_id))
    flash("Proposal submitted for government review.",
          "success" if new_status == "SUBMITTED"
          else "Revision submitted — it is under review again.")
    return redirect(url_for("proposal_detail", proposal_id=proposal_id))


@app.route("/command-center/proposals")
@login_required(role=GOVERNMENT)
def gov_proposals():
    conn = db.get_db()
    return render_template("gov_proposals.html",
                           review=db.list_proposals_for_mode(conn, "review"),
                           decided=db.list_proposals_for_mode(conn, "decided"))


@app.post("/command-center/proposals/<int:proposal_id>/review")
@login_required(role=GOVERNMENT)
def gov_proposal_review(proposal_id):
    conn = db.get_db()
    proposal = db.get_proposal_row(conn, proposal_id)
    if proposal is None:
        flash("Proposal not found.", "error")
        return redirect(url_for("gov_proposals"))
    try:
        db.begin_proposal_review(conn, proposal_id, g.user.id)
        conn.commit()
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("proposal_detail", proposal_id=proposal_id))


def _gov_verdict(proposal_id, decision, default_comment):
    """Shared verdict handler for revision / approve / reject."""
    conn = db.get_db()
    proposal = db.get_proposal_row(conn, proposal_id)
    if proposal is None:
        flash("Proposal not found.", "error")
        return redirect(url_for("gov_proposals"))
    comment = request.form.get("review_comment", "").strip() or default_comment
    try:
        db.review_proposal(conn, proposal_id, decision, comment, g.user.id)
        conn.commit()
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("proposal_detail", proposal_id=proposal_id))


@app.post("/command-center/proposals/<int:proposal_id>/approve")
@login_required(role=GOVERNMENT)
def gov_proposal_approve(proposal_id):
    return _gov_verdict(proposal_id, "APPROVED",
                        "Proposal approved by the government review.")


@app.post("/command-center/proposals/<int:proposal_id>/reject")
@login_required(role=GOVERNMENT)
def gov_proposal_reject(proposal_id):
    return _gov_verdict(proposal_id, "REJECTED",
                        "Proposal rejected by the government review.")


@app.post("/command-center/proposals/<int:proposal_id>/revision")
@login_required(role=GOVERNMENT)
def gov_proposal_revision(proposal_id):
    return _gov_verdict(proposal_id, "REVISION_REQUESTED",
                        "Revision requested — please improve and resubmit.")


@app.post("/command-center/proposals/<int:proposal_id>/verdict")
@login_required(role=GOVERNMENT)
def gov_proposal_verdict(proposal_id):
    decision = request.form.get("decision", "")
    if decision == "APPROVED":
        return _gov_verdict(proposal_id, "APPROVED",
                            "Proposal approved by the government review.")
    if decision == "REJECTED":
        return _gov_verdict(proposal_id, "REJECTED",
                            "Proposal rejected by the government review.")
    if decision == "REVISION_REQUESTED":
        return _gov_verdict(proposal_id, "REVISION_REQUESTED",
                            "Revision requested — please improve and resubmit.")
    flash("Unknown review decision.", "error")
    return redirect(url_for("proposal_detail", proposal_id=proposal_id))


@app.post("/command-center/proposals/<int:proposal_id>/create-project")
@login_required(role=GOVERNMENT)
def gov_proposal_create_project(proposal_id):
    conn = db.get_db()
    proposal = db.get_proposal(conn, proposal_id)
    if proposal is None:
        flash("Proposal not found.", "error")
        return redirect(url_for("gov_proposals"))
    title = request.form.get("title", "").strip()
    start_date = request.form.get("start_date", "").strip()
    target_end_date = request.form.get("target_end_date", "").strip()
    description = request.form.get("description", "").strip()
    title = title or (proposal.title + " — Project")
    try:
        project_id = db.create_project_from_proposal(
            conn, proposal, title,
            start_date or datetime.utcnow().date().isoformat(),
            target_end_date, g.user.id, description)
        conn.commit()
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("proposal_detail", proposal_id=proposal_id))
    flash("Project created from the approved proposal.", "success")
    return redirect(url_for("project_details", project_id=project_id))


@app.route("/project/<int:project_id>")
@login_required(role=("university", "faculty", "student", "admin", "officer"))
def project_details(project_id):
    conn = db.get_db()
    project = db.get_project(conn, project_id)
    if project is None:
        flash("Project not found.", "error")
        return redirect(url_for("landing"))
    if g.user.role == "citizen":
        flash("You don't have access to that page.", "error")
        return redirect(url_for("landing"))
    uni = _uni_context(conn)
    is_gov = g.user.role in GOVERNMENT
    is_own_uni = uni is not None and project.university_id == uni.id
    is_admin = g.user.role == "university" and is_own_uni
    member = None
    if g.user.role in ("faculty", "student") and is_own_uni:
        member = db.get_team_member(conn, project.team_id, g.user.id)
    is_member = bool(member) and member["status"] == "ACTIVE"
    if not (is_gov or is_admin or is_member):
        flash("This project is not accessible to your account.", "error")
        return redirect(url_for(_portal_back(g)))
    return render_template("project_detail.html", project=project,
                           is_gov=is_gov, is_lead_uni=is_admin,
                           is_member=is_member,
                           readiness=db.project_readiness(conn, project),
                           connections=db.list_project_collaborations(
                               conn, project_id=project.id),
                           collab_requests=db.list_collaborations_for_project(
                               conn, project.id))


# ---------------------------------------------------------------------------
# Phase 6 — team prototype / testing workflow (server-side gates)
# ---------------------------------------------------------------------------

def _project_guard(conn, project_id):
    """Server-side gate for every project-level page (Phase 4 + 6): the
    owning university's admin, active members of the project team, or
    government readers. Citizens and every other institution are denied.
    Never trusts URL or form IDs."""
    project = db.get_project(conn, project_id)
    if project is None:
        return None
    if g.user.role == "citizen":
        return None
    uni = _uni_context(conn)
    is_gov = g.user.role in GOVERNMENT
    is_own_uni = uni is not None and project.university_id == uni.id
    is_admin = g.user.role == "university" and is_own_uni
    member = None
    if g.user.role in ("faculty", "student") and is_own_uni:
        member = db.get_team_member(conn, project.team_id, g.user.id)
    is_member = bool(member) and member["status"] == "ACTIVE"
    if not (is_gov or is_admin or is_member):
        return None
    return {
        "project": project, "uni": uni,
        "is_gov": is_gov, "is_lead_uni": is_admin, "is_member": is_member,
        "member": member,
    }


def _save_evidence_files(files):
    """Persist uploaded evidence files into UPLOAD_DIR and return the
    normalized [{"name": original_name, "path": saved_filename}] list."""
    saved = []
    for f in files or []:
        if not f or not f.filename:
            continue
        safe = secure_filename(f.filename)
        if not safe:
            continue
        name = "{}_{}".format(datetime.utcnow().strftime("%Y%m%d%H%M%S%f"),
                              safe)
        f.save(os.path.join(UPLOAD_DIR, name))
        saved.append({"name": f.filename, "path": name})
    return saved


@app.route("/project/<int:project_id>/prototype")
@login_required()
def project_prototype(project_id):
    conn = db.get_db()
    ctx = _project_guard(conn, project_id)
    if ctx is None:
        flash("This project is not accessible to your account.", "error")
        return redirect(url_for(_portal_back(g)))
    ctx["prototype"] = db.get_prototype_for_project(conn, project_id)
    return render_template("project_prototype.html", **ctx)


@app.post("/project/<int:project_id>/prototype/submit")
@login_required()
def project_prototype_submit(project_id):
    conn = db.get_db()
    ctx = _project_guard(conn, project_id)
    if ctx is None or not ctx["is_member"]:
        flash("Only an active team member can submit a prototype.", "error")
        return redirect(url_for(_portal_back(g)))
    description = request.form.get("description", "").strip()
    version = request.form.get("version", "").strip() or "v1"
    progress_update = request.form.get("progress_update", "").strip()
    if not description:
        flash("A prototype description is required.", "error")
        return redirect(url_for("project_prototype", project_id=project_id))
    evidence = _save_evidence_files(request.files.getlist("evidence"))
    try:
        db.create_prototype(conn, project_id, description, version, g.user.id,
                            progress_update=progress_update, evidence=evidence)
        conn.commit()
        flash("Prototype submitted to the government for review.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("project_prototype", project_id=project_id))


@app.post("/project/<int:project_id>/prototype/update")
@login_required()
def project_prototype_update(project_id):
    conn = db.get_db()
    ctx = _project_guard(conn, project_id)
    if ctx is None or not ctx["is_member"]:
        flash("Only an active team member can edit the prototype.", "error")
        return redirect(url_for(_portal_back(g)))
    proto = db.get_prototype_for_project(conn, project_id)
    if proto is None:
        flash("Prototype not found.", "error")
        return redirect(url_for("project_prototype", project_id=project_id))
    new_files = _save_evidence_files(request.files.getlist("evidence"))
    evidence = list(proto.evidence or []) + new_files
    try:
        db.update_prototype_details(
            conn, proto.id,
            description=request.form.get("description", "").strip(),
            version=request.form.get("version", "").strip(),
            progress_update=request.form.get("progress_update", "").strip(),
            evidence=evidence)
        conn.commit()
        flash("Prototype draft updated.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("project_prototype", project_id=project_id))


@app.post("/project/<int:project_id>/prototype/resubmit")
@login_required()
def project_prototype_resubmit(project_id):
    conn = db.get_db()
    ctx = _project_guard(conn, project_id)
    if ctx is None or not ctx["is_member"]:
        flash("Only an active team member can resubmit the prototype.", "error")
        return redirect(url_for(_portal_back(g)))
    proto = db.get_prototype_for_project(conn, project_id)
    if proto is None:
        flash("Prototype not found.", "error")
        return redirect(url_for("project_prototype", project_id=project_id))
    try:
        db.resubmit_prototype(conn, proto.id, g.user.id)
        conn.commit()
        flash("Prototype resubmitted to the government for review.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("project_prototype", project_id=project_id))


@app.route("/project/<int:project_id>/testing")
@login_required()
def project_testing(project_id):
    conn = db.get_db()
    ctx = _project_guard(conn, project_id)
    if ctx is None:
        flash("This project is not accessible to your account.", "error")
        return redirect(url_for(_portal_back(g)))
    ctx["prototype"] = db.get_prototype_for_project(conn, project_id)
    ctx["testing"] = db.get_testing_report_for_project(conn, project_id)
    ctx["testing_results"] = db.TESTING_RESULT_STATUSES
    return render_template("project_testing.html", **ctx)


@app.post("/project/<int:project_id>/testing/submit")
@login_required()
def project_testing_submit(project_id):
    conn = db.get_db()
    ctx = _project_guard(conn, project_id)
    if ctx is None or not ctx["is_member"]:
        flash("Only an active team member can submit a testing report.",
              "error")
        return redirect(url_for(_portal_back(g)))
    objective = request.form.get("objective", "").strip()
    test_description = request.form.get("test_description", "").strip()
    expected_result = request.form.get("expected_result", "").strip()
    actual_result = request.form.get("actual_result", "").strip()
    if not (objective and test_description and expected_result
            and actual_result):
        flash("Objective, description, expected and actual results are all "
              "required.", "error")
        return redirect(url_for("project_testing", project_id=project_id))
    evidence = _save_evidence_files(request.files.getlist("evidence"))
    try:
        db.create_testing_report(
            conn, project_id, objective, test_description, expected_result,
            actual_result, request.form.get("test_result", "PENDING").strip(),
            g.user.id,
            issues_findings=request.form.get("issues_findings", "").strip(),
            evidence=evidence)
        conn.commit()
        flash("Testing report submitted to the government for review.",
              "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("project_testing", project_id=project_id))


@app.post("/project/<int:project_id>/testing/resubmit")
@login_required()
def project_testing_resubmit(project_id):
    conn = db.get_db()
    ctx = _project_guard(conn, project_id)
    if ctx is None or not ctx["is_member"]:
        flash("Only an active team member can resubmit the testing report.",
              "error")
        return redirect(url_for(_portal_back(g)))
    report = db.get_testing_report_for_project(conn, project_id)
    if report is None:
        flash("Testing report not found.", "error")
        return redirect(url_for("project_testing", project_id=project_id))
    try:
        db.resubmit_testing_report(conn, report.id, g.user.id)
        conn.commit()
        flash("Testing report resubmitted to the government for review.",
              "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("project_testing", project_id=project_id))


@app.post("/project/<int:project_id>/testing/update")
@login_required()
def project_testing_update(project_id):
    conn = db.get_db()
    ctx = _project_guard(conn, project_id)
    if ctx is None or not ctx["is_member"]:
        flash("Only an active team member can edit the testing report.",
              "error")
        return redirect(url_for(_portal_back(g)))
    report = db.get_testing_report_for_project(conn, project_id)
    if report is None:
        flash("Testing report not found.", "error")
        return redirect(url_for("project_testing", project_id=project_id))
    new_files = _save_evidence_files(request.files.getlist("evidence"))
    evidence = list(report.evidence or []) + new_files
    try:
        db.update_testing_report(
            conn, report.id,
            objective=request.form.get("objective", "").strip(),
            test_description=request.form.get("test_description", "").strip(),
            expected_result=request.form.get("expected_result", "").strip(),
            actual_result=request.form.get("actual_result", "").strip(),
            test_result=request.form.get("test_result", "").strip(),
            issues_findings=request.form.get("issues_findings", "").strip(),
            evidence=evidence)
        conn.commit()
        flash("Testing report draft updated.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("project_testing", project_id=project_id))


@app.route("/faculty")
@login_required(role="faculty")
def faculty_dashboard():
    conn = db.get_db()
    prof = db.get_faculty_profile(conn, g.user.id)
    if prof is None:
        flash("No faculty profile is linked to your account.", "error")
        return redirect(url_for("landing"))
    matches = db.list_university_matches_for_institution(conn, prof.university_id)
    relevant = [m for m in matches if m.status in ("INVITED", "ACCEPTED")]
    recommended = [m for m in matches if m.status == "RECOMMENDED"]
    return render_template("faculty_dashboard.html", prof=prof, matches=matches,
                           relevant=relevant, recommended=recommended,
                           my_teams=db.list_teams_for_user(conn, g.user.id),
                           my_proposals=db.list_proposals_for_user(conn, g.user.id),
                           my_projects=db.list_projects_for_user(conn, g.user.id))


@app.route("/student")
@login_required(role="student")
def student_dashboard():
    conn = db.get_db()
    prof = db.get_student_profile(conn, g.user.id)
    if prof is None:
        flash("No student profile is linked to your account.", "error")
        return redirect(url_for("landing"))
    matches = db.list_university_matches_for_institution(conn, prof.university_id)
    accepted = [m for m in matches if m.status == "ACCEPTED"]
    return render_template("student_dashboard.html", prof=prof, accepted=accepted,
                           university_count=db.count_faculty(conn, prof.university_id),
                           my_teams=db.list_teams_for_user(conn, g.user.id),
                           my_projects=db.list_projects_for_user(conn, g.user.id))


@app.route("/api/challenge-map-data")
@login_required(role=GOVERNMENT)
def api_challenge_map_data():
    conn = db.get_db()
    rows = conn.execute(
        "SELECT id, code, title, category, district, priority_level, status, "
        "latitude, longitude, report_count FROM challenges "
        "WHERE latitude IS NOT NULL AND longitude IS NOT NULL ORDER BY id DESC"
    ).fetchall()
    return jsonify([
        {
            "id": r["id"], "code": r["code"], "title": r["title"],
            "category": r["category"], "district": r["district"],
            "priority": r["priority_level"] or "normal",
            "status": r["status"], "reports": r["report_count"],
            "lat": r["latitude"], "lng": r["longitude"],
        }
        for r in rows
    ])


# ---------------------------------------------------------------------------
# map view (geo tracking of every complaint)
# ---------------------------------------------------------------------------

@app.route("/admin/map")
@app.route("/officer/map")
@login_required(role=("admin", "officer"))
def complaints_map():
    return render_template("map.html")


@app.route("/api/map-data")
@login_required(role=("admin", "officer"))
def api_map_data():
    conn = db.get_db()
    rows = conn.execute(
        "SELECT id, code, title, category, district, status, urgency, severity, "
        "latitude, longitude, created_at FROM complaints "
        "WHERE latitude IS NOT NULL AND longitude IS NOT NULL "
        "ORDER BY created_at DESC"
    ).fetchall()
    return jsonify([
        {
            "id": r["id"], "code": r["code"], "title": r["title"],
            "category": r["category"], "district": r["district"],
            "status": r["status"], "urgency": r["urgency"] or "normal",
            "severity": r["severity"],
            "lat": r["latitude"], "lng": r["longitude"],
            "created_at": r["created_at"] or "",
        }
        for r in rows
    ])


# ---------------------------------------------------------------------------
# live problems map (public)
# ---------------------------------------------------------------------------

# Complaint status -> i18n key. Anything not listed falls back to the raw
# status string so the public map always shows an honest label.
_PUBLIC_PROBLEM_STATUS_KEYS = {
    "Submitted": "status_submitted",
    "AI Verified": "status_ai_verified",
    "Pending Officer Review": "status_pending_officer",
    "Accepted by Officer": "status_accepted",
    "Reopened": "status_reopened",
    "Escalated": "status_escalated",
    "Resolved": "status_resolved",
    "Rejected": "status_rejected",
}


@app.route("/api/live-problems")
def api_live_problems():
    """Public, unauthenticated feed of reported problems for the homepage
    map. Only ever exposes data already visible on the public track page
    (code, title, category, district, status, urgency, date, coordinates) --
    never reporter identity, officer/reviewer info, evidence or private notes."""
    conn = db.get_db()
    rows = conn.execute(
        "SELECT code, title, category, district, status, urgency, severity, "
        "latitude, longitude, location_text, created_at FROM complaints "
        "WHERE latitude IS NOT NULL AND longitude IS NOT NULL "
        " ORDER BY created_at DESC, id DESC"
    ).fetchall()
    out = []
    for r in rows:
        status_key = _PUBLIC_PROBLEM_STATUS_KEYS.get(r["status"])
        urgency = r["urgency"] or ""
        if urgency in ("critical", "high", "normal", "low"):
            urgency_label = i18n.t("urgency_" + urgency)
        else:
            urgency_label = i18n.t("lm_urgency_not_specified")
        out.append({
            "code": r["code"],
            "title": r["title"],
            "category": r["category"],
            "category_label": i18n.cat_label(r["category"]),
            "district": r["district"],
            "district_label": i18n.dist_label(r["district"]),
            "status": r["status"],
            "status_label": i18n.t(status_key) if status_key else r["status"],
            "urgency": urgency or "none",
            "urgency_label": urgency_label,
            "severity": r["severity"],
            "location_text": r["location_text"],
            "lat": r["latitude"],
            "lng": r["longitude"],
            "created_at": r["created_at"] or "",
            "track_url": url_for("track_complaint", code=r["code"]),
        })
    return jsonify(out)


# ---------------------------------------------------------------------------
# uploaded files
# ---------------------------------------------------------------------------

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# ---------------------------------------------------------------------------
# EXIF GPS extraction (PIL)
# ---------------------------------------------------------------------------

def _to_deg(value, ref):
    try:
        d, m, s = value
        dec = float(d) + float(m) / 60 + float(s) / 3600
        if ref in ("S", "W"):
            dec = -dec
        return round(dec, 6)
    except Exception:
        return None


def _extract_gps(exif, tags):
    try:
        if not exif:
            return None, None
        if 34853 not in exif:
            return None, None
        gps = exif[34853]
        lat = _to_deg(gps.get(2), gps.get(1, "N"))
        lon = _to_deg(gps.get(4), gps.get(3, "E"))
        return lat, lon
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Phase 5 — industry / startup / MSME collaboration
# ---------------------------------------------------------------------------

def _require_industry(conn):
    """Industry org profile for the logged-in user, or None."""
    return db.get_organization_for_user(conn, g.user)


def _industry_org_link(conn):
    org = _require_industry(conn)
    if org is None:
        flash("No industry profile is linked to your account.", "error")
        return None
    return org


@app.route("/industry")
@login_required(role="industry")
def industry_dashboard():
    conn = db.get_db()
    org = _industry_org_link(conn)
    if org is None:
        return redirect(url_for("landing"))
    projects = db.list_discoverable_projects(conn)
    unread = db.unread_notification_count(conn, g.user.id)
    return render_template("industry_dashboard.html",
                           org=org, projects=projects,
                           kpis=db.industry_dashboard_kpis(conn),
                           unread=unread)


@app.route("/industry/profile", methods=["GET", "POST"])
@login_required(role="industry")
def industry_profile():
    conn = db.get_db()
    org = _industry_org_link(conn)
    if org is None:
        return redirect(url_for("landing"))
    if request.method == "POST":
        db.update_industry_organization(conn, org.id,
            name=request.form.get("name", "").strip() or org.name,
            short_name=request.form.get("short_name", "").strip() or None,
            legal_entity_name=request.form.get("legal_entity_name", "").strip() or None,
            org_type=request.form.get("org_type") or org.org_type,
            sector=request.form.get("sector", "").strip() or None,
            core_expertise=request.form.get("core_expertise", "").strip() or None,
            technologies=request.form.get("technologies", "").strip() or None,
            capabilities=request.form.get("capabilities", "").strip() or None,
            email=request.form.get("email", "").strip() or None,
            phone=request.form.get("phone", "").strip() or None,
            address=request.form.get("address", "").strip() or None,
            district=request.form.get("district") or org.district,
            city=request.form.get("city", "").strip() or None,
            website=request.form.get("website", "").strip() or None,
            description=request.form.get("description", "").strip() or None)
        flash("Industry profile updated.", "success")
        return redirect(url_for("industry_profile"))
    return render_template("industry_profile.html", org=org,
                           org_types=db.INDUSTRY_ORG_TYPES,
                           districts=db.DISTRICTS)


@app.route("/industry/projects")
@login_required(role="industry")
def industry_projects():
    conn = db.get_db()
    org = _industry_org_link(conn)
    if org is None:
        return redirect(url_for("landing"))
    projects = db.list_discoverable_projects(conn)
    for p in projects:
        fit = industry_project_fit(p, org)
        p.fit_score = fit["score"]
        p.fit_level = fit["level"]
        p.fit_signals = fit["signals"]
    projects.sort(key=lambda p: -p.fit_score)
    return render_template("industry_projects.html", org=org, projects=projects)


@app.route("/industry/projects/<int:project_id>")
@login_required(role="industry")
def industry_project_detail(project_id):
    conn = db.get_db()
    org = _industry_org_link(conn)
    if org is None:
        return redirect(url_for("landing"))
    if not org.is_verified:
        flash("Your organisation must be government-verified to access "
              "project details and submit collaboration requests.", "error")
        return redirect(url_for("industry_dashboard"))
    project = db.get_project(conn, project_id)
    if project is None:
        flash("Project not found.", "error")
        return redirect(url_for("industry_projects"))
    if not db.project_discoverable(project):
        flash("This project is not open for collaboration.", "error")
        return redirect(url_for("industry_projects"))
    existing = [c for c in db.list_collaborations_for_org(conn, org.id)
                if c.project_id == project_id]
    fit = industry_project_fit(project, org)
    faculty_lead = db.project_faculty_lead(conn, project.team_id)
    return render_template("industry_project_detail.html",
                           org=org, project=project, existing=existing,
                           fit=fit, faculty_lead=faculty_lead,
                           is_partner=any(c.status == "ACCEPTED"
                                          for c in existing),
                           readiness=db.project_readiness(conn, project))


@app.post("/industry/projects/<int:project_id>/interest")
@login_required(role="industry")
def industry_interest(project_id):
    conn = db.get_db()
    org = _industry_org_link(conn)
    if org is None:
        return redirect(url_for("landing"))
    if not org.is_verified:
        flash("Only verified organisations can submit collaboration requests.",
              "error")
        return redirect(url_for("industry_projects"))
    project = db.get_project(conn, project_id)
    if project is None or not db.project_discoverable(project):
        flash("Project not found or not open for collaboration.", "error")
        return redirect(url_for("industry_projects"))
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    if not (title and description):
        flash("A title and description are required to express interest.",
              "error")
        return redirect(url_for("industry_project_detail",
                                project_id=project_id))
    try:
        db.express_interest(conn, project, org, g.user.id,
                            request.form.get("collaboration_type",
                                              "TECHNICAL_SUPPORT"),
                            title, description,
                            expected_support=request.form.get(
                                "expected_support", "").strip(),
                            proposed_amount=request.form.get(
                                "proposed_amount", "").strip() or None,
                            funding_type=request.form.get("funding_type"),
                            funding_description=request.form.get(
                                "funding_description", "").strip())
        conn.commit()
        flash("Interest recorded. Submit the request when you are ready.",
              "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("industry_project_detail",
                            project_id=project_id))


@app.post("/industry/collaborations/<int:request_id>/submit")
@login_required(role="industry")
def industry_collaboration_submit(request_id):
    conn = db.get_db()
    org = _industry_org_link(conn)
    if org is None:
        return redirect(url_for("landing"))
    row = db.get_collaboration_row(conn, request_id)
    if row is None or row["organization_id"] != org.id:
        flash("Collaboration request not found.", "error")
        return redirect(url_for("industry_collaborations"))
    try:
        db.submit_collaboration(conn, request_id, g.user.id)
        conn.commit()
        flash("Collaboration request submitted to the government.",
              "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("industry_collaboration_detail",
                            request_id=request_id))


@app.route("/industry/collaborations")
@login_required(role="industry")
def industry_collaborations():
    conn = db.get_db()
    org = _industry_org_link(conn)
    if org is None:
        return redirect(url_for("landing"))
    requests = db.list_collaborations_for_org(conn, org.id)
    return render_template("industry_collaborations.html", org=org,
                           requests=requests)


@app.route("/industry/collaborations/<int:request_id>")
@login_required(role="industry")
def industry_collaboration_detail(request_id):
    conn = db.get_db()
    org = _industry_org_link(conn)
    if org is None:
        return redirect(url_for("landing"))
    collab = db.get_collaboration(conn, request_id)
    if collab is None or collab.organization_id != org.id:
        flash("Collaboration request not found.", "error")
        return redirect(url_for("industry_collaborations"))
    return render_template("industry_collaboration_detail.html",
                           org=org, collab=collab)


# ---------------------------------------------------------------------------
# Government — industry verification & collaboration review
# ---------------------------------------------------------------------------

@app.route("/command-center/industry")
@login_required(role=GOVERNMENT)
def gov_industry():
    conn = db.get_db()
    return render_template("gov_industry.html",
                           pending=db.list_industry_organizations(conn, "PENDING"),
                           organizations=db.list_industry_organizations(conn),
                           kpis=db.industry_dashboard_kpis(conn))


@app.post("/command-center/industry/<int:org_id>/verify")
@login_required(role=GOVERNMENT)
def gov_industry_verify(org_id):
    conn = db.get_db()
    note = request.form.get("note", "").strip()
    try:
        db.verify_industry_organization(conn, org_id, "VERIFIED", note,
                                        g.user.id)
        conn.commit()
        flash("Organisation verified — they can now collaborate on projects.",
              "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("gov_industry"))


@app.post("/command-center/industry/<int:org_id>/reject")
@login_required(role=GOVERNMENT)
def gov_industry_reject(org_id):
    conn = db.get_db()
    note = request.form.get("note", "").strip()
    try:
        db.verify_industry_organization(conn, org_id, "REJECTED", note,
                                        g.user.id)
        conn.commit()
        flash("Organisation profile rejected.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("gov_industry"))


@app.route("/command-center/collaborations")
@login_required(role=GOVERNMENT)
def gov_collaborations():
    conn = db.get_db()
    return render_template("gov_collaborations.html",
                           review=db.list_collaborations_for_mode(conn, "review"),
                           decided=db.list_collaborations_for_mode(conn,
                                                                  "decided"))


@app.post("/command-center/collaborations/<int:request_id>/review")
@login_required(role=GOVERNMENT)
def gov_collaboration_review(request_id):
    conn = db.get_db()
    try:
        db.begin_collaboration_review(conn, request_id, g.user.id)
        conn.commit()
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("gov_collaboration_detail",
                            request_id=request_id))


@app.post("/command-center/collaborations/<int:request_id>/verdict")
@login_required(role=GOVERNMENT)
def gov_collaboration_verdict(request_id):
    conn = db.get_db()
    decision = request.form.get("decision", "")
    comment = request.form.get("review_comment", "").strip()
    try:
        db.review_collaboration(conn, request_id, decision, comment,
                                g.user.id)
        conn.commit()
        flash({
            "ACCEPTED": "Collaboration request accepted.",
            "REVISION_REQUESTED": "Collaboration revision requested.",
            "REJECTED": "Collaboration request rejected.",
        }.get(decision, "Decision recorded."), "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("gov_collaboration_detail",
                            request_id=request_id))


@app.route("/command-center/collaborations/<int:request_id>")
@login_required(role=GOVERNMENT)
def gov_collaboration_detail(request_id):
    conn = db.get_db()
    collab = db.get_collaboration(conn, request_id)
    if collab is None:
        flash("Collaboration request not found.", "error")
        return redirect(url_for("gov_collaborations"))
    funding = db.get_project_collaboration(conn, request_id, by_request=True)
    return render_template("gov_collaboration_detail.html", collab=collab,
                           funding=funding,
                           funding_types=db.FUNDING_TYPES,
                           funding_statuses=db.FUNDING_STATUSES)


@app.post("/command-center/collaborations/<int:request_id>/funding")
@login_required(role=GOVERNMENT)
def gov_collaboration_funding(request_id):
    conn = db.get_db()
    funding_status = request.form.get("funding_status", "").strip()
    comment = request.form.get("funding_comment", "").strip()
    try:
        db.update_collaboration_funding(conn, request_id, funding_status,
                                        comment, g.user.id)
        conn.commit()
        flash(f"Funding status updated to {funding_status.lower()}.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("gov_collaboration_detail",
                            request_id=request_id))


# ---------------------------------------------------------------------------
# Phase 6 — government review centre (prototype / testing / pilot)
# ---------------------------------------------------------------------------

def _prototype_or_404(conn, prototype_id):
    proto = db.get_prototype(conn, prototype_id)
    if proto is None:
        flash("Prototype not found.", "error")
        return None
    return proto


@app.route("/command-center/prototypes")
@login_required(role=GOVERNMENT)
def gov_prototypes():
    conn = db.get_db()
    return render_template("gov_prototypes.html",
                           review=db.list_prototypes(conn, "review"),
                           decided=db.list_prototypes(conn, "decided"))


@app.route("/command-center/prototypes/<int:prototype_id>")
@login_required(role=GOVERNMENT)
def gov_prototype_detail(prototype_id):
    conn = db.get_db()
    proto = _prototype_or_404(conn, prototype_id)
    if proto is None:
        return redirect(url_for("gov_prototypes"))
    return render_template("gov_prototype_detail.html", prototype=proto)


@app.post("/command-center/prototypes/<int:prototype_id>/review")
@login_required(role=GOVERNMENT)
def gov_prototype_review(prototype_id):
    conn = db.get_db()
    proto = _prototype_or_404(conn, prototype_id)
    if proto is None:
        return redirect(url_for("gov_prototypes"))
    try:
        db.begin_prototype_review(conn, prototype_id, g.user.id)
        conn.commit()
        flash("Prototype review started.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("gov_prototype_detail", prototype_id=prototype_id))


@app.post("/command-center/prototypes/<int:prototype_id>/verdict")
@login_required(role=GOVERNMENT)
def gov_prototype_verdict(prototype_id):
    conn = db.get_db()
    proto = _prototype_or_404(conn, prototype_id)
    if proto is None:
        return redirect(url_for("gov_prototypes"))
    decision = request.form.get("decision", "").strip()
    comment = request.form.get("review_comment", "").strip()
    try:
        db.review_prototype(conn, prototype_id, decision, comment, g.user.id)
        conn.commit()
        flash("Prototype updated.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("gov_prototype_detail", prototype_id=prototype_id))


def _testing_or_404(conn, report_id):
    report = db.get_testing_report(conn, report_id)
    if report is None:
        flash("Testing report not found.", "error")
        return None
    return report


@app.route("/command-center/testing")
@login_required(role=GOVERNMENT)
def gov_testing():
    conn = db.get_db()
    return render_template("gov_testing.html",
                           review=db.list_testing_reports(conn, "review"),
                           decided=db.list_testing_reports(conn, "decided"))


@app.route("/command-center/testing/<int:report_id>")
@login_required(role=GOVERNMENT)
def gov_testing_detail(report_id):
    conn = db.get_db()
    report = _testing_or_404(conn, report_id)
    if report is None:
        return redirect(url_for("gov_testing"))
    return render_template("gov_testing_detail.html", report=report)


@app.post("/command-center/testing/<int:report_id>/review")
@login_required(role=GOVERNMENT)
def gov_testing_review(report_id):
    conn = db.get_db()
    report = _testing_or_404(conn, report_id)
    if report is None:
        return redirect(url_for("gov_testing"))
    try:
        db.begin_testing_review(conn, report_id, g.user.id)
        conn.commit()
        flash("Testing report review started.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("gov_testing_detail", report_id=report_id))


@app.post("/command-center/testing/<int:report_id>/verdict")
@login_required(role=GOVERNMENT)
def gov_testing_verdict(report_id):
    conn = db.get_db()
    report = _testing_or_404(conn, report_id)
    if report is None:
        return redirect(url_for("gov_testing"))
    decision = request.form.get("decision", "").strip()
    comment = request.form.get("review_comment", "").strip()
    try:
        db.review_testing_report(conn, report_id, decision, comment, g.user.id)
        conn.commit()
        flash("Testing report updated.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("gov_testing_detail", report_id=report_id))


@app.route("/command-center/pilots")
@login_required(role=GOVERNMENT)
def gov_pilots():
    conn = db.get_db()
    all_pilots = db.list_pilots(conn)
    in_progress = [p for p in all_pilots if p.status != "DEPLOYED"]
    deployed = [p for p in all_pilots if p.status == "DEPLOYED"]
    return render_template(
        "gov_pilots.html", in_progress=in_progress, deployed=deployed,
        eligible_count=len(db.list_pilot_eligible_projects(conn)),
        pilots_eval=db.count_pilots_needing_evaluation(conn),
        pilots_overdue=db.count_pilots_overdue(conn))


@app.route("/command-center/pilots/new", methods=["GET", "POST"])
@login_required(role=GOVERNMENT)
def gov_pilot_new():
    conn = db.get_db()
    if request.method == "POST":
        project_id = request.form.get("project_id", "").strip()
        district = request.form.get("district", "").strip()
        if not (project_id.isdigit() and district in db.DISTRICTS):
            flash("Choose a project and a district to open the pilot.",
                  "error")
            return redirect(url_for("gov_pilot_new"))
        try:
            db.create_pilot(
                conn, int(project_id), district, g.user.id,
                location=request.form.get("location", "").strip(),
                target_community=request.form.get("target_community",
                                                  "").strip(),
                objectives=request.form.get("objectives", "").strip(),
                start_date=request.form.get("start_date", "").strip() or None,
                target_end_date=request.form.get("target_end_date",
                                                 "").strip() or None,
                responsible_org=request.form.get("responsible_org",
                                                 "").strip())
            conn.commit()
            flash("Pilot opened successfully.", "success")
            return redirect(url_for("gov_pilots"))
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("gov_pilot_new"))
    eligible = db.list_pilot_eligible_projects(conn)
    return render_template("gov_pilot_new.html", eligible=eligible,
                           districts=db.DISTRICTS)


@app.route("/command-center/pilots/<int:pilot_id>")
@login_required(role=GOVERNMENT)
def gov_pilot_detail(pilot_id):
    conn = db.get_db()
    pilot = db.get_pilot(conn, pilot_id)
    if pilot is None:
        flash("Pilot not found.", "error")
        return redirect(url_for("gov_pilots"))
    return render_template("gov_pilot_detail.html", pilot=pilot,
                           all_statuses=db.PILOT_STATUSES,
                           deferred_statuses=("ACTIVE", "COMPLETED",
                                              "DEPLOYED"))


@app.post("/command-center/pilots/<int:pilot_id>/status")
@login_required(role=GOVERNMENT)
def gov_pilot_status(pilot_id):
    conn = db.get_db()
    status = request.form.get("status", "").strip()
    comment = request.form.get("review_comment", "").strip()
    try:
        db.set_pilot_status(conn, pilot_id, status, g.user.id, comment=comment)
        conn.commit()
        flash("Pilot status updated.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("gov_pilot_detail", pilot_id=pilot_id))


@app.post("/command-center/pilots/<int:pilot_id>/progress")
@login_required(role=GOVERNMENT)
def gov_pilot_progress(pilot_id):
    conn = db.get_db()
    text = request.form.get("progress_text", "").strip()
    if not text:
        flash("A progress update is required.", "error")
        return redirect(url_for("gov_pilot_detail", pilot_id=pilot_id))
    try:
        db.add_pilot_progress(conn, pilot_id, text, g.user.id)
        conn.commit()
        flash("Progress update recorded.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("gov_pilot_detail", pilot_id=pilot_id))


# ---------------------------------------------------------------------------
# Phase 7 — impact assessment and scaling
# ---------------------------------------------------------------------------

def _impact_or_404(conn, impact_id):
    assessment = db.get_impact_assessment(conn, impact_id)
    if assessment is None:
        flash("Impact assessment not found.", "error")
        return None
    return assessment


def _scaling_or_404(conn, scaling_id):
    proposal = db.get_scaling_proposal(conn, scaling_id)
    if proposal is None:
        flash("Scaling proposal not found.", "error")
        return None
    return proposal


def _impact_metrics_from_form():
    """Optional reported figures. Empty inputs are dropped; numeric values
    are cast so they render sensibly; anything else is kept verbatim."""
    raw = {
        "beneficiaries": request.form.get("metric_beneficiaries", "").strip(),
        "problems_resolved": request.form.get("metric_problems_resolved", "").strip(),
        "time_saved": request.form.get("metric_time_saved", "").strip(),
        "cost_saved": request.form.get("metric_cost_saved", "").strip(),
        "satisfaction": request.form.get("metric_satisfaction", "").strip(),
    }
    out = {}
    for k, v in raw.items():
        if not v:
            continue
        try:
            out[k] = int(v)
        except ValueError:
            try:
                out[k] = float(v)
            except ValueError:
                out[k] = v
    return out


@app.route("/project/<int:project_id>/impact")
@login_required()
def project_impact(project_id):
    conn = db.get_db()
    ctx = _project_guard(conn, project_id)
    if ctx is None:
        flash("This project is not accessible to your account.", "error")
        return redirect(url_for(_portal_back(g)))
    ctx["impact"] = db.get_impact_assessment_for_project(conn, project_id)
    ctx["pilot"] = db.get_pilot_for_project(conn, project_id)
    return render_template("project_impact.html", **ctx)


@app.post("/project/<int:project_id>/impact/submit")
@login_required()
def project_impact_submit(project_id):
    conn = db.get_db()
    ctx = _project_guard(conn, project_id)
    if ctx is None or not ctx["is_member"]:
        flash("Only an active team member can submit an impact assessment.",
              "error")
        return redirect(url_for(_portal_back(g)))
    existing = db.get_impact_assessment_for_project(conn, project_id)
    if existing is not None:
        flash("An impact assessment already exists for this project.", "error")
        return redirect(url_for("project_impact", project_id=project_id))
    try:
        impact_id = db.create_impact_assessment(
            conn, project_id, g.user.id,
            period_start=request.form.get("period_start", "").strip(),
            period_end=request.form.get("period_end", "").strip(),
            target_population=request.form.get("target_population", "").strip(),
            beneficiaries_reached=request.form.get("beneficiaries_reached",
                                                    "").strip(),
            problems_addressed=request.form.get("problems_addressed", "").strip(),
            key_outcomes=request.form.get("key_outcomes", "").strip(),
            before_observations=request.form.get("before_observations", "").strip(),
            after_observations=request.form.get("after_observations", "").strip(),
            success_indicators=request.form.get("success_indicators", "").strip(),
            challenges_faced=request.form.get("challenges_faced", "").strip(),
            reported_metrics=_impact_metrics_from_form(),
            evidence=_save_evidence_files(request.files.getlist("evidence")))
        conn.commit()
        try:
            db.submit_impact_assessment(conn, impact_id, g.user.id)
            conn.commit()
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("project_impact", project_id=project_id))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("project_impact", project_id=project_id))


@app.post("/project/<int:project_id>/impact/update")
@login_required()
def project_impact_update(project_id):
    conn = db.get_db()
    ctx = _project_guard(conn, project_id)
    if ctx is None or not ctx["is_member"]:
        flash("Only an active team member can edit the assessment.", "error")
        return redirect(url_for(_portal_back(g)))
    existing = db.get_impact_assessment_for_project(conn, project_id)
    if existing is None:
        flash("Impact assessment not found.", "error")
        return redirect(url_for("project_impact", project_id=project_id))
    new_files = _save_evidence_files(request.files.getlist("evidence"))
    evidence = list(existing.evidence or []) + new_files
    try:
        db.update_impact_assessment_details(
            conn, existing.id, g.user.id,
            period_start=request.form.get("period_start", "").strip(),
            period_end=request.form.get("period_end", "").strip(),
            target_population=request.form.get("target_population", "").strip(),
            beneficiaries_reached=request.form.get("beneficiaries_reached",
                                                    "").strip(),
            problems_addressed=request.form.get("problems_addressed", "").strip(),
            key_outcomes=request.form.get("key_outcomes", "").strip(),
            before_observations=request.form.get("before_observations", "").strip(),
            after_observations=request.form.get("after_observations", "").strip(),
            success_indicators=request.form.get("success_indicators", "").strip(),
            challenges_faced=request.form.get("challenges_faced", "").strip(),
            reported_metrics=_impact_metrics_from_form(),
            evidence=evidence)
        conn.commit()
        flash("Impact assessment draft updated.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("project_impact", project_id=project_id))


@app.post("/project/<int:project_id>/impact/resubmit")
@login_required()
def project_impact_resubmit(project_id):
    conn = db.get_db()
    ctx = _project_guard(conn, project_id)
    if ctx is None or not ctx["is_member"]:
        flash("Only an active team member can resubmit the assessment.", "error")
        return redirect(url_for(_portal_back(g)))
    existing = db.get_impact_assessment_for_project(conn, project_id)
    if existing is None:
        flash("Impact assessment not found.", "error")
        return redirect(url_for("project_impact", project_id=project_id))
    try:
        db.resubmit_impact_assessment(conn, existing.id, g.user.id)
        conn.commit()
        flash("Assessment resubmitted to the government for review.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("project_impact", project_id=project_id))


@app.route("/command-center/impact")
@login_required(role=GOVERNMENT)
def gov_impact():
    conn = db.get_db()
    return render_template("gov_impact.html",
                           review=db.list_impact_assessments(conn, "review"),
                           decided=db.list_impact_assessments(conn, "decided"))


@app.route("/command-center/impact/<int:impact_id>")
@login_required(role=GOVERNMENT)
def gov_impact_detail(impact_id):
    conn = db.get_db()
    assessment = _impact_or_404(conn, impact_id)
    if assessment is None:
        return redirect(url_for("gov_impact"))
    return render_template("gov_impact_detail.html", assessment=assessment)


@app.post("/command-center/impact/<int:impact_id>/review")
@login_required(role=GOVERNMENT)
def gov_impact_review(impact_id):
    conn = db.get_db()
    assessment = _impact_or_404(conn, impact_id)
    if assessment is None:
        return redirect(url_for("gov_impact"))
    try:
        db.begin_impact_review(conn, impact_id, g.user.id)
        conn.commit()
        flash("Impact assessment review started.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("gov_impact_detail", impact_id=impact_id))


@app.post("/command-center/impact/<int:impact_id>/verdict")
@login_required(role=GOVERNMENT)
def gov_impact_verdict(impact_id):
    conn = db.get_db()
    assessment = _impact_or_404(conn, impact_id)
    if assessment is None:
        return redirect(url_for("gov_impact"))
    decision = request.form.get("decision", "").strip()
    comment = request.form.get("review_comment", "").strip()
    try:
        db.review_impact_assessment(conn, impact_id, decision, g.user.id,
                                    comment=comment)
        conn.commit()
        flash("Impact assessment updated.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("gov_impact_detail", impact_id=impact_id))


@app.route("/command-center/scaling")
@login_required(role=GOVERNMENT)
def gov_scaling():
    conn = db.get_db()
    return render_template("gov_scaling.html",
                           review=db.list_scaling_proposals(conn, "review"),
                           decided=db.list_scaling_proposals(conn, "decided"))


@app.route("/command-center/scaling/new", methods=["GET", "POST"])
@login_required(role=GOVERNMENT)
def gov_scaling_new():
    conn = db.get_db()
    if request.method == "POST":
        project_id = request.form.get("project_id", "").strip()
        if not project_id.isdigit():
            flash("Choose a project to open the scaling proposal.", "error")
            return redirect(url_for("gov_scaling_new"))
        impact = db.get_impact_assessment_for_project(conn, int(project_id))
        proposed = request.form.getlist("proposed_districts")
        try:
            if impact is None:
                raise ValueError("Approved impact is required for scaling.")
            db.create_scaling_proposal(
                conn, int(project_id), impact.id, g.user.id,
                current_location=request.form.get("current_location", "").strip(),
                proposed_districts=proposed,
                target_communities=request.form.get("target_communities",
                                                     "").strip(),
                scaling_objective=request.form.get("scaling_objective", "").strip(),
                expected_beneficiaries=request.form.get("expected_beneficiaries",
                                                        "").strip(),
                required_resources=request.form.get("required_resources", "").strip(),
                estimated_duration=request.form.get("estimated_duration", "").strip(),
                notes=request.form.get("notes", "").strip(),
                evidence=_save_evidence_files(request.files.getlist("evidence")))
            conn.commit()
            flash("Scaling proposal opened successfully.", "success")
            return redirect(url_for("gov_scaling"))
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("gov_scaling_new"))
    return render_template("gov_scaling_new.html",
                           eligible=db.list_scaling_eligible_projects(conn),
                           districts=db.DISTRICTS)


@app.route("/command-center/scaling/<int:scaling_id>")
@login_required(role=GOVERNMENT)
def gov_scaling_detail(scaling_id):
    conn = db.get_db()
    proposal = _scaling_or_404(conn, scaling_id)
    if proposal is None:
        return redirect(url_for("gov_scaling"))
    return render_template("gov_scaling_detail.html", proposal=proposal,
                           districts=db.DISTRICTS)


@app.post("/command-center/scaling/<int:scaling_id>/review")
@login_required(role=GOVERNMENT)
def gov_scaling_review(scaling_id):
    conn = db.get_db()
    proposal = _scaling_or_404(conn, scaling_id)
    if proposal is None:
        return redirect(url_for("gov_scaling"))
    try:
        db.begin_scaling_review(conn, scaling_id, g.user.id)
        conn.commit()
        flash("Scaling proposal review started.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("gov_scaling_detail", scaling_id=scaling_id))


@app.post("/command-center/scaling/<int:scaling_id>/verdict")
@login_required(role=GOVERNMENT)
def gov_scaling_verdict(scaling_id):
    conn = db.get_db()
    proposal = _scaling_or_404(conn, scaling_id)
    if proposal is None:
        return redirect(url_for("gov_scaling"))
    decision = request.form.get("decision", "").strip()
    comment = request.form.get("review_comment", "").strip()
    try:
        db.review_scaling_proposal(conn, scaling_id, decision, g.user.id,
                                   comment=comment)
        conn.commit()
        flash("Scaling proposal updated.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("gov_scaling_detail", scaling_id=scaling_id))


@app.post("/command-center/scaling/<int:scaling_id>/update")
@login_required(role=GOVERNMENT)
def gov_scaling_update(scaling_id):
    conn = db.get_db()
    proposal = _scaling_or_404(conn, scaling_id)
    if proposal is None:
        return redirect(url_for("gov_scaling"))
    new_files = _save_evidence_files(request.files.getlist("evidence"))
    evidence = list(proposal.evidence or []) + new_files
    try:
        db.update_scaling_details(
            conn, scaling_id, g.user.id,
            current_location=request.form.get("current_location", "").strip(),
            proposed_districts=request.form.getlist("proposed_districts"),
            target_communities=request.form.get("target_communities", "").strip(),
            scaling_objective=request.form.get("scaling_objective", "").strip(),
            expected_beneficiaries=request.form.get("expected_beneficiaries",
                                                    "").strip(),
            required_resources=request.form.get("required_resources", "").strip(),
            estimated_duration=request.form.get("estimated_duration", "").strip(),
            notes=request.form.get("notes", "").strip(),
            evidence=evidence)
        conn.commit()
        flash("Scaling proposal updated.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("gov_scaling_detail", scaling_id=scaling_id))


@app.post("/command-center/scaling/<int:scaling_id>/resubmit")
@login_required(role=GOVERNMENT)
def gov_scaling_resubmit(scaling_id):
    conn = db.get_db()
    proposal = _scaling_or_404(conn, scaling_id)
    if proposal is None:
        return redirect(url_for("gov_scaling"))
    try:
        db.resubmit_scaling_proposal(conn, scaling_id, g.user.id)
        conn.commit()
        flash("Scaling proposal resubmitted.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("gov_scaling_detail", scaling_id=scaling_id))


# ---------------------------------------------------------------------------
# Notifications feed
# ---------------------------------------------------------------------------

@app.route("/notifications")
@login_required()
def notifications_page():
    conn = db.get_db()
    notes = db.list_notifications(conn, g.user.id)
    db.mark_all_notifications_read(conn, g.user.id)
    conn.commit()
    return render_template("notifications.html", notifications=notes)


@app.post("/notifications/read-all")
@login_required()
def notifications_read_all():
    conn = db.get_db()
    db.mark_all_notifications_read(conn, g.user.id)
    conn.commit()
    return redirect(url_for("notifications_page"))


DEMO_USERS = [
    ("Jharkhand Admin", "admin@jsamadhan.gov", "0000000000", "admin123", "admin"),
    ("Ramesh Kumar", "officer1@jsamadhan.gov", "1000000001", "officer123", "officer"),
    ("Sita Devi", "officer2@jsamadhan.gov", "1000000002", "officer123", "officer"),
    ("Amit Kumar", "citizen@example.com", "2000000001", "citizen123", "citizen"),
]

# Demo institution ecosystem (Phase 3). Small, realistic set whose verifies
# the matcher discriminates: BIT (roads/civil) and NIT JSR (cyber) and BAU
# (agriculture) should rank differently per challenge, VBU (humanities) low,
# and the PENDING institute never appears in matches.
DEMO_INSTITUTIONS = [
    dict(key="uni1", name="Birsa Institute of Technology", short_name="BIT Mesra",
         email="university1@jsamadhan.demo", phone="3000000011",
         address="Mesra, Ranchi", district="Ranchi", website="https://bitmesra.example",
         description="Leading engineering institute with a strong civil and rural infrastructure research group.",
         institution_type="Engineering College", verification_status="VERIFIED",
         expertise=[
             dict(department="Civil Engineering", expertise="Transportation Engineering",
                  research_area="Rural Road Infrastructure",
                  keywords="roads, potholes, pavement, transport, civil infrastructure, drainage, asphalt",
                  lab_capabilities="Pavement Testing Laboratory; Soil Mechanics Laboratory",
                  description="Designing and testing durable rural and urban road surfaces, pavement "
                              "rehabilitation and traffic safety."),
             dict(department="Civil Engineering", expertise="Public Works Management",
                  research_area="Municipal Infrastructure",
                  keywords="waterlogging, street, footpath, bridge, repair, public works",
                  lab_capabilities="", description="Planning and maintenance of municipal civic assets."),
         ]),
    dict(key="uni2", name="National Institute of Technology Jamshedpur", short_name="NIT JSR",
         email="university2@jsamadhan.demo", phone="3000000012",
         address="Adityapur, Jamshedpur", district="East Singhbhum",
         website="https://nitjsr.example",
         description="Technical institute with a dedicated cyber-security research group working on digital public safety.",
         institution_type="Engineering College", verification_status="VERIFIED",
         expertise=[
             dict(department="Computer Science", expertise="Cybersecurity",
                  research_area="Digital Forensics and Network Security",
                  keywords="cybercrime, digital security, network, forensics, encryption, malware, fraud, privacy",
                  lab_capabilities="Cyber Security Laboratory; Digital Forensics Laboratory",
                  description="Securing digital infrastructure, analysing cybercrime patterns and "
                              "building safe civic platforms."),
         ]),
    dict(key="uni3", name="Birsa Agricultural University", short_name="BAU",
         email="university3@jsamadhan.demo", phone="3000000013",
         address="Kanke, Ranchi", district="Ranchi", website="https://bau.example",
         description="Agricultural university leading irrigation, drainage and crop-science research for the region.",
         institution_type="University", verification_status="VERIFIED",
         expertise=[
             dict(department="Agricultural Engineering", expertise="Irrigation and Drainage",
                  research_area="Crop Water Management",
                  keywords="irrigation, crop, agriculture, drainage, soil, water conservation, farming",
                  lab_capabilities="Soil and Water Conservation Farm",
                  description="Efficient irrigation scheduling, drainage design and sustainable crop production."),
         ]),
    dict(key="uni4", name="Vinoba Bhave University", short_name="VBU",
         email="university4@jsamadhan.demo", phone="3000000014",
         address="Hazaribagh", district="Hazaribagh", website="https://vbu.example",
         description="A liberal-arts university focused on the humanities and social sciences.",
         institution_type="University", verification_status="VERIFIED",
         expertise=[
             dict(department="Humanities", expertise="History and Literature",
                  research_area="Indigenous Cultural Heritage",
                  keywords="history, literature, culture, languages, heritage, society",
                  lab_capabilities="", description="Documentation of tribal heritage, languages and "
                                                   "oral traditions of Jharkhand."),
         ]),
    dict(key="uni5", name="Jharkhand Water & Sanitation Institute", short_name="JWSI",
         email="university5@jsamadhan.demo", phone="3000000015",
         address="Bokaro", district="Bokaro", website="https://jwsi.example",
         description="Specialist institute for rural water supply and sanitation planning.",
         institution_type="Research Institution", verification_status="PENDING",
         expertise=[
             dict(department="Water & Sanitation", expertise="Rural Water Supply",
                  research_area="Safe Drinking Water",
                  keywords="water, drinking water, sanitation, piping, leakage, supply",
                  lab_capabilities="Water Quality Laboratory",
                  description="Water quality monitoring and rural supply networks."),
         ]),
]

DEMO_INSTITUTION_ADMINS = {
    "uni1": ("Birsa Institute of Technology Admin", "university1@jsamadhan.demo", "3000000011", "university123"),
    "uni2": ("NIT Jamshedpur Admin", "university2@jsamadhan.demo", "3000000012", "university123"),
    "uni3": ("Birsa Agricultural University Admin", "university3@jsamadhan.demo", "3000000013", "university123"),
    "uni4": ("Vinoba Bhave University Admin", "university4@jsamadhan.demo", "3000000014", "university123"),
    "uni5": ("Jharkhand Water & Sanitation Institute Admin", "university5@jsamadhan.demo", "3000000015", "university123"),
}

DEMO_FACULTY = [
    dict(name="Dr. Asha Verma", email="faculty1@jsamadhan.demo", phone="4000000001", password="faculty123",
         uni_key="uni1", department="Civil Engineering", designation="Professor",
         expertise="Transportation Engineering",
         research_interests="pavement durability, rural roads, pothole repair"),
    dict(name="Dr. Rajesh Kumar", email="faculty2@jsamadhan.demo", phone="4000000002", password="faculty123",
         uni_key="uni2", department="Computer Science", designation="Associate Professor",
         expertise="Cybersecurity", research_interests="digital forensics, cybercrime analytics"),
    dict(name="Dr. Meena Devi", email="faculty3@jsamadhan.demo", phone="4000000003", password="faculty123",
         uni_key="uni3", department="Agricultural Engineering", designation="Professor",
         expertise="Irrigation Engineering", research_interests="crop water management, drainage design"),
]

DEMO_STUDENTS = [
    dict(name="Ravi Kumar", email="student1@jsamadhan.demo", phone="5000000001", password="student123",
         uni_key="uni1", department="Civil Engineering", course="B.Tech Civil", year="3rd Year",
         skills="surveying, CAD drafting", interests="road infrastructure"),
    dict(name="Priya Singh", email="student2@jsamadhan.demo", phone="5000000002", password="student123",
         uni_key="uni2", department="Computer Science", course="B.Tech CSE", year="2nd Year",
         skills="python, networking basics", interests="cybersecurity"),
    dict(name="Sunil Oraon", email="student3@jsamadhan.demo", phone="5000000003", password="student123",
         uni_key="uni3", department="Agricultural Engineering", course="B.Sc Agriculture", year="4th Year",
         skills="field surveys, soil sampling", interests="irrigation systems"),
    dict(name="Meena Kujur", email="student4@jsamadhan.demo", phone="5000000004", password="student123",
         uni_key="uni1", department="Civil Engineering", course="B.Tech Civil", year="3rd Year",
         skills="drainage surveys, GIS mapping", interests="waterlogging resilience"),
]

DEMO_INDUSTRY_ORGS = [
    dict(name="Vidyut Infra & Civicworks Pvt Ltd", short_name="Vidyut Infra",
         email="vidyut@jsamadhan.demo", phone="6000000001", password="industry123",
         org_type="INDUSTRY", sector="Civil Roads Infrastructure",
         core_expertise="roads, pavement, drainage, waterlogging, GIS monitoring, public works",
         technologies="GIS, IoT sensors, surveying drones, condition scoring",
         capabilities="field surveys, road condition assessment, maintenance planning",
         address="Kanke Road, Ranchi", district="Ranchi", city="Ranchi",
         website="https://vidyutinfra.example",
         description="Infrastructure firm specialising in rural and urban road condition monitoring, "
                     "drainage design and public works project delivery.",
         verification_status="VERIFIED",
         verification_note="Verified infrastructure partner for government projects."),
    dict(name="AarogyaSparsh Health Solutions", short_name="AarogyaSparsh",
         email="aarogya@jsamadhan.demo", phone="6000000002", password="industry123",
         org_type="STARTUP", sector="HealthTech",
         core_expertise="telemedicine, diagnostics, digital health, mobile health",
         technologies="mobile apps, cloud dashboards, data analytics",
         capabilities="app development, health data dashboards",
         address="Adityapur, Jamshedpur", district="East Singhbhum", city="Jamshedpur",
         website="https://aarogyasparsh.example",
         description="HealthTech startup building affordable telemedicine and diagnostic platforms "
                     "for rural and semi-urban India.",
         verification_status="VERIFIED",
         verification_note="Verified digital health startup."),
    dict(name="KisanTech Agri Solutions", short_name="KisanTech",
         email="kisantech@jsamadhan.demo", phone="6000000003", password="industry123",
         org_type="MSME", sector="AgriTech",
         core_expertise="irrigation sensors, soil monitoring, crop management",
         technologies="IoT soil sensors, mobile apps",
         capabilities="agricultural IoT device deployment",
         address="Kanke, Ranchi", district="Ranchi", city="Ranchi",
         website="https://kisantech.example",
         description="AgriTech MSME deploying IoT-based irrigation and soil monitoring "
                     "solutions for smallholder farmers.",
         verification_status="PENDING",
         verification_note=None),
]


def seed_demo_users():
    """Create the demo accounts if the users table is empty, then seed the
    small demo institution ecosystem (universities, expertise, faculty and
    students) once, and auto-run university matching for challenges that are
    already awaiting it. All steps are additive and idempotent."""
    db.init_db()
    with app.app_context():
        conn = db.get_db()
        if conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] == 0:
            for name, email, phone, password, role in DEMO_USERS:
                db.create_user(conn, name, email, phone, password, role)

        if conn.execute("SELECT COUNT(*) c FROM universities").fetchone()["c"] == 0:
            uni_ids = {}
            for inst in DEMO_INSTITUTIONS:
                uni_id = db.create_university(
                    conn,
                    name=inst["name"], short_name=inst["short_name"],
                    email=inst["email"], phone=inst["phone"],
                    address=inst["address"], district=inst["district"],
                    website=inst["website"], description=inst["description"],
                    institution_type=inst["institution_type"],
                    verification_status=inst["verification_status"])
                for e in inst["expertise"]:
                    db.create_university_expertise(
                        conn, uni_id, e["department"], e["expertise"],
                        research_area=e["research_area"], keywords=e["keywords"],
                        lab_capabilities=e["lab_capabilities"],
                        description=e["description"])
                uni_ids[inst["key"]] = uni_id

            for key, (name, email, phone, password) in DEMO_INSTITUTION_ADMINS.items():
                uid = db.create_user(conn, name, email, phone, password, "university")
                db.update_university(conn, uni_ids[key], admin_user_id=uid)

            for f in DEMO_FACULTY:
                uid = db.create_user(conn, f["name"], f["email"], f["phone"],
                                     f["password"], "faculty")
                db.create_faculty_profile(
                    conn, uid, uni_ids[f["uni_key"]], f["department"],
                    designation=f["designation"], expertise=f["expertise"],
                    research_interests=f["research_interests"])

            for s in DEMO_STUDENTS:
                uid = db.create_user(conn, s["name"], s["email"], s["phone"],
                                     s["password"], "student")
                db.create_student_profile(
                    conn, uid, uni_ids[s["uni_key"]], s["department"],
                    course=s["course"], year=s["year"],
                    skills=s["skills"], interests=s["interests"])

            _ensure_university_matching_ready(conn)

        _seed_phase4_demo(conn)
        _seed_phase5_demo(conn)


def _seed_phase4_demo(conn):
    """Idempotent Phase 4 demo: BIT builds one team with an under-review
    proposal on JS-CH-0001 (roads & waterlogging) and one team with an
    approved proposal converted into a project on JS-CH-0003 (waterlogging
    cluster). Runs exactly once (guarded by an empty teams table) and only
    advances matches that are still RECOMMENDED/INVITED, so it never overrides
    decisions a reviewer has already made."""
    if conn.execute("SELECT COUNT(*) c FROM teams").fetchone()["c"] > 0:
        return

    def _uid(email):
        row = conn.execute("SELECT id FROM users WHERE email=?",
                           (email,)).fetchone()
        return row["id"] if row else None

    admin_id = _uid("university1@jsamadhan.demo")
    officer_id = _uid("officer1@jsamadhan.gov")
    faculty_id = _uid("faculty1@jsamadhan.demo")
    student1 = _uid("student1@jsamadhan.demo")
    uni = db.get_university_by_admin(conn, admin_id) if admin_id else None
    if not (admin_id and officer_id and faculty_id and student1 and uni):
        return
    uni_id = uni["id"]
    student4 = _uid("student4@jsamadhan.demo")
    if student4 is None:
        sid = db.create_user(conn, "Meena Kujur", "student4@jsamadhan.demo",
                             "5000000004", "student123", "student")
        db.create_student_profile(
            conn, sid, uni_id, "Civil Engineering",
            course="B.Tech Civil", year="3rd Year",
            skills="drainage surveys, GIS mapping",
            interests="waterlogging resilience")
        student4 = sid

    def _accept_challenge(code):
        """RECOMMENDED/INVITED -> ACCEPTED for BIT on the given challenge."""
        row = conn.execute("SELECT id FROM challenges WHERE code=?",
                           (code,)).fetchone()
        if row is None:
            row = conn.execute("SELECT id FROM challenges WHERE code LIKE ?",
                               (code + "%",)).fetchone()
        if row is None:
            return None
        match = conn.execute(
            "SELECT id, status FROM challenge_university_matches "
            "WHERE challenge_id=? AND university_id=?",
            (row["id"], uni_id)).fetchone()
        if match is None:
            return None
        if match["status"] == "RECOMMENDED":
            db.invite_university_match(conn, match["id"], officer_id)
            conn.commit()
        match = conn.execute(
            "SELECT id, status FROM challenge_university_matches WHERE id=?",
            (match["id"],)).fetchone()
        if match["status"] == "INVITED":
            db.respond_university_match(conn, match["id"], True,
                                        "Accepted for the Phase 4 demo.",
                                        admin_id)
            conn.commit()
        return row["id"]

    def _member(team_id, user_id, role):
        db.add_team_member(conn, team_id, user_id, role)

    # Scenario A — proposal under review (government is assessing it).
    ch1 = _accept_challenge("JS-CH-0001")
    if ch1 is not None:
        team1 = db.create_team(
            conn, ch1, uni_id, "Smart Rural Infrastructure Team",
            "BIT students and faculty building a low-cost rural road "
            "condition monitoring and maintenance system.", admin_id)
        if team1:
            _member(team1, faculty_id, "FACULTY_LEAD")
            _member(team1, student1, "TEAM_LEAD")
            _member(team1, student4, "STUDENT")
            p1 = db.create_proposal(
                conn, ch1, uni_id, team1,
                "Low-Cost Rural Road Condition Monitoring and Maintenance System",
                "Rural roads in Jharkhand deteriorate without timely intervention; "
                "potholes and drainage failures go unnoticed until repair costs rise.",
                "A lightweight, low-cost inspection workflow using geo-tagged "
                "field surveys, structured condition scoring and prioritised "
                "maintenance queues.",
                "Monthly condition surveys by trained students using a simple "
                "tablet app; severity scoring; repair workflow for the district "
                "road department.",
                "Reduced pothole repair costs and faster maintenance response.",
                "Tablet app, survey checklists, training manual.", "6 months",
                faculty_id)
            if p1:
                db.submit_proposal(conn, p1, faculty_id)
                db.begin_proposal_review(conn, p1, officer_id)
                conn.commit()

    # Scenario B — approved proposal, then a created project.
    ch3 = _accept_challenge("JS-CH-0003")
    if ch3 is not None:
        team2 = db.create_team(
            conn, ch3, uni_id, "Resilient Roads & Waterlogging Response Team",
            "BIT team focused on drainage-aware road integrity for recurring "
            "waterlogging clusters.", admin_id)
        if team2:
            _member(team2, faculty_id, "FACULTY_LEAD")
            _member(team2, student4, "TEAM_LEAD")
            _member(team2, student1, "STUDENT")
            p2 = db.create_proposal(
                conn, ch3, uni_id, team2,
                "Low-Cost Drainage and Road Integrity Monitoring",
                "Recurring waterlogging damages road surfaces and blocks "
                "movement; existing reports are anecdotal and uncoordinated.",
                "A coordinated geo-tagged monitoring and early-warning approach "
                "that links road condition to drainage health.",
                "Survey waterlogging hotspots, score road-drainage coupling, and "
                "produce a prioritised mitigation list for the district.",
                "Fewer flood-damage claims and better-planned drainage repairs.",
                "Survey kit, hotspot map, mitigation checklist.", "6 months",
                faculty_id)
            if p2:
                db.submit_proposal(conn, p2, faculty_id)
                db.begin_proposal_review(conn, p2, officer_id)
                db.review_proposal(conn, p2, "APPROVED",
                                   "Approved — low-cost, feasible and directly "
                                   "addresses the district's waterlogging reports.",
                                   officer_id)
                proposal = db.get_proposal(conn, p2)
                db.create_project_from_proposal(
                    conn, proposal,
                    "Rural Roads & Waterlogging Mitigation Project",
                    datetime.utcnow().date().isoformat(), "",
                    officer_id,
                    "Roll-out of the approved low-cost drainage and road "
                    "integrity monitoring across the affected blocks.")
                conn.commit()


def _seed_phase5_demo(conn):
    """Idempotent Phase 5 demo: three industry organisations (two government
    verified, one pending), plus two collaboration scenarios on the Phase 4
    project — Scenario A: one request sitting UNDER_REVIEW, Scenario B: one
    request ACCEPTED and connected to the project with a PROPOSED funding
    line. Runs exactly once (guarded by an empty industry_organizations
    table) and never re-verifies or re-submits anything a reviewer already
    handled."""
    if conn.execute(
            "SELECT COUNT(*) c FROM industry_organizations").fetchone()["c"] > 0:
        return

    def _uid(email):
        row = conn.execute("SELECT id FROM users WHERE email=?",
                           (email,)).fetchone()
        return row["id"] if row else None

    officer_id = _uid("officer1@jsamadhan.gov")
    admin_id = _uid("university1@jsamadhan.demo")
    if not (officer_id and admin_id):
        return

    project = None
    project_row = conn.execute(
        "SELECT id FROM projects WHERE proposal_id IN "
        "(SELECT id FROM proposals WHERE status='APPROVED') "
        "ORDER BY id ASC LIMIT 1").fetchone()
    if project_row is not None:
        project = db.get_project(conn, project_row["id"])

    # Create the three demo organizations once.
    for org in DEMO_INDUSTRY_ORGS:
        uid = db.create_user(conn, org["name"], org["email"], org["phone"],
                             org["password"], "industry")
        db.create_industry_organization(
            conn, uid, org["name"], org_type=org["org_type"],
            short_name=org.get("short_name"), legal_entity_name=org["name"],
            sector=org["sector"], core_expertise=org["core_expertise"],
            technologies=org["technologies"], capabilities=org["capabilities"],
            email=org["email"], phone=org["phone"], address=org.get("address"),
            district=org.get("district"), city=org.get("city"),
            website=org.get("website"), description=org.get("description"))

    def _scope_org(email):
        row = conn.execute(
            "SELECT o.* FROM industry_organizations o JOIN users u "
            "ON u.id=o.user_id WHERE u.email=?", (email,)).fetchone()
        return db.hydrate_industry_organization(conn, row) if row else None

    # Government verifies the two eligible partners (the MSME stays pending so
    # the review queue has live work).
    for org in DEMO_INDUSTRY_ORGS:
        if org["verification_status"] == "VERIFIED":
            row = conn.execute(
                "SELECT o.* FROM industry_organizations o JOIN users u ON "
                "u.id=o.user_id WHERE u.email=?",
                (org["email"],)).fetchone()
            db.verify_industry_organization(conn, row["id"], "VERIFIED",
                                            org["verification_note"],
                                            officer_id)

    if project is None:
        return
    org_a = _scope_org("vidyut@jsamadhan.demo")
    org_b = _scope_org("aarogya@jsamadhan.demo")
    if org_a is None or org_b is None:
        return

    # Scenario A — a request the government is still reviewing.
    try:
        r_a = db.express_interest(
            conn, project, org_a, org_a.user_id, "FUNDING",
            "Road survey scale-up partnership",
            "Partner with the team to scale the low-cost road and drainage "
            "condition monitoring across every affected block, contributing "
            "field equipment and condition-scoring hardware.",
            expected_support="20 field survey kits, IoT sensors, "
                             "maintenance planning",
            proposed_amount=250000, funding_type="GRANT",
            funding_description="Grant to fund equipment and field training "
                                "for the drainage monitoring rollout.")
        db.submit_collaboration(conn, r_a, org_a.user_id)
        db.begin_collaboration_review(conn, r_a, officer_id)
        conn.commit()
    except ValueError:
        pass

    # Scenario B — an accepted collaboration with a proposed funding line.
    try:
        r_b = db.express_interest(
            conn, project, org_b, org_b.user_id, "FUNDING",
            "Digital dashboards for waterlogging response",
            "Contribute a cloud dashboard and data-analytics layer that turns "
            "the team's geo-tagged survey data into clear maps for district "
            "response teams.",
            expected_support="cloud dashboard, data analytics, app interface",
            proposed_amount=800000, funding_type="CSR",
            funding_description="CSR contribution for the dashboard build "
                                "and one year of cloud hosting.")
        db.submit_collaboration(conn, r_b, org_b.user_id)
        db.begin_collaboration_review(conn, r_b, officer_id)
        db.review_collaboration(conn, r_b, "ACCEPTED",
                                "Approved — dashboard aligns with the "
                                "district waterlogging response plan and the "
                                "CSR funding is fully disclosed.",
                                officer_id)
        conn.commit()
    except ValueError:
        pass


if __name__ == "__main__":
    db.init_db()
    seed_demo_users()
    app.run(debug=True)