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
- Added type declarations for existing JSX UI primitives and corrected readonly navigation type. Build/test results pending.

## Verification and unfinished work
Backend testing pending: success, failure, reconciliation, ledger count, real policy denial, ownership/RBAC/CSRF, consent revocation, idempotency, worker restart and Redis outage recovery. Frontend visual/functionality testing pending permission. Scheduled cron secret source mismatch still unresolved; automatic recovery unproven. Architecture/readme/six diagrams/jury guide remain backlog. Identifier mappings are embedded, not populated as a separate projection. Retry budget is four total attempts; no force-complete bypass.
