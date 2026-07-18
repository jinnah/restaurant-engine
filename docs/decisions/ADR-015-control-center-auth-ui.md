# ADR-015: Control-Center Auth UI

- **Status:** Accepted
- **Date:** 2026-07-18
- **Deciders:** Product owner, principal architect

## Context

M2E gives the control center its first real behavior: signing in against
the M2A session API, accepting M2D invitations, and redeeming M2D
password-reset tokens. Until now the SPA was the M1B placeholder shell
with no data fetching, no auth state, and no development-time path to the
API. The approved architecture went through a proposal, a corrections
addendum, and a final source-verified delta — the binding decisions are
recorded here.

M2E is deliberately frontend-only: no backend, contract, migration, or
generated-client change. The generated facade (ADR-009) is consumed
as-is.

## Decisions

_Skeleton — each decision is elaborated as its implementation lands; the
final revision of this ADR accompanies the last M2E commit._

1. **Same-origin development proxy; no CORS surface.**
2. **TanStack Query is the only session store** (exact pin `5.101.2`).
3. **Authoritative session establishment after login** (login response is
   never cached as the session).
4. **CSRF token lives only in the session cache**, read at call time.
5. **Paste-only token handling** for invitations and resets.
6. **Dual invitation-acceptance flows** (guest and authenticated),
   with an irreversible post-acceptance refresh state.
7. **Password-reset success clears all cached authenticated state.**
8. **Safe internal-only `next` redirects.**
9. **React Hook Form and Zod remain deferred** to the first complex
   editing workflow (expected M3); M2E uses controlled accessible forms.
10. **Styling stays app-local** (CSS modules + existing custom
    properties); no `admin-ui`/`design-tokens` packages yet.
11. **Live browser verification is a separately authorized step**
    (fresh dev-DB backup → verify → migrate → live proxy/browser smoke).

## Consequences

_To be completed with the final revision._
