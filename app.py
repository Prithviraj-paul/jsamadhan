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
    verify_image_against_problem,
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
    return render_template(
        "officer_dashboard.html",
        queue=queue, my_cases=my_cases, resolved=resolved,
    )


@app.route("/officer/complaint/<int:complaint_id>")
@login_required(role="officer")
def officer_complaint(complaint_id):
    conn = db.get_db()
    complaint = db.hydrate_complaint(conn, db.get_complaint_row(conn, complaint_id))
    if complaint is None:
        flash("Complaint not found.", "error")
        return redirect(url_for("officer_dashboard"))
    return render_template("officer_complaint.html", complaint=complaint)


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
    return render_template("admin_complaint.html", complaint=complaint, officers=officers)


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


DEMO_USERS = [
    ("Jharkhand Admin", "admin@jsamadhan.gov", "0000000000", "admin123", "admin"),
    ("Ramesh Kumar", "officer1@jsamadhan.gov", "1000000001", "officer123", "officer"),
    ("Sita Devi", "officer2@jsamadhan.gov", "1000000002", "officer123", "officer"),
    ("Amit Kumar", "citizen@example.com", "2000000001", "citizen123", "citizen"),
]


def seed_demo_users():
    """Create the demo accounts if the users table is empty."""
    db.init_db()
    with app.app_context():
        conn = db.get_db()
        if conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] == 0:
            for name, email, phone, password, role in DEMO_USERS:
                db.create_user(conn, name, email, phone, password, role)


if __name__ == "__main__":
    db.init_db()
    seed_demo_users()
    app.run(debug=True)