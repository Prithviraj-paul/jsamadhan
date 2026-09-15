"""
Seed optional demo complaints with map coordinates, real uploaded photos and
AI verification metadata so the dashboards, the Live Map, and the public
"Fixed & Verified" gallery look alive during a demo. Run `python seed_demo_data.py`.

This only fills the complaints table when it is empty; run once after a fresh
database. To start over: stop the server, delete jsamadhan.db + uploads/*,
then `python seed_demo_data.py` again.
"""

import json
import os
import random
import shutil
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import db

SEED_ASSETS = os.path.join(os.path.abspath(os.path.dirname(__file__)), "seed_assets")


def ensure_seed_photos():
    """Copy demo photos from the tracked seed_assets/ folder into uploads/,
    because uploads/ is gitignored (fresh clones need these to exist)."""
    uploads = os.path.join(os.path.abspath(os.path.dirname(__file__)), "uploads")
    os.makedirs(uploads, exist_ok=True)
    for name in os.listdir(SEED_ASSETS):
        src = os.path.join(SEED_ASSETS, name)
        if os.path.isfile(src) and not os.path.exists(os.path.join(uploads, name)):
            shutil.copy2(src, uploads)
            print(f"  copied {name} -> uploads/")

# Approximate city centres used as fake pin locations (lat, lng).
CITY_PINS = {
    "Ranchi": [23.3441, 85.3096],
    "Dhanbad": [23.7956, 86.4304],
    "Dumka": [24.2679, 87.2485],
    "Bokaro": [23.6693, 86.1511],
    "Gumla": [23.0435, 84.5418],
    "Deoghar": [24.4814, 86.6977],
    "Hazaribagh": [23.9925, 85.3620],
    "Giridih": [24.1927, 86.3060],
    "East Singhbhum": [22.7903, 86.2021],   # Jamshedpur
    "West Singhbhum": [22.2167, 85.5379],    # Chaibasa
}

# Real photos shipped in uploads/ (before/after pairs for the RESOLVED cases).
DEMO = [
    dict(title="Deep potholes on Main Road near Daily Market",
         description="Multiple deep potholes outside the Daily Market gate. Two-wheeler riders are skidding, especially after rain. Needs urgent re-carpeting.",
         category="Roads & Infrastructure", district="Ranchi", severity=84,
         status="Resolved", photo="seed_pothole.jpg", resolution="seed_road_fixed.jpg"),
    dict(title="All four streetlights dead on Sector 4 market road",
         description="The whole 200-metre stretch near the market goes pitch dark after sunset. Women and schoolchildren feel unsafe walking here.",
         category="Electricity", district="Bokaro", severity=60,
         status="Resolved", photo="seed_street_dark.jpg", resolution="seed_street_lit.jpg"),
    dict(title="Transformer hum and sparking near bank",
         description="Frequent sparks at the transformer above the bank branch; children play nearby every evening.",
         category="Electricity", district="Ranchi", severity=91,
         status="AI Verified", photo="seed_street_dark.jpg"),
    dict(title="Roadside debris blocking lane after rains",
         description="Earthen debris and broken slabs have blocked half the lane since the last storm.",
         category="Roads & Infrastructure", district="Hazaribagh", severity=22,
         status="AI Verified", photo="seed_garbage.jpg"),
    dict(title="Hand pump dry since monsoon ended",
         description="The only handpump on our lane has gone completely dry. Around 40 families depend on it for drinking water.",
         category="Water Resources", district="Gumla", severity=66,
         status="Pending Officer Review", photo="seed_handpump.jpg"),
    dict(title="Garbage pile near bus stop",
         description="Municipal van has not come for ten days; the pile now blocks half the footpath.",
         category="Sanitation", district="Bokaro", severity=41,
         status="Pending Officer Review", photo="seed_garbage.jpg"),
    dict(title="PHC building plaster peeling",
         description="Peeling plaster and damp streaks across the OPD wall; patients say water seeps in during rain.",
         category="Healthcare", district="Hazaribagh", severity=33,
         status="Submitted"),
    dict(title="School ceiling damaged after rains",
         description="A large section of the classroom ceiling collapsed overnight; classes have moved outside.",
         category="Education", district="Dumka", severity=27,
         status="Submitted", photo="seed_school.jpg"),
    dict(title="Broken paver blocks on footpath",
         description="Paver blocks are lifted and cracked along the footpath; elderly residents keep tripping.",
         category="Roads & Infrastructure", district="Deoghar", severity=19,
         status="Rejected", photo="seed_pothole.jpg"),
    dict(title="Drinking water pipeline leaking day and night",
         description="Clean water has been gushing from a burst joint since yesterday morning; a tanker of water is wasted daily.",
         category="Water Resources", district="East Singhbhum", severity=58,
         status="Accepted by Officer", photo="seed_pipe.jpg"),
    dict(title="Drain overflow during rainfall",
         description="Drain water meets the road within minutes of heavy rain; the crossing becomes unusable.",
         category="Sanitation", district="Giridih", severity=74,
         status="Accepted by Officer"),
    dict(title="Classroom without electricity",
         description="The only classroom equipped with fans has had no power connection for a month.",
         category="Education", district="West Singhbhum", severity=45,
         status="Pending Officer Review"),
]


def _urgency(score):
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "normal"
    return "low"


def _verify_detail(verified, category, signals):
    """Stable, believable AI verification payload stored in complaints.ai_detail"""
    return {
        "confidence": 74 if verified else 48,
        "verified": bool(verified),
        "category": category,
        "threshold": 62,
        "signals": signals,
        "warnings": [],
    }


def _move(conn, cid, status, note, ts, extra=None):
    """Transition status with a correct timestamped history entry."""
    fields = dict(extra or {})
    fields["status"] = status
    set_clause = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE complaints SET {set_clause} WHERE id=?", (*fields.values(), cid))
    conn.execute(
        "INSERT INTO complaint_logs (complaint_id, status, note, timestamp) VALUES (?,?,?,?)",
        (cid, status, note, ts.isoformat()),
    )
    conn.commit()


def main():
    ensure_seed_photos()
    import app as app_mod
    db.init_db()
    with app_mod.app.app_context():
        conn = db.get_db()
        count = conn.execute("SELECT COUNT(*) c FROM complaints").fetchone()["c"]
        if count:
            print(f"Complaints table already has {count} rows — not re-seeding complaints."
                  "\n  A clean start: stop server, delete jsamadhan.db and uploads/*, then rerun.")
            # Still ensure demo official challenges exist for the Command Center demo.
            seed_demo_challenges(conn)
            return

        rnd = random.Random(7)
        citizen = conn.execute("SELECT id FROM users WHERE role='citizen' ORDER BY id LIMIT 1").fetchone()
        if citizen is None:
            print("No citizen user found — start the app once so demo users are seeded first.")
            return
        citizen_id = citizen["id"]
        officers = [r["id"] for r in conn.execute(
            "SELECT id FROM users WHERE role='officer' ORDER BY id LIMIT 2").fetchall()]
        officer1 = officers[0]
        officer2 = officers[-1]

        now = datetime.utcnow()
        for i, it in enumerate(DEMO):
            title = it["title"]
            category = it["category"]
            district = it["district"]
            severity = it["severity"]
            status = it["status"]

            lat, lng = CITY_PINS[district]
            lat += rnd.uniform(-0.015, 0.015)
            lng += rnd.uniform(-0.015, 0.015)
            code = db.new_complaint_code(conn)
            created = now - timedelta(days=rnd.randint(2, 40), hours=rnd.randint(0, 23))

            # deterministic AI-verification payload for photo-based cases
            ai_detail = None
            verified = status == "AI Verified"
            detail_signals = [
                "Description keywords consistent with the category: streetlight, dark, unsafe.",
                "Visible structures against the dark — masts/poles/wiring plausible.",
            ]
            if it.get("photo") and status in ("AI Verified", "Resolved", "Pending Officer Review"):
                ai_detail = json.dumps(_verify_detail(verified, category, detail_signals),
                                       ensure_ascii=False)

            cid = db.create_complaint(
                conn,
                code=code,
                title=title,
                description=it["description"],
                category=category,
                district=district,
                location_text=district + " (demo data)",
                latitude=round(lat, 5),
                longitude=round(lng, 5),
                photo_filename=it.get("photo"),
                citizen_id=citizen_id,
                status="Submitted",
                severity=severity,
                urgency=_urgency(severity),
                ai_confidence=(74 if verified else 48) if ai_detail else None,
                ai_note=("AI cross-checked the photo against the reported problem and found "
                         "consistent visual and textual evidence (confidence 74%). Auto-verified."
                         if verified else None),
                ai_detail=ai_detail,
                created_at=created.isoformat(),
                action_due_at=(created + timedelta(days=3)).isoformat(),
                notify_sent_at=(created + timedelta(days=1)).isoformat(),
            )
            _move(conn, cid, "Submitted", "Complaint registered by citizen. AI severity estimate generated.", created)

            if status == "AI Verified":
                _move(conn, cid, "AI Verified",
                      "Automated satellite screening matched the report (confidence "
                      f"{rnd.randint(66, 96)}%).", created + timedelta(hours=2),
                      {"ai_note": "Satellite pass shows a visible anomaly at the location."})
            elif status == "Pending Officer Review":
                if ai_detail:
                    _move(conn, cid, "Pending Officer Review",
                          "AI cross-check of the photo could not fully confirm the "
                          f"reported problem ({category}) (confidence 48%). Routed to a "
                          "officer for manual verification.", created + timedelta(hours=2))
                else:
                    _move(conn, cid, "Pending Officer Review",
                          "Awaiting manual verification by an officer.", created + timedelta(days=1))
            elif status == "Accepted by Officer":
                off = officer1 if i % 2 == 0 else officer2
                deadline = now + timedelta(days=db.URGENCY_SLA_DAYS[_urgency(severity)])
                _move(conn, cid, "Accepted by Officer",
                      f"Accepted by officer. Resolution due by {deadline:%Y-%m-%d}.",
                      created + timedelta(days=2),
                      {"officer_id": off, "accepted_at": (created + timedelta(days=2)).isoformat(),
                       "deadline": deadline.isoformat()})
            elif status == "Resolved":
                resolved = created + timedelta(days=5)
                _move(conn, cid, "Accepted by Officer",
                      "Accepted by officer and resolved on ground.",
                      created + timedelta(days=2),
                      {"officer_id": officer1, "accepted_at": (created + timedelta(days=2)).isoformat(),
                       "deadline": (created + timedelta(days=7)).isoformat()})
                _move(conn, cid, "Resolved",
                      "Officer confirmed completion; AI change score satisfied.",
                      resolved,
                      {"resolution_filename": it.get("resolution"),
                       "resolution_confidence": round(58 + i, 1),
                       "resolved_at": resolved.isoformat()})
            elif status == "Rejected":
                _move(conn, cid, "Rejected", "After verification the reported site was found unchanged.",
                      created + timedelta(days=3))

        # --- accountability demo pass ------------------------------------
        # Notification is already "sent within 24 hours" for every seed (the
        # checked-in photos are older than 24h), while action deadlines are
        # pushed into the future so the live checker never auto-escalates the
        # static demo queue. Real submissions during the demo run the FULL
        # 24h-notify + 3-day + auto-escalate cycle.
        future = now + timedelta(days=1)
        conn.execute(
            "UPDATE complaints SET action_due_at=? WHERE status IN "
            "('Submitted','AI Verified','Pending Officer Review','Accepted by Officer','Reopened') "
            "AND action_due_at < ?",
            (future.isoformat(), now.isoformat()))
        conn.commit()

        # One real escalated case so the higher-authority queue has content.
        esc_created = now - timedelta(days=8)
        esc_lat, esc_lng = CITY_PINS["Dhanbad"]
        esc_lat += rnd.uniform(-0.015, 0.015)
        esc_lng += rnd.uniform(-0.015, 0.015)
        cid = db.create_complaint(
            conn,
            code=db.new_complaint_code(conn),
            title="Traffic signal dark at Bansidih crossing for over a week",
            description="Signal has not worked for 8 days; daily peak-hour jams and near-misses. "
                        "Officials missed the promised action deadline.",
            category="Roads & Infrastructure", district="Dhanbad",
            location_text="Dhanbad (demo data)",
            latitude=round(esc_lat, 5), longitude=round(esc_lng, 5),
            citizen_id=citizen_id, status="Escalated",
            severity=66, urgency="high",
            ai_confidence=62,
            ai_note="Satellite pass shows congestion anomaly at the junction.",
            created_at=esc_created.isoformat(),
            action_due_at=(esc_created + timedelta(days=3)).isoformat(),
            notify_sent_at=(esc_created + timedelta(days=1)).isoformat(),
            escalated_at=(esc_created + timedelta(days=5)).isoformat(),
        )
        _move(conn, cid, "Submitted",
              "Complaint registered by citizen. AI severity estimate generated.", esc_created)
        _move(conn, cid, "Committed",
              "Citizen will be notified within 24 hours. Officials will take action within 2\u20133 days.",
              esc_created + timedelta(hours=1))
        _move(conn, cid, "Notification",
              "Citizen notified within 24 hours (demo SMS/call).", esc_created + timedelta(days=1))
        esc_deadline = esc_created + timedelta(days=7)
        _move(conn, cid, "Accepted by Officer",
              "Accepted by officer. Resolution due by " + esc_deadline.strftime("%Y-%m-%d") + ".",
              esc_created + timedelta(days=2),
              {"officer_id": officer1, "accepted_at": (esc_created + timedelta(days=2)).isoformat(),
               "deadline": esc_deadline.isoformat()})
        _move(conn, cid, "Escalated",
              "Action was not completed within the promised 2\u20133 days. Complaint escalated "
              "to higher authority for immediate disposal.", esc_created + timedelta(days=5))

        print(f"Seeded {len(DEMO) + 1} demo complaints with map pins and photos."
              "\n  Open /admin/map (or /officer/map) to see the Live Map.")
        print("  The public landing page now shows 2 resolved cases with real before/after photos.")

        # --- minimal official challenges (Government Command Center) --------
        seed_demo_challenges(conn)


def seed_demo_challenges(conn):
    """Create two demo official challenges only when the challenges table is
    empty and the required demo complaints exist. Runs as a harmless no-op
    if the table already has rows."""
    import app as app_mod
    from app import _challenge_ai_recommendation

    ch_count = conn.execute("SELECT COUNT(*) c FROM challenges").fetchone()["c"]
    if ch_count:
        print(f"  Challenges table already has {ch_count} rows — not seeding demo challenges.")
        return

    now = datetime.utcnow()
    admin_id = conn.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
    officer_id = conn.execute("SELECT id FROM users WHERE role='officer' ORDER BY id LIMIT 1").fetchone()
    admin_id = admin_id["id"] if admin_id else 1
    officer_id = officer_id["id"] if officer_id else 2

    # Link to the first two seeded complaints (potholes + dead streetlights).
    c1 = conn.execute("SELECT id FROM complaints WHERE title LIKE '%Deep potholes%' LIMIT 1").fetchone()
    c2 = conn.execute("SELECT id FROM complaints WHERE title LIKE '%streetlights dead%' LIMIT 1").fetchone()

    with app_mod.app.app_context():
        if c1:
            rows1 = [dict(conn.execute("SELECT * FROM complaints WHERE id=?", (c1["id"],)).fetchone())]
            rec1 = _challenge_ai_recommendation(rows1)
            ch1_id = db.create_challenge(
                conn,
                code=db.new_challenge_code(conn),
                title="Persistent waterlogging and road damage",
                description="Multiple citizen reports highlight severe road deterioration and recurring waterlogging in this sector. Requires coordinated municipal and public works intervention.",
                category="Roads & Infrastructure",
                subcategory="Road Damage",
                district="Ranchi",
                location_text="Ranchi (demo data)",
                latitude=rows1[0]["latitude"], longitude=rows1[0]["longitude"],
                priority_score=rec1["score"], priority_level=rec1["level"],
                ai_summary=rec1["summary"], ai_confidence=rec1["confidence"],
                created_by=admin_id,
            )
            db.link_complaints_to_challenge(conn, ch1_id, [c1["id"]])
            db.validate_challenge(conn, ch1_id, admin_id)
            conn.commit()
            ch1_code = db.get_challenge_row(conn, challenge_id=ch1_id)["code"]
            print(f"  Seeded official challenge {ch1_code} -> linked complaint #{c1['id']}")

        if c2:
            rows2 = [dict(conn.execute("SELECT * FROM complaints WHERE id=?", (c2["id"],)).fetchone())]
            rec2 = _challenge_ai_recommendation(rows2)
            ch2_id = db.create_challenge(
                conn,
                code=db.new_challenge_code(conn),
                title="Unsafe street lighting in market corridor",
                description="Complete darkness along a 200-metre market stretch after sunset. Safety risk for women, children and commuters. Municipal coordination required.",
                category="Electricity",
                subcategory="Street Lighting",
                district="Bokaro",
                location_text="Bokaro (demo data)",
                latitude=rows2[0]["latitude"], longitude=rows2[0]["longitude"],
                priority_score=rec2["score"], priority_level=rec2["level"],
                ai_summary=rec2["summary"], ai_confidence=rec2["confidence"],
                created_by=officer_id,
            )
            db.link_complaints_to_challenge(conn, ch2_id, [c2["id"]])
            db.add_challenge_log(conn, ch2_id, "NEEDS_VALIDATION",
                             "Challenge created by officer. Government users notified via the command feed.",
                             officer_id)
            conn.commit()
            ch2_code = db.get_challenge_row(conn, challenge_id=ch2_id)["code"]
            print(f"  Seeded official challenge {ch2_code} -> linked complaint #{c2['id']}")


if __name__ == "__main__":
    main()