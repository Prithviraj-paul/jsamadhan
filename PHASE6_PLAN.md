# Phase 6 — Implementation Plan (Inspection Only)

**Status:** Read-only inspection + plan. **Zero app files modified, server NOT restarted, ngrok untouched, nothing committed/pushed.**
**Constraint:** No AI unless a demonstrated requirement. No UI redesign. No functionality outside Phase 6.
**Objective workflow:** Project → Prototype → Testing → Pilot → Deployment.

---

## 1. What was inspected (read-only, 17 Sep 2026)

| Area | File | Findings |
|---|---|---|
| Launcher | `run_server.py` | Port-in-use guard → `import app` (writes `server_error.log` on import failure) → `db.init_db()` + `seed_demo_users()` → `notifications.start_worker()` → `app.run(0.0.0.0:5000)`. |
| Routes/Auth | `app.py` (2809 lines) | **56 `@app.route` decorators.** Session auth via `@login_required(role=...)` + `g.user`. `GOVERNMENT = ("admin","officer")`. Route groups: citizen, officer, admin, command-center (challenges/proposals), university, projects, industry, gov-industry/collaborations, notifications, maps. |
| Data | `db.py` (2833 lines) | Plain sqlite3 → `SimpleNamespace` hydration (dot attributes in templates). `db.init_db()` at line 508 uses `CREATE TABLE IF NOT EXISTS` (additive, non-destructive). |
| Language | `i18n.py` (1824 lines) | `t(key, **kwargs)` with fallback chain ending at `en`. EN + HI are primary and in sync (756/756). Jharkhand tribal languages fall back to HI. |
| Notifications | `notifications.py` | Background daemon thread: 30s cycle, notify window 24h, action due 3 days. Inserts `notifications` rows keyed to a user; titles are i18n keys rendered `t(n.title)`. |
| AI (offline/deterministic) | `ai_engine.py` | `industry_project_fit`, `match_challenge_to_university`, `satellite_screen`, `detect_duplicates`. Honesty-labelled; no online models. |
| UI | `templates/` + `macros.html` + `static/css/style.css` | Reusable primitives: `badge*`, `card`, `grid-2/3/4`, `kpi`, `kpi-grid-inline`, `kpi-hot`, `banner-*`, `btn-*`, `table-scroll`, `timeline`, `cc-section-head`, `field-row`, `crumb`, `topbar`, `conf-pill`. Macros: `urgency_badge`, `severity_meter`, `status_badge`, `challenge_status_badge`, `priority_badge`, `collab_status_badge`, `collab_type_badge`, `funding_status_badge`, `org_type_badge`, `org_verification_badge`, `project_status_badge`, `fit_badge`, `readiness_badge`. |
| Harness | `%TEMP%\opencode\` | `live_smoke.py` (19 checks) and `live_p14_sweep.py` (23 GET-only checks) pass; not part of the repo. |

---

## 2. Findings — 11 analysis points

### 1. Data model today and what Phase 6 must add

Existing tables: `users`, `complaints`, `challenges`, `university_matches`, `teams`, `team_members`, `proposals`, `proposal_logs`, `projects`, `industry_organizations`, `collaboration_requests`, `collaboration_logs`, `project_collaborations`, `notifications`, `duplicate_matches`. Key PK chains: `challenge → teams → proposals → projects → project_collaborations`.

Phase 6 needs **additive** tables only (SQLite `CREATE TABLE IF NOT EXISTS` in `init_db` is already the migration mechanism — no destructive change to the live DB):
- `project_prototypes` — one project → one prototype record: `(project_id, title, description, technology_stack, target_trl, evidence_json, milestones_json, status, submitted_by, reviewed_by, review_comment, reviewed_at, created_at, updated_at)`.
- `prototype_logs` — audit trail mirroring `collaboration_logs`.
- `testing_reports` — `(project_id, prototype_id, report_title, scope, methodology, results_text, verdict, evidence_json, recorded_by, recorded_at)`.
- `pilot_deployments` — `(project_id, pilot_district, pilot_location, start_date, target_end_date, status, metrics_json, report_json, created_by, created_at, updated_at)`.

### 2. Routes / page inventory (56 total) and Phase 6 additions

- Existing relevant: `/project/<id>` (project_details), `/university/...` proposal flow, `/command-center/challenges`, `/command-center/proposals`, `/command-center/industry`, `/command-center/collaborations`, `/industry/projects/<id>`, `/admin/map`, `/officer/map`, `/api/map-data`, `/api/challenge-map-data`.
- Phase 6 additions (mirroring the collaboration pattern, gov/university/industry views):
  - `POST /project/<id>/prototype/submit` — university/faculty, evidence upload.
  - `/command-center/prototypes`, `/command-center/prototypes/<id>` (+ `POST ... /review`).
  - `/command-center/pilots`, `/command-center/pilots/<id>` (+ `POST ... /evaluate`).
  - `/project/<id>/tests` (university records test reports) + gov review entry.
  - Extend `/api/map-data` filter or add `/api/pilot-map-data` if pilots are pinned to districts.

### 3. Dashboard/KPI hooks ALREADY exist (honest zeros)

`db.command_center_kpis()` (db.py:965) already returns `"pilot_projects": 0, "deployed_solutions": 0` and `db.command_center_actions()` (db.py:1012) returns `"projects_overdue": 0, "pilots_needing_evaluation": 0`. `officer_dashboard.html` already renders these KPI cards (lines 30–31) and "future" action rows (lines 101–110). Phase 6 "lights these up" with real counts — no dashboard restructuring needed.

### 4. Readiness & discoverability logic to extend

- `db.project_readiness()` (db.py:2790) currently returns only `academic_ready | industry_connected | not_ready` and is rendered in `project_detail.html` as a readiness badge. Phase 6 must insert `prototype_ready`, `testing_passed`, `pilot_complete`, `deployed` stages into this function (keep existing labels unchanged for lifecycle continuity — the UI is not being redesigned).
- `db.project_discoverable()` (db.py:2357) gates industry on `proposal APPROVED + project status CREATED/ACTIVE`. Decision needed: should a prototype-approved project remain visible but mark "Prototype Ready" (recommended, keeps investors engaged) or hide until pilot? Recommend: always visible, label advances.
- `i18n` readiness keys exist: `ind_readiness_academic`, `ind_readiness_connected`, `readiness_not_ready` (EN+HI). Add `ind_readiness_prototype`, `ind_readiness_testing`, `ind_readiness_pilot`, `ind_readiness_deployed` in both dicts.

### 5. Permission model & PII rules

- Roles: `citizen, officer, admin, university, faculty, student, industry`. No new role needed in Phase 6.
- Prototype submission: `faculty`/`student` team members of the owning university (same gate as `list_projects_for_user`).
- Review/approval: `GOVERNMENT` only (matches `@login_required(role=GOVERNMENT)` used by command-center routes).
- **PII rule to preserve:** `list_discoverable_projects()` (db.py:2376) deliberately strips student/citizen PII for industry — the "industry view" never sees phone/email of students. Prototype/testing evidence that industries see must follow the same rule (evidence object reviewed by gov before it becomes industry-visible, or evidence shown to industry only with a gov-set "public to partners" flag).

### 6. Notification pattern (reuse)

`notifications.py` is a daemon worker that detects state changes/overdue SLA and inserts `notifications` rows. Phase 6 is **event-driven**, not worker-driven:
- `add_notification(...)` calls already exist inline in db.py actions (e.g. collaboration submit, interest, review).
- Add new kinds: `prototype_submitted` (→ gov), `prototype_approved` (→ team + connected industry org), `prototype_revision_requested` (→ team), `testing_passed` (→ gov + industry), `pilot_started` / `pilot_evaluation_due` (→ gov + industry + team).
- Add matching i18n title keys in EN and HI. Optionally extend the worker for a `pilot_evaluation_due` SLA (reuse `ACTION_DUE_DAYS` style constant).

### 7. i18n rules (parity is enforced by convention)

- Add all new Phase 6 keys to BOTH the EN block (~line 556+) and the corresponding HI block (~line 1347+) — EN/HI parity is a project invariant; a key missing from one dict silently falls back to EN, which breaks the hi locale.
- Status keys follow the existing pattern: `prototype_status_SUBMITTED` → "Submitted for review", etc.
- Range/district labels already available via `dist_label()` / `cat_label()` — reuse for pilot location fields.

### 8. Reusable architecture patterns (copy, don't re-invent)

Every Phase 4/5 workflow follows a strict, copyable pattern:
1. Status constants + `_SQL_IN`/state-machine check that raises `ValueError` on invalid transition (see `express_interest`, collaboration transitions).
2. A `*_logs` table for audit of every state change; `add_*_log` writes on each mutation.
3. `hydrate_*` helper returning `SimpleNamespace` with `with_relations` flag; relations fetched in one place.
4. KPI counter functions (`count_*`) feeding `command_center_kpis/actions`.
5. Macros badge per status (`collab_status_badge`, `project_status_badge`) — add `prototype_status_badge`, `testing_status_badge`, `pilot_status_badge` to `macros.html` the same way.
6. `t()` for every user-visible string; `dist_label/cat_label` for enum text.

Phase 6 should implement prototype/testing/pilot **exactly** in this shape. This keeps the live sweep green and the codebase uniform.

### 9. DB migration mechanics (safe, additive)

`init_db()` runs `CREATE TABLE IF NOT EXISTS` on every start; adding new Phase 6 tables there does **not** touch existing rows. No ALTERs needed. Schema evolution is effectively "add table + hydrate + helpers". The live DB currently has: 14 complaints, 4 challenges, 2 teams, 2 proposals, 1 project, 3 industry orgs, collaboration requests + project collaborations, 19 notifications — all preserved under an additive change.

### 10. Security notes

- Uploads: `MAX_CONTENT_LENGTH = 50MB` already set; evidence upload control exists (`data-evidence-controls` in `main.js`). Phase 6 evidence should enforce allow-listed extensions/size per file and an upload count cap.
- No CSRF tokens on the session-based POST forms today (existing app-wide posture; not introduced by Phase 6, but flagging for the record).
- Prototype/testing evidence uploaded by team members must not be rendered to `industry` until gov-approved-to-share (PII rule, point 5).
- All Phase 6 POST routes must be `@login_required(role=...)` with the exact `GOVERNMENT`/university membership gates; do not trust IDs in URLs (check `project.university_id` / `team_members.status='ACTIVE'` like `project_details` does at app.py:1845).
- Validation mirrors `create_project_from_proposal`: only permit prototype for a project whose proposal is `APPROVED`; only one prototype per project.

### 11. Proposed Phase 6 workflow (maps to the objective)

```
Project (done, Phase 4)
  → compute readiness: Academic Solution Ready / Industry Collaboration Connected

Prototype  (new)
  team submits prototype → gov review → APPROVED / REVISION_REQUESTED / REJECTED
  readiness advances: Prototype Ready (industry label when approved)

Testing (new)
  team records test plan + evidence → verdict PASSED / FAILED / IN_REVIEW
  readiness advances: Under Testing → Testing Passed

Pilot (new)
  gov opens pilot deployment (district/location, window) → team runs → gov evaluation
  readiness advances: Pilot Running → Pilot Completed & Evaluated

Deployment (new)
  gov records deployment (location, date, evidence) → DEPLOYED
  readiness advances: Deployed & Live; KPI deployed_solutions counts 1
```

---

## 3. Recommended implementation plan (when green-lit)

Order matters so the live sweep never regresses and the server restarts exactly once:

1. **db.py** — add 4 tables + status constants + `add_prototype_log`/hydrate helpers mirroring `collaboration_logs`/`hydrate_collaboration`; extend `project_readiness()`; extend `command_center_kpis/actions` to real counts for prototype/pilot/deployed; add `list_prototypes_for_*`, `list_testing_reports`, `list_pilot_deployments`, `list_discoverable_projects` extension (PII-safe), and `get_connected_collaboration`-style helpers.
2. **i18n.py** — one commit-worthy block: all Phase 6 keys in EN **and** HI (readiness labels, statuses, action labels, notification titles, page titles).
3. **app.py** — new routes per point 2 (prototype submit/review, tests, pilots, evaluate) reusing `_portal_back`, `_uni_context`, `g.user`, `flash` patterns.
4. **templates/** — `gov_prototypes.html/details`, `gov_pilots.html/details`, prototype submit form on university side, testing evidence form; extend `project_detail.html` section with stage badges + timeline (reuse `timeline` CSS); extend `gov_collaboration_detail.html`? No — separate pages. New macros in `macros.html`.
5. **notifications.py** — inline `add_notification` calls inside new db.py action functions for the new kinds (+ optional worker SLA for pilot evaluation due).
6. **CSS** — expect ~0–10 new classes; reuse `badge`, `card`, `timeline`, `kpi-grid-inline`, `table-scroll`, `btn-*`, `conf-pill`.
7. **Verification** — extend `live_smoke.py` (current 19) + `live_p14_sweep.py` (current 23) with GET-only checks for the new pages; run full suite local + via ngrok; confirm no `server_error.log`.
8. **Restart/deploy exactly once** when ready: stop Flask pid, restart `run_server.py` (ngrok tunnel/URL unchanged), re-run remote harness.

**No AI additions** unless a demonstrated requirement is identified (none found in inspection; every candidate can be done with deterministic rules + honest zero states, matching the app's existing honesty stance).

---

## 4. Clarification questions (need answers before implementation)

1. **Prototype evidence** — what formats/limits? Photos + zip of deliverables + milestone list? Size caps beyond the existing 50MB request limit?
2. **Approval chain** — industry/government only (single gov review, like collaborations), or university HoD first then gov?
3. **Industry visibility** — should industry automatically see approved prototype/testing evidence (stripped of PII), or only what gov flags "share with partners"?
4. **Pilot scope** — one pilot location per project at a time, or multiple districts? Should pilots appear on `/admin/map` with pins?
5. **Testing rigor** — lightweight (faculty uploads evidence + PASS/FAIL verdict) or a structured test-plan form (scope, methodology, results, metric fields)?
6. **Citizen "Fixed & Verified" gallery** — tie to Deployment (citizens see deployed solutions) in Phase 6, or keep gallery out of scope?
7. **Funding tie-in** — should prototype approval post a funding line on the existing `project_collaborations` (representation only, like today), or stay separate?
8. **What is "Deployed"?** — photo + district + date by gov, or need more fields (cost, agency, uptime/SLA tracking)?
9. **i18n scope** — EN + HI only (current parity target), or extend Phase 6 keys to the Jharkhand tribal language entries too?
10. **AI** — confirm none wanted for phase 6 (no demonstrated requirement found; deterministic only).

---

## 5. Explicitly out of scope (unchanged from constraints)

- No AI features unless a demonstrated requirement emerges from the clarifications.
- No UI redesign; existing badges/cards/timelines reused as-is.
- No functionality outside Project → Prototype → Testing → Pilot → Deployment.
- No real payments/transfers (funding remains representation-only).
- No changes to auth model, no new roles, no destructive DB migrations.