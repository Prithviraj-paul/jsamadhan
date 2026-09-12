"""
Seed optional demo complaints with map coordinates so the dashboards and the
Live Map look alive during a demo. Run `python seed_demo_data.py`.

This only fills the complaints table when it is empty; run once after a fresh
database. To start over: stop the server, delete jsamadhan.db + uploads/*,
then `python seed_demo_data.py` again.
"""

import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import db

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

DEMO = [
    ("Deep potholes on Harmu bridge approach", "Roads & Infrastructure", "Ranchi", 84, "AI Verified"),
    ("Hand pump dry since monsoon ended", "Water Resources", "Gumla", 66, "Pending Officer Review"),
    ("Street lights dark on MG Road", "Electricity", "Dhanbad", 52, "Accepted by Officer"),
    ("Garbage pile near bus stop", "Sanitation", "Bokaro", 41, "Pending Officer Review"),
    ("PHC building plaster peeling", "Healthcare", "Hazaribagh", 33, "Submitted"),
    ("School ceiling damaged after rains", "Education", "Dumka", 27, "Submitted"),
    ("Broken paver blocks on footpath", "Roads & Infrastructure", "Deoghar", 19, "Rejected"),
    ("Drain overflow during rainfall", "Sanitation", "Giridih", 74, "Accepted by Officer"),
    ("Classroom without electricity", "Education", "West Singhbhum", 45, "Pending Officer Review"),
    ("Water tank leak near market", "Water Resources", "East Singhbhum", 58, "Resolved"),
    ("Roadside debris blocking lane", "Roads & Infrastructure", "Hazaribagh", 22, "Resolved"),
    ("Transformer hum and sparking", "Electricity", "Ranchi", 91, "AI Verified"),
]


def _urgency(score):
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "normal"
    return "low"


def main():
    import app as app_mod
    db.init_db()
    with app_mod.app.app_context():
        conn = db.get_db()
        count = conn.execute("SELECT COUNT(*) c FROM complaints").fetchone()["c"]
        if count:
            print(f"Complaints table already has {count} rows — not seeding. A clean start:"
                  "\n  stop server, delete jsamadhan.db and uploads/*, then rerun.")
            return

        rnd = random.Random(7)
        citizen = conn.execute("SELECT id FROM users WHERE role='citizen' ORDER BY id LIMIT 1").fetchone()
        if citizen is None:
            print("No citizen user found — start the app once so demo users are seeded first.")
            return
        citizen_id = citizen["id"]
        officer1 = conn.execute("SELECT id FROM users WHERE role='officer' ORDER BY id LIMIT 1").fetchone()["id"]
        officer2 = conn.execute("SELECT id FROM users WHERE role='officer' ORDER BY id LIMIT 2").fetchall()[-1]["id"]

        now = datetime.utcnow()
        for i, (title, category, district, severity, status) in enumerate(DEMO):
            lat, lng = CITY_PINS[district]
            # jitter the pin slightly so markers don't stack exactly
            lat += rnd.uniform(-0.015, 0.015)
            lng += rnd.uniform(-0.015, 0.015)
            code = db.new_complaint_code(conn)
            created = now - timedelta(days=rnd.randint(0, 40), hours=rnd.randint(0, 23))

            cid = db.create_complaint(
                conn,
                code=code,
                title=title,
                description=title + ". Reported for civic action under Jharkhand Samadhan.",
                category=category,
                district=district,
                location_text=district + " (demo data)",
                latitude=round(lat, 5),
                longitude=round(lng, 5),
                citizen_id=citizen_id,
                status=status,
                severity=severity,
                urgency=_urgency(severity),
                created_at=created.isoformat(),
            )
            db.add_log(conn, cid, "Submitted", "Complaint registered by citizen. AI severity estimate generated.")
            if status == "AI Verified":
                db.set_status(conn, cid, "AI Verified",
                              "Automated satellite screening matched the report (confidence "
                              f"{rnd.randint(66, 96)}%).", {"ai_confidence": rnd.randint(66, 96),
                                                            "ai_note": "Satellite pass shows a visible anomaly at the location."})
            elif status == "Pending Officer Review":
                db.set_status(conn, cid, "Pending Officer Review", "Awaiting manual verification by an officer.")
            elif status == "Accepted by Officer":
                off = officer1 if i % 2 == 0 else officer2
                deadline = now + timedelta(days=db.URGENCY_SLA_DAYS[_urgency(severity)])
                db.set_status(conn, cid, "Accepted by Officer",
                              f"Accepted by officer. Resolution due by {deadline:%Y-%m-%d}.",
                              {"officer_id": off, "accepted_at": now.isoformat(),
                               "deadline": deadline.isoformat()})
            elif status == "Resolved":
                resolved = created + timedelta(days=4)
                db.set_status(conn, cid, "Accepted by Officer",
                              "Accepted by officer and resolved on ground.",
                              {"officer_id": officer1, "accepted_at": (created + timedelta(days=1)).isoformat(),
                               "deadline": (created + timedelta(days=5)).isoformat()})
                db.set_status(conn, cid, "Resolved",
                              "Officer confirmed completion; AI change score satisfied.",
                              {"resolution_confidence": round(58 + i, 1),
                               "resolved_at": resolved.isoformat()})
            elif status == "Rejected":
                db.set_status(conn, cid, "Rejected", "After verification the reported site was found unchanged.")

    print(f"Seeded {len(DEMO)} demo complaints with map pins. Open /admin/map (or /officer/map) to see them.")


if __name__ == "__main__":
    main()