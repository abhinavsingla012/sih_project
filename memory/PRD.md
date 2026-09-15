# Samanvay — SIH26129

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

Known preview limitation: legacy clients missing Fetch Metadata cannot reliably distinguish proxy-rewritten neighboring origins. Scheduled cron secret source mismatch still unresolved; automatic recovery unproven. Architecture/readme/six diagrams/jury guide remain backlog. Identifier mappings are embedded, not populated as a separate projection. Retry budget is four total attempts; no force-complete bypass. No backend changes in the UI redesign milestone.
