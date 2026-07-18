# ADR-015: Control-Center Auth UI

- **Status:** Accepted
- **Date:** 2026-07-18
- **Deciders:** Product owner, principal architect

## Context

M2E gives the control center its first real behavior: signing in against
the M2A session API, accepting M2D invitations (both as a new user and
as an authenticated multi-business user), and redeeming M2D
password-reset tokens. Until now the SPA was the M1B placeholder shell
with no data fetching, no auth state, and no development-time path to
the API. The approved architecture went through a proposal, a
corrections addendum, and a final source-verified delta; the binding
decisions are recorded here.

M2E is deliberately frontend-only: no backend, contract, migration, or
generated-client change. The generated facade (ADR-009) is consumed
as-is, through an injectable provider — never deep imports, never a
parallel raw-fetch client.

## Decisions

### 1. Same-origin development proxy; no CORS surface

The Vite dev server proxies `/api` to `http://127.0.0.1:8000` with
`changeOrigin: false`. The invariant, verified against backend source
before selection: the UI is used at exactly `http://localhost:5173`;
every client call is an origin-relative `/api/...` request (facade
`baseUrl: ''`); the forwarded `Host` stays `localhost:5173`, which
`KnownHostGuard` accepts outside production after port-stripping
normalization; the browser `Origin` stays `http://localhost:5173`,
which the backend's trusted-origins default accepts; the session cookie
is first-party throughout. `http://127.0.0.1:5173` is a different
origin and is unsupported. Production serves the SPA and API behind one
reverse-proxy origin the same way. Consequently the M1C-deferred CORS
decision resolves as: **no CORS middleware exists, anywhere** — there
is no cross-origin surface to configure.

### 2. TanStack Query (exact pin 5.101.2) is the only session store

One cache entry (`['session']`) holds exactly two value shapes:
`{ kind: 'authenticated', session: SessionView, csrfToken }` or
`{ kind: 'anonymous' }`. The expected `GET /auth/session` 401 is a
_value_ (anonymous); unexpected bootstrap failures remain retryable
query errors and are never cached as session values. The query pins
`staleTime: Infinity`: revalidation is always explicit (login
establishment, logout, user-triggered retry), so clearing state can
never race an automatic mount refetch into a loop. No second
independently writable session or CSRF store exists. React peer range
`^18 || ^19` is satisfied by the workspace's exact React 19.2.7.

### 3. Authoritative session establishment after login

`POST /auth/login` returns the lean `SessionResponse`; the enriched
`SessionView` comes only from `GET /auth/session`. The login response
is therefore never cast or cached as the session: login success
triggers a session fetch, the cache is populated only from its
response, and navigation to the sanitized `next` happens only after
that succeeds. If establishment fails after a successful login, a
distinct state offers a session-fetch-only retry — credentials are
never resubmitted automatically.

### 4. CSRF token read from the session cache at call time

The two authenticated unsafe M2E operations — logout and existing-user
invitation acceptance — resolve the token from the cache when they
execute, never capturing it at construction. Public mutations
(invitation preview, new-user acceptance, reset redemption) attach no
CSRF header; their protection is the backend's browser-context Origin
validation, which same-origin requests satisfy. A privileged 401
cancels user-scoped queries, _sets_ the session to anonymous (no
refetch of a known-dead session), and removes user-scoped cached data.

### 5. Paste-only token handling

Invitation and reset tokens exist only in controlled component state
and transient mutation execution. They never enter URL paths, query
parameters, fragments, router state, browser history, localStorage,
sessionStorage, query keys (preview and redemption are mutations, never
token-keyed queries), logs, telemetry, or rendered/developer error
output. Token inputs disable autofill, spellcheck, autocorrect, and
autocapitalize. Terminal success clears the fields and resets
token-bearing mutation state, leaving no path that could resubmit a
consumed token.

### 6. Dual invitation-acceptance flows

The public accept route resolves the session first (loading renders a
neutral pending state — the wrong flow can never flash; an unexpected
bootstrap failure is distinct and retryable). Anonymous visitors get
the new-user flow: preview (POST body; business name, role, masked
email hint only) → display name + password + confirmation → acceptance
→ an explicit not-signed-in success linking to `/login` (no
auto-login). Authenticated visitors get the existing-user flow: same
preview → explicit confirmation → CSRF-protected acceptance. The full
invited email is never rendered; the backend's neutral 404 semantics
are preserved verbatim; the honest already-member 409 message may be
shown.

### 7. Acceptance is irreversible: the terminal refresh machine

After existing-user acceptance succeeds, the flow enters a terminal
`acceptedRefreshingSession` state: the token is cleared, token-bearing
mutations are reset, and only the acceptance response's safe
`business_id` survives (in a ref) to confirm the new membership in the
refreshed authoritative session. Refresh failure preserves the
acceptance and offers a session-refresh retry only; a refreshed session
missing the membership is a safe consistency state offering refresh and
logout/login recovery — nothing ever resubmits or suggests resubmitting
the consumed token, and no internal identifiers are exposed.

### 8. Password-reset success clears all cached authenticated state

The reset page always uses the public redemption contract, regardless
of any existing session cookie. Success clears every sensitive field
and mutation state, sets the cached session to anonymous, removes
user-scoped data (the backend revoked every session), and says plainly
that the user is not signed in.

### 9. Safe internal-only redirects

`sanitizeNext` reduces untrusted `next` values to a normalized internal
`pathname + search` (fragments dropped; no M2E route consumes them).
Rejected outright: non-strings, empty or over-length values, control
characters, literal backslashes, percent-encoded path separators
(`%2f`/`%5c`, any case — router normalization is never trusted with
them), absolute and scheme-relative URLs, anything resolving outside
the app origin, `/login` and its subpaths including dot-segment
equivalents, and query keys whose decoded names contain `token`.
Invalid input falls back to `/`.

### 10. Deferred and app-local choices

React Hook Form and Zod remain deferred to the first complex editing
workflow (expected M3); M2E uses controlled, accessible forms with
inline 422 field-error mapping through the ADR-008 envelope. Styling
stays app-local (CSS modules over the existing custom properties,
mobile-first, 44px minimum targets); no `admin-ui` or `design-tokens`
package exists until a second real consumer does.

### 11. Live verification is a separately authorized step

Component tests (mocked injected client) prove the flows; the literal
proxy behavior — cookie round-trip, Host/Origin acceptance, relative
`/api` URLs through the running Vite proxy — requires the dev database
at the M2D schema. That step is deliberately sequenced as: fresh
verified backup → authorized migration to `6fbce030db33` → live
browser smoke. Until then the root `pnpm dev` command (which
auto-migrates) is not run.

## Consequences

- The backend keeps zero CORS configuration; deploying the control
  center to a different origin would require a new ADR, not a config
  flip.
- The session cache is the single source of auth truth; any future
  feature needing identity reads it through `useSession`/the query
  cache rather than adding stores.
- Token-bearing UI must keep the paste-only discipline; a future
  link-based acceptance flow (URL-carried tokens) needs its own
  security ruling.
- M2F (platform UI, E2E) builds on these guards and providers without
  re-deciding them.
