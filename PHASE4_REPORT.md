# Phase 4 — Teams, Proposals & Projects

Delivered: team formation and proposal lifecycle after government validation and
university acceptance, through government review and project creation, with
server-side authorization, privacy rules and EN/HI localization.

## Lifecycle

```
Official Challenge
  -> University accepts (ACCEPTED match)
     -> Team created (team creation only for ACCEPTED matches)
        -> Faculty/students join or are added
           -> Proposal created (DRAFT)
              -> Submitted (SUBMITTED -> UNDER_REVIEW)
                 -> Government verdict
                    -> APPROVED       -> Project created (one per proposal)
                    -> REJECTED
                    -> REVISION_REQUESTED -> member edits -> resubmit (UNDER_REVIEW again)
```

## Role matrix (enforced server-side, never trusts URL/form IDs)

| Action | university (admin) | faculty / student | admin / officer | citizen |
|---|---|---|---|---|
| Create team | own institution's ACCEPTED match only | no | no | no |
| View team | own institution | own institution (members full; non-members may join) | read-only | no |
| Add / remove member | own institution | no | no | no |
| Self-join team | n/a | own institution | no | no |
| Create / edit / submit proposal | own institution admin or active team member | active team member only | no | no |
| Review / approve / reject | no | no | yes | no |
| Create project | no | no | yes (from APPROVED proposal only) | no |
| View project | own institution | own institution members | yes | no |

- Cross-institution and citizen access attempts redirect (HTTP 302) with a flash
  message; no data is exposed.
- Government reviewers cannot open university-scoped creation forms.

## Routes

- `GET  /university/teams`
- `GET/POST /university/challenges/<match_id>/team/new`
- `GET  /university/teams/<team_id>`
- `POST /university/teams/<team_id>/members/add`
- `POST /university/teams/<team_id>/members/<user_id>/remove`
- `POST /university/teams/<team_id>/join`
- `GET/POST /university/teams/<team_id>/proposals/new`
- `GET  /university/proposals/<proposal_id>`
- `POST /university/proposals/<proposal_id>/edit`
- `POST /university/proposals/<proposal_id>/submit`
- `GET  /command-center/proposals` (gov review board)
- `POST /command-center/proposals/<proposal_id>/review`
- `POST /command-center/proposals/<proposal_id>/verdict` (APPROVED / REJECTED / REVISION_REQUESTED)
- `POST /command-center/proposals/<proposal_id>/approve`
- `POST /command-center/proposals/<proposal_id>/reject`
- `POST /command-center/proposals/<proposal_id>/revision`
- `POST /command-center/proposals/<proposal_id>/create-project`
- `GET  /project/<project_id>`

## Security

- Every team/proposal action re-resolves the institution from the session user
  (`_uni_context`) and re-checks ownership; IDs from the client are not trusted.
- Team guard: owning university admin, government readers, or same-institution
  faculty/student. Proposal guard: government, owning university admin, or an
  ACTIVE member of the proposing team.
- Project creation requires an APPROVED proposal and rejects a second conversion.

## Privacy

- Citizens are blocked from all Phase 4 team/proposal/project pages.
- No citizen PII, coordinate or reporter identity is rendered to non-government
  users; government sees citizen reports only within its own command-centre views.
- No in-app notification feed: the audit trail is `proposal_logs` +
  `challenge_logs` timelines.

## Localization

- `i18n.py` `t()` used throughout; Phase 4 keys added in English and Hindi, and
  status badges resolve via `team_status_*`, `team_role_*`, `proposal_status_*`,
  `project_status_*`.
- Verified all reconstructed/updated pages render under both `en` and `hi`.

## Database

- New tables/helpers for teams, team_members, proposals, proposal_logs, projects
  and their hydrators, plus `challenge_lifecycle` / `attach_lifecycle` snapshots
  used by the Command Center and university portal.
- `hydrate_team` / `hydrate_proposal` / `hydrate_project` nest related objects
  without recursion; `list_team_members` includes department (COALESCE) and course.

## Tests

Run on throwaway copies of `jsamadhan.db`; the live DB is never modified.

- Data-level workflow smoke — OK.
- UI role sweep — every page returns 200 for allowed roles and 302 for blocked
  roles; no 500s.
- HTTP end-to-end lifecycle + authorization — 21/21 passed, covering: team gate
  (ACCEPTED-only, not-owned RECOMMENDED rejected), member add, self-join, proposal
  DRAFT -> submit -> review -> revision -> edit/resubmit -> approve, project
  creation with duplicate-conversion guard, cross-institution/citizen/government
  negatives, challenge-detail lifecycle surfacing, and proposal timeline.
- Hindi render check for all reconstructed/updated pages — OK.

## Recovery note

Three templates (`university_dashboard.html`, `faculty_dashboard.html`,
`challenge_detail.html`) were accidentally truncated by a script during
development and were untracked in git. They were reconstructed from route
contexts, i18n keys, macros and sibling templates, and re-verified (EN + HI).

## Deployment

Phase 4 is merged into the working tree and tested, but the live ngrok server was
restarted only after all tests passed. No git commit/push was performed.
