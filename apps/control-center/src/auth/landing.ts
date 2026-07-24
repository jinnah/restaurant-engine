import type { SessionView } from '@restaurant-engine/api-client';
import { sanitizeNext } from './redirect';

/**
 * Post-authentication landing (item 2).
 *
 * A `next` destination the signed-in user can actually reach is honoured, so
 * authorized deep links keep working exactly as before. A `next` that would
 * only reach a guard's neutral not-found — a platform administrator following
 * a stale restaurant-owner deep link, or an owner following a platform link —
 * resolves instead to that user's role-appropriate home, so nobody lands on
 * Page Not Found straight after a legitimate sign-in.
 *
 * This is presentation only. It never grants access — the route guards and
 * the backend remain the authority, and an unreachable target simply chooses
 * a different landing rather than being rendered.
 */

/** The pathname portion of an internal `pathname + search` target. */
function pathnameOf(target: string): string {
  return target.split('?')[0]?.split('#')[0] ?? '/';
}

/** The home for this user's role: platform admins start in the platform area. */
export function roleHomePath(session: SessionView): string {
  return session.user.is_platform_admin ? '/platform' : '/';
}

/**
 * Whether the signed-in user can reach an internal path, mirroring the route
 * guards: platform routes need `is_platform_admin`; a business workspace needs
 * a membership in that business. Everything else (the home, invitation and
 * reset flows) is reachable by any authenticated user.
 */
export function canReachPath(target: string, session: SessionView): boolean {
  const path = pathnameOf(target);
  if (path === '/platform' || path.startsWith('/platform/')) {
    return session.user.is_platform_admin;
  }
  const match = /^\/businesses\/([^/]+)/.exec(path);
  if (match) {
    const businessId = decodeURIComponent(match[1] ?? '');
    return session.memberships.some(
      (membership) => membership.business_id === businessId,
    );
  }
  return true;
}

/** Where to send a user after authentication, given an untrusted `next`. */
export function landingPath(rawNext: unknown, session: SessionView): string {
  const target = sanitizeNext(rawNext);
  return canReachPath(target, session) ? target : roleHomePath(session);
}
