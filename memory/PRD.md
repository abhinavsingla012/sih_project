# Sampark — SIH26129

## Approved objective
Government interoperability and service orchestration prototype for Maharashtra. We do not replace government systems; we make them work together. Preserve React/FastAPI/MongoDB, existing design and implementation.

## Core acceptance journey
One citizen application and correlated APP/TXN IDs across Citizen Registry (JSON/API key), Skill Development (JSON/scoped bearer), State Treasury (form/XML/HMAC). Demonstrate transformations, identifier correlation, Redis Streams propagation, durable workflow, timeout-after-commit reconciliation without duplicate business payments, real audited 403 policy denial, and unified citizen status.

## Explicit simulation boundary
Departments, identity, citizens and payments are SIMULATED. HTTP calls, MongoDB persistence, Redis at-least-once events and authorization are real. No production-readiness or exactly-once event claim.

## Continuation milestone
Restore usable existing prototype, repair frontend TypeScript compilation without redesign, verify backend core flows, then request frontend testing permission. No new external integration or API key required.

## Current observations
- Mounted branch is conflict_150926_2011, unlike handoff's emergent. No git writes performed.
- Protected frontend/backend .env URL values left untouched.
- setup_local originally restored only secrets; operational settings were missing after workspace restore. Extended idempotent setup to require runtime URLs from environment and fill non-secret defaults.
- Restored supervised Redis and event consumer configuration using existing restore_runtime.py.
- Added type declarations for existing JSX UI primitives and corrected readonly navigation type. Production build and subsequent frontend browser checks passed.

## Latest approved scope: simple government-inspired frontend
User requested Indian/Maharashtra government styling, then emphasized a normal clean interface without complexity: backend functionality matters most. Applied a shared navy-blue, white, green and restrained saffron theme, system typography, Marathi brand caption, and simpler sign-in department list. Existing routing, forms, actions and backend logic are unchanged. No official emblems or claim of endorsement; visible prototype/simulation disclaimers remain. No new external integration.

Changed frontend files: App.js, components/shared/Common.tsx, pages/LoginPage.tsx, new government-theme.css. JavaScript/TypeScript lint and production build passed. After explicit user approval, frontend testing agent verified desktop1920x800 and mobile390x844 login, session reload/logout/relogin, operations navigation, transaction tabs and policy probe, citizen submission and notifications. No horizontal overflow reported. Main-agent final screenshot review also showed populated operations dashboard with overflow [] at both required viewports and clean login styling. No backend changes were needed for the redesign.

## Verification and unfinished work
Initial backend suite reported 74 passing checks for core success/recovery/authorization, but omitted Origin on session requests and was not browser verification. User then reported actual login ORIGIN_DENIED. Browser reproduction confirmed ingress rewrites public Origin to the project's internal cluster alias. Fixed shared exact configured origin allowlist and added Fetch Metadata guard for cross-origin login; final targeted backend suite reported 17 passes. After the UI redesign, the frontend testing agent verified the original sign-in failure is resolved through actual browser clicks at the user's exact URL on desktop and mobile. Session reload and logout/relogin also passed.

## 2026-09-15 — Runtime self-healing and scheduled recovery (DONE, tested)
User-reported bugs: login HTTP 503 "Sign-in protection is temporarily unavailable" and a submitted application frozen at SUBMITTED 0/4. Root cause: after pod resume the fresh image lacks the apt `redis-server` binary when supervisor starts `samanvay-redis` (execvp FileNotFoundError → FATAL/STOPPED); the event worker crashed at its first `ensure_group()`; login rate limiting is Redis-backed and fails closed.
Fixes: `backend/run_redis.py` polls for the binary, installs redis-server non-interactively if absent, stops a stray postinst instance and execs by absolute path; `backend/event_worker.py` retries Redis at startup instead of exiting; `scripts/samanvay-supervisor.conf` adds startsecs/startretries=200; `scripts/restore_runtime.py` also runs setup_local and starts the services. Scheduled recovery: `setup_local.py` now stores `WEBHOOK_CRON_SECRET` in `backend/.env` (the only file the platform dispatcher reads) and removes it from `.env.local`; cron ticks now return 202 (were 401).
Verified by backend testing agent (iteration_5: 14/14 new resilience tests + 74/74 regression + 17/17 auth): services RUNNING, login 200, new applications COMPLETED 4/4 with exactly one payment, worker survives Redis stop/start and Redis-down startup, dispatcher 202 idempotent / wrong bearer 401, setup idempotent. The user's originally stuck TXN-C6080D53F2BD (RETRY_SCHEDULED after a CONNECTION_FAILED during the backend restart) was recovered automatically by the maintenance dispatcher once due → COMPLETED 4/4, one payment. Operational note: if `supervisorctl status` ever lacks samanvay-* after a resume, run `python /app/scripts/restore_runtime.py`.

## 2026-09-15 — Jury README (DONE)
`/app/README.md` rewritten (≈550 lines): capability matrix, six Mermaid diagrams (system context, success sequence, workflow state machine, outbox→Redis Streams propagation, timeout-after-commit reconciliation, policy/consent decision), interoperability model (connectors, canonical v1, identifier correlation), reliability and security tables, a 12-minute step-by-step jury demo script with timings/click targets/talking points (UI labels verified against the frontend source), stage-failure playbook and expected jury Q&A, local setup and test commands, API reference, repo layout, nine architecture decisions and explicit non-claims. All six diagrams were rendered with Mermaid 11 in a browser (one syntax error fixed) — no application code changed.

## 2026-09-15 — Expired-session handling (DONE, tested)
User saw "services may be temporarily unavailable". Root cause: 4h session JWT expired while the tab stayed open; every API call returned 401 but the SPA kept its in-memory user and showed the generic ErrorState / hung on Loading. Fix (frontend only): AuthProvider axios interceptor on 401 (except /auth/login) clears cache + user → Guard redirects to /login with toast "Your session has expired. Please sign in again."; QueryClient no longer retries 4xx; ErrorState shows the real API message or HTTP status. Frontend testing agent iteration_6: 8/8 scenarios passed (share-link landing, expiry inside open tab for operator and citizen, server-side revocation, specific 503/500 messages, logout/invalid password/deep-link regressions, desktop + mobile).

## 2026-09-15 — 12-hour demo sessions (DONE, tested)
User chose 12 h for all roles. `SESSION_HOURS` (default 12, set by setup_local.py in .env.local, validated 0–168 h at startup) now drives both the JWT `exp` and both cookie `max_age` values in backend/modules/auth.py so they cannot drift. Verified: login sets `Max-Age=43200`, decoded JWT lifetime 12.0 h; auth regression suite 17/17 passed. README security table, env list and demo pre-checks updated.

## 2026-09-15 — Embedded-frame sign-in fix (DONE, tested)
User: "not able to login, it says session expired". Access log: login 200 → next GET 401. Reproduced by embedding the app in a cross-site iframe (preview/portal panel): SameSite=Lax cookies were not sent from the frame. Fix: session + CSRF cookies now `SameSite=None; Secure` (protection kept via exact Origin allow-list, Fetch-Metadata login guard, session-bound CSRF); frontend login() verifies the cookie round-trip with /auth/me and, if the browser blocks it, shows "did not keep the sign-in cookie… open in a new tab" with an **Open in a new tab** link. Testing agent iteration_7: 21/21 frontend assertions (embedded citizen/operator login, navigation and a mutation from inside the frame, cookie attributes, top-level regressions desktop+mobile, COOKIE_BLOCKED UX, expired-session redirect) + 17/17 auth security suite. README security table and stage playbook updated.

## 2026-09-15 — Officer Review Inbox / human-in-the-loop (DONE, tested)
Workflow pauses at stage 3 (`AWAITING_REVIEW`, app `UNDER_REVIEW`) for manual-review applications (citizen submissions default manual; demo journeys choose Officer decides / Auto-sanction). Officials decide from `/operations/reviews` (pending/decided tabs) or the case page `ReviewPanel` (remarks ≥5 chars; Sanction → READY → approval + treasury run; Reject → REJECTED, treasury never runs). Citizens see a pending notice and later the officer of record + remarks; operators/auditors see read-only notices. `GET /api/reviews?state=`, `POST /api/reviews/{key}/decision` (official only; 403/404/409/422 paths). Login page gained a Department officer preset. Verified iteration_8: 12/12 backend + all UI flows incl. mobile.

## 2026-09-15 — Multi-scheme catalogue, department officers, seeded history (DONE, tested)
User choices: 3 schemes (Skill training benefit ₹15k / Post-matric scholarship ₹25k / Drip irrigation subsidy ₹40k), one officer per department (official@ skill, sjsa@ social_justice, agri@ agriculture), ~100 seeded applications.
- `definitions.py`: `SCHEMES` catalogue (unit, department, amount, age band, option list), 18 `DISTRICTS`, `stage_templates()` sets stage systems per scheme; realistic connector branding (State Resident Registry / Line department systems / State Treasury (DBT)); purpose renamed `BENEFIT_ELIGIBILITY`, field `scheme.optionCode`.
- Models: `CreateApplication{service_code, option_code, district}` validated against the catalogue (422 UNKNOWN_SERVICE / INVALID_OPTION / INVALID_DISTRICT); `ApplicationView` adds service_name/option_label/department/unit. `DemoJourney` adds service_code. `GET /api/services` returns the catalogue; `GET /api/applications?service_code=`; overview `by_scheme[]`.
- Officers: users carry `unit`/`unit_name`; `visibility()` scopes officials to `{'departments':'eligibility','unit':…}` → other departments' cases are 404.
- Mock eligibility takes scheme_code/option_code and applies the scheme age band; treasury accepts any catalogue amount.
- `modules/dataset.py` seeds ~109 internally consistent, backdated (≤60 d) applications with events/audit/evidence/mappings + matching mock ledgers: ~70 completed, 12 in inboxes (4 per unit), 11 rejected (ineligible/officer), exception backlog (4 retry scheduled, 3 reconciling w/ committed payment, 3 needs investigation, 3 policy blocked). Aditi/Rohan get a small personal history. Runs on first startup; `python seed_dataset.py --reset` or operator `POST /api/demo/dataset/reset` (Overview → Regenerate demo history) wipes and regenerates. Seeded cases are actionable through the real workflow (verified: sanction → COMPLETED 1 payment; reconciling retry → RECONCILED).
- Frontend: citizen service catalogue cards, scheme-aware NewApplicationPage (`?scheme=`), scheme filter on transactions, scheme portfolio table on overview, scheme select in demo dialog, scheme labels in tables/inbox/case page. README rewritten in the affected sections (catalogue, demo script, accounts, seed, API).
Verified iteration_9: 14/14 multi-scheme pytest (`backend/tests/test_multi_scheme.py`), 12/12 review, 17/17 auth; all frontend flows incl. 390px.

## 2026-09-16 — Brand rename + officer login picker (DONE)
- Product renamed **Sampark (संपर्क)** in all user-facing text (title, brand mark, login, overview core, footer, README, PRD). Internal codenames unchanged on purpose: cookies `samanvay_session`/`samanvay_csrf`, Redis stream `samanvay:events`/group `samanvay-workflows`, supervisor programs `samanvay-redis`/`samanvay-events`, JWT aud/iss.
- User report "citizen request shows in operations but not the department manager's inbox": backend routing verified correct (unit-scoped); root cause was the login page only offering the Skill Development officer. Login "Department officer" preset now opens a picker for Skill / Social Justice / Agriculture (`officer-<unit>` testids); pending notices name the deciding department; operator inbox rows show "<Department> inbox".

## 2026-09-16 — Stale views after officer approval (FIXED, tested iteration_10)
User report: after sanction the citizen got the notification but citizen/operator transaction lists kept the old status. Backend was correct; causes were frontend staleness: React Query `staleTime 60s` + `refetchOnWindowFocus:false` (background tabs are timer-throttled by the browser) and cookie sessions shared across tabs (login as another role replaced the tab's session silently). Fix: `index.js` → `staleTime 0`, `refetchOnWindowFocus`, `refetchOnReconnect`; `AuthProvider` re-validates `/auth/me` on focus/visibilitychange → invalidates all queries, or if the session user changed, toast "Signed in as X from another tab · switching workspace" + cache clear + role redirect. Verified: list flips to Completed ≤3 s live, ≤1.5 s after focus; cross-tab switch; logout-elsewhere → login.

## 2026-09-16 — Readable typography + lighter demo data (DONE, tested iteration_11)
User: "too stuffed", "fix the typography… easy to use by normal people". Design agent guidelines in `/app/design_guidelines.json` applied:
- Fonts: Plus Jakarta Sans (body/headings), Noto Sans Devanagari (brand caption), JetBrains Mono (IDs). `scripts/lift_typography.py` remapped every hard-coded px size in `App.css`/`government-theme.css` (7–11px → 12–14px; body 16px; H1 28/24px; H2 20px; badges/eyebrows/table headings 12px). Readability layer appended to `government-theme.css`: buttons ≥40px (44px mobile), inputs ≥44px, focus-visible outlines, 64px list rows, 24px card padding, scrollable sidebar, single-column login presets.
- Data: seed reduced to 36 apps (16 completed, 6 pending = 2 per officer, 4 rejected, 5 exceptions) + Aditi 3 / Rohan 2; 24 synthetic people. Citizen list lost search/status filters (heading "My applications" instead); operator keeps filters. Overview recent = 5.
- Verified: no text < 12px on 12 routes at 1920 and 390; no horizontal overflow; e2e submit → sanction still works; backend suites green.

## Backlog
- P2: Verify timeout-after-commit recovery via the scheduled maintenance path creates exactly one treasury payment (manual retry path already verified).
- P2: Verify the policy probe calls the real service data-access endpoint and yields an audited 403 (browser flow verified; backend contract test pending).
- P2: Per-scheme eligibility inputs beyond age (income certificate, landholding) in the mock line department.
- P3: Identifier mappings as a separate projection; retry budget/force-complete policy review.

Known preview limitation: legacy clients missing Fetch Metadata cannot reliably distinguish proxy-rewritten neighboring origins. Scheduled cron secret mismatch RESOLVED 2026-09-15 (see above). Architecture/readme/six diagrams/jury guide remain backlog. Identifier mappings are embedded, not populated as a separate projection. Retry budget is four total attempts; no force-complete bypass. No backend changes in the UI redesign milestone.
