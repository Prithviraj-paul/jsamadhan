# Jharkhand Samadhan

**Report it. Track it. See it fixed.**

A Smart India Hackathon prototype for the Government of Jharkhand: one platform
that takes a civic problem from a citizen report to a district-wide, verified,
scaled solution.

Live demo: https://majority-bolt-rentable.ngrok-free.dev

---

## What it does

- **Citizen reporting** — snap a photo/video, pin the location, pick a category.
  Every report gets a public tracking code (e.g. `JS-37740`).
- **AI screening** — satellite/photo verification for road reports and automatic
  duplicate detection keep the queue honest.
- **Officer + SLA** — a field officer verifies and accepts the case with a fixed
  resolution deadline; overdue cases auto-escalate.
- **Before/After proof** — the officer uploads the after-photo; AI compares
  before/after and closes the case. Results appear on the public gallery and
  the live map.
- **Live Problems Map** — public, unauthenticated Leaflet + OpenStreetMap view
  on the landing page with marker clustering, urgency colouring
  (critical/high/normal/low/unspecified), status, district, reported date, and
  a *View Problem* link to the tracking page. Only safe public fields are
  exposed — no PII.
- **Challenges & collaboration** — government posts official challenges; AI
  matches universities by expertise; teams propose solutions; government
  reviews and approves.
- **Industry collaboration** — partner organizations fund prototypes and pilots.
- **Pilot → Deployment** — field pilots are tracked with progress logs until
  deployed.
- **Impact assessment** — teams report outcomes; government evaluates deployed
  projects.
- **Scaling review** — approved projects expand to new districts through a full
  approval flow.
- **Seven roles** — Citizen, Officer, Admin, University team, Faculty, Student,
  and Industry partner, each with the right views and permissions.
- **English + Hindi** — complete localization (1007 keys per language).

## How it works (8 steps)

1. **Report** — photo/video + location pin
2. **AI Screen** — satellite/photo check + duplicate scan
3. **Officer + SLA** — verified & accepted with a deadline
4. **Before/After** — photo proof it's actually fixed
5. **Resolved** — shown on gallery + live map
6. **University Teams** — faculty + students take on official challenges
7. **Industry Pilots** — partners fund field pilots
8. **Impact & Scale** — measure impact, then expand districts

## Tech stack

| Layer     | Technology                                                              |
|-----------|-------------------------------------------------------------------------|
| Backend   | Python, Flask, SQLite, Werkzeug                                         |
| AI/ML     | Satellite photo verification, duplicate detection, before/after comparison, voice-to-text + OCR reporting |
| Frontend  | HTML/CSS/JS, responsive layout, Leaflet + OpenStreetMap + MarkerCluster |
| Automation| 24h notification worker, 3-day action SLA worker, auto-escalation       |
| Testing   | Phase-level suites (UI, DB, end-to-end, render sweep)                   |

## Getting started

### Requirements

- Python 3.10+
- `pip install -r requirements.txt`

### Run locally

```bash
python run_server.py
```

or on Windows double-click `start.bat`.

Then open http://127.0.0.1:5000

`run_server.py` auto-initialises the database and seeds demo data. Set
`SEED_DEMO_USERS=0` to start with a clean database and normal signup only.

### Public access

An ngrok tunnel exposes the local server at
https://majority-bolt-rentable.ngrok-free.dev. Add the header
`ngrok-skip-browser-warning: 1` to skip the browser interstitial.

## Demo accounts

Seeded automatically (unless `SEED_DEMO_USERS=0`):

| Role        | Email                   | Password       |
|-------------|-------------------------|----------------|
| Admin       | admin@jsamadhan.gov     | `admin123`     |
| Officer     | officer1@jsamadhan.gov  | `officer123`   |
| Citizen     | citizen@example.com     | `citizen123`   |
| Faculty     | faculty1@jsamadhan.demo | `faculty123`   |
| Student     | student1@jsamadhan.demo | `student123`   |
| University  | *(institution admin)*   | —              |
| Industry    | vidyut@jsamadhan.demo   | `industry123`  |

> Demo credentials are enabled by default so the instance is easy to explore;
> rotate or disable them (`SEED_DEMO_USERS=0`) before public sharing.

## Public API

`GET /api/live-problems` — unauthenticated feed for the landing map.

Returns only safe public fields per problem: `code, title, category,
category_label, district, district_label, status, status_label, urgency,
urgency_label, severity, location_text, lat, lng, created_at, track_url`.
No citizen/officer IDs, phone numbers, private photos, or internal notes.

## Tests

Phase-level regression suites live alongside the project:

- `test_p8_ui.py` — Phase 8 UI checks (map, role picker, API, PII, i18n)
- `test_p7_db.py` / `test_p7_e2e.py` — Phase 7 impact & scaling workflows
- `test_p6_e2e.py` — Phase 6 pilot & deployment workflows
- `sweep_p7.py` — role/render sweep across the app
- `parity_check.py` — EN/HI translation parity

```bash
python test_p8_ui.py
python test_p7_db.py
python test_p7_e2e.py
python test_p6_e2e.py
python sweep_p7.py
python parity_check.py
```

## Project structure

```
app.py            Flask application, routes, Phase 8 public map API
db.py             SQLite schema and data access (phases 1–7)
i18n.py           English + Hindi dictionaries (1007 keys each)
ai_engine.py      AI verification / comparison / duplicate detection
notifications.py  24h + SLA deadline background worker
seed_demo_data.py Demo users, institutions, problems
run_server.py     Robust launcher (port guard, crash log, DB init)
templates/        Jinja templates (landing, login, dashboards, ...)
static/           CSS, JS, images
uploads/          User-uploaded evidence (access-controlled)
```

## Phase history

| Phase | What shipped                                                        |
|-------|---------------------------------------------------------------------|
| 1–3   | Citizen reporting, AI verification, officer SLA, tracking, gallery   |
| 4     | Teams, proposals, projects with government review                    |
| 5     | Industry collaboration, university challenge matching                |
| 6     | Prototypes, testing, pilots, deployment                              |
| 7     | Impact assessment → scaling approval workflow                        |
| 8     | Live Problems Map, responsive role picker, UI polish                 |