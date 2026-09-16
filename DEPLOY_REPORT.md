# Phase 5 Deployment Report

## Summary
The Phase 5 release (industry collaboration + funding) is now **deployed and live** on the existing
Flask 5000 server and the existing permanent ngrok domain. The previously-500
`/industry/collaborations/<id>` page is verified fixed.

## 1. Processes before / after

| Item | Before | After |
|---|---|---|
| Flask server PID | **20860** (`pythonw.exe run_server.py`) | **20956** (`pythonw.exe run_server.py`) |
| ngrok PID | **17144** | **17144** — **unchanged** |
| Public URL | `https://majority-bolt-rentable.ngrok-free.dev` | **unchanged** (confirmed responding) |
| Port 5000 | listening | listening (re-opened on restart) |

No ngrok process was touched: the flask server was stopped and restarted while the ngrok tunnel
kept running and immediately resumed serving the new process.

## 2. Restart method
Used the existing entry point unchanged: `pythonw.exe run_server.py` (the file `start.bat` /
`tunnel_autostart.ps1` invoke). `run_server.py` performs `app.db.init_db()`,
`app.seed_demo_users()` (idempotent), starts the `notifications` background worker, then
`app.run(0.0.0.0:5000)`. `tunnel_autostart.ps1` was NOT run (it would have killed ngrok).

## 3. Migration / schema verification (`init_db` ran, read-only probe of live DB)

Phase 5 tables present after restart:
`industry_organizations`, `collaboration_requests`, `collaboration_logs`,
`project_collaborations`, `notifications` — **all created**.

## 4. Demo seed verification (idempotent, no Phase 1–4 duplication)

Phase 1–4 counts before → after restart:

| Table | Before | After | Change |
|---|---|---|---|
| users | 18 | 21 | +3 (the 3 industry demo org accounts — intended) |
| complaints | 14 | 14 | — |
| duplicate_matches | 0 | 0 | — |
| challenges | 4 | 4 | — |
| challenge_university_matches | 8 | 8 | — |
| universities | 5 | 5 | — |
| faculty | 3 | 3 | — |
| students | 4 | 4 | — |
| teams | 2 | 2 | — |
| proposals | 2 | 2 | — |
| projects | 1 | 1 | — |

**No Phase 1–4 data was duplicated.** All seed functions are guarded (users empty → skip;
`_seed_phase4_demo` guarded by `teams` count; `_seed_phase5_demo` guarded by
`industry_organizations` count), so a further restart would not duplicate either.

## 5. Three Phase 5 demo organizations (live DB)

| Name | Type | Verification |
|---|---|---|
| Vidyut Infra & Civicworks Pvt Ltd | INDUSTRY | **VERIFIED** |
| AarogyaSparsh Health Solutions | STARTUP | **VERIFIED** |
| KisanTech Agri Solutions | MSME | **PENDING** |

Request states: req #1 `UNDER_REVIEW` (GRANT ₹250,000), req #2 `ACCEPTED` (CSR ₹800,000).
Project collaboration: 1 row `CONNECTED` / `PROPOSED` ₹800,000. Notifications: 19.

## 6. Non-mutating local smoke checks (live server, 127.0.0.1:5000)

Landing, officer login+dashboard, gov `/command-center/industry`, gov
`/command-center/collaborations`, gov collaboration detail (UNDER_REVIEW and ACCEPTED+funding),
citizen dashboard, university dashboard + challenges, industry dashboard, industry project
discovery, industry project detail, industry collaborations list, **industry collaboration detail
(was 500!)**, Phase 5 Hindi pages (industry dashboard/projects, gov-industry).
**19/19 PASS.**

## 7. Verification through the public ngrok URL

The exact same 19-check smoke suite run against
`https://majority-bolt-rentable.ngrok-free.dev` (with `ngrok-skip-browser-warning: 1`):
**19/19 PASS** — including the industry collaboration detail page.

## 8. Fix confirmation (item 9)

`/industry/collaborations/1` (the page that previously threw
`collab.project.university` → `UndefinedError` 500 before the
`hydrate_collaboration(with_relations=True)` change) now returns **HTTP 200** both locally and via
ngrok. No `UndefinedError` / "Internal Server Error" markers in the response.

## 9. Phase 1–4 regression (live server)

GET-only sweep over Phase 1–4 routes: login, register, `/api/map-data`, citizen dashboard,
my complaints, account, officer complaint detail, command-center, officer map, admin dashboard,
admin command-center, admin map, university dashboard/challenges/teams/profile/expertise, faculty
dashboard, student dashboard, challenge details 1–4. **23/23 PASS.**

## 10. Errors
- `server_error.log` — **not created** (clean startup).
- No tracebacks observed in any of the smoke responses.
- The only issues found during deployment were two **test-harness** mistakes (a faulty `login()`
  helper that never posted, and two wrong URL paths in the sweep script); neither was an app error.
  Harness scripts live under the temp dir, not the repo.

## 11. Files changed during deployment
**None.** No application file was modified during the deployment. (All verification scripts were
created/edited under `%TEMP%\opencode`. The `hydrate_collaboration` fix was already in `db.py`
before deployment began.)

## 12. SIH demo readiness
**Yes — ready.** App is live on the existing ngrok URL with all Phase 1–5 functionality,
verified demo data, and the collaboration-detail 500 fixed.
Server will not be restarted again unless explicitly instructed.

## Demo login hints (Phase 5)
- Industry (verified): `vidyut@jsamadhan.demo` / `industry123` · `aarogya@jsamadhan.demo` / `industry123`
- Industry (pending verification): `kisantech@jsamadhan.demo` / `industry123`