# Jharkhand Samadhan

**From local problems to scalable solutions.**

Jharkhand Samadhan is a collaborative problem-solving platform that transforms
verified local problems into structured innovation challenges and connects them
with government, academia and industry for solution development, field pilots,
impact assessment and scaling.

A Smart India Hackathon prototype (demo only — not an official Government of
Jharkhand service).

---

## Problem

Fragmented societal problems often remain isolated reports.

## Solution

Jharkhand Samadhan converts citizen evidence into validated challenges and
connects them with institutions capable of developing and testing solutions.

A grievance system closes individual tickets. Jharkhand Samadhan also
identifies recurring patterns and turns validated systemic problems into
collaborative innovation challenges.

---

## Phase-1 Focus

To demonstrate measurable real-world impact, the current pilot concentrates on
three high-impact areas (new reports and challenges use only these; older
records keep rendering under their legacy categories):

- **Roads & Public Infrastructure** — potholes, damaged roads, culverts,
  streetlights, roadside drainage, unsafe public assets
- **Water & Sanitation** — handpumps, pipeline leakage, drinking water,
  waterlogging, drains, community sanitation
- **Education Infrastructure** — school buildings, classrooms, toilets,
  drinking water, electricity, accessibility (infrastructure only — no student
  personal data is ever collected)

The underlying collaboration model is designed to support additional sectors
in future phases.

## End-to-end workflow

Report → Validate → Consolidate → Challenge → Match → Solution → Pilot →
Impact → Scale

1. **Report** — citizen Problem Report with photo/video + location pin
2. **Validate** — AI-assisted evidence screening + officer review (humans decide)
3. **Consolidate** — recurring reports grouped; duplicates flagged for review
4. **Challenge** — government validates an Official Challenge
5. **Match** — universities matched by registered expertise (government invites)
6. **Solution** — teams submit evidence-based Solution Proposals → Project
7. **Pilot** — Prototype → field Testing → field Pilot with industry partners
8. **Impact** — Impact Assessment of outcomes and beneficiaries
9. **Scale** — government-reviewed Scaling to additional districts

## Stakeholders

- **Citizens** — report problems with evidence, track progress
- **Government** (Officer, Admin) — validate, prioritize, monitor, scale
- **Universities** — discover challenges, manage expertise, form teams
- **Researchers** (Faculty) — lead teams and proposals
- **Students** — join teams and build solutions
- **Industry partners** — fund and support prototypes, pilots and scaling

## Public pages (no login required)

- `/` — story, focus areas, ecosystem, workflow, live map, challenge preview
- `/challenges` + `/challenges/<id>` — validated Official Challenges only
- `/track` + `/track/<code>` — tracking-code entry + citizen journey view
- `/impact` — aggregated pilot/impact/scaling dashboard (demo-labelled)
- `/api/live-problems` — map feed with public-safe fields only (no PII)

## Technology

| Layer     | Technology                                                        |
|-----------|-------------------------------------------------------------------|
| Backend   | Python, Flask, SQLite (plain `sqlite3`, no ORM), Werkzeug         |
| AI        | Pillow-based photo analysis, duplicate detection, before/after comparison, photo-evidence screening, Web Speech voice input |
| Frontend  | Jinja templates, HTML/CSS/JS, Leaflet + OpenStreetMap + MarkerCluster |
| Automation| 24h notification worker, 3-day action SLA worker, auto-escalation |
| i18n      | English + Hindi (+ additional language fallbacks), role-aware UI   |

> AI assists with recommendations and pattern detection — government officers
> make all validation, invitation and approval decisions.

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

## Demo accounts

Seeded automatically (unless `SEED_DEMO_USERS=0`). A compact **Demo Access**
section also lives on the Login page:

| Role        | Email                   | Password       |
|-------------|-------------------------|----------------|
| Admin       | admin@jsamadhan.gov     | `admin123`     |
| Officer     | officer1@jsamadhan.gov  | `officer123`   |
| Citizen     | citizen@example.com     | `citizen123`   |
| University  | university1@jsamadhan.demo | `university123` |
| Faculty     | faculty1@jsamadhan.demo | `faculty123`   |
| Student     | student1@jsamadhan.demo | `student123`   |
| Industry    | vidyut@jsamadhan.demo   | `industry123`  |

> Demo credentials are enabled by default so the instance is easy to explore;
> rotate or disable them (`SEED_DEMO_USERS=0`) before public sharing.

## Project structure

```
app.py            Flask application and routes
db.py             SQLite schema and data access (safe additive migrations)
i18n.py           English + Hindi dictionaries
ai_engine.py      AI-assisted verification / comparison / duplicate detection
notifications.py  24h + SLA deadline background worker
seed_demo_data.py Demo users, institutions, problems
run_server.py     Robust launcher (port guard, crash log, DB init)
templates/        Jinja templates (global header partial, public pages, dashboards)
static/           CSS, JS (hamburger drawer, maps, filters), images
uploads/          User-uploaded evidence (access-controlled)
```
