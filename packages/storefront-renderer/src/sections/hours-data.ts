// The hours section's render-time composition (M5D, ADR-025 D5) — the
// `MenuSectionData` convention: a small, explicit slice of the public
// availability projection, assembled by the consuming application
// (`apps/storefront` from `GET /api/v1/public/availability`; the
// workspace preview passes null). Field names and shapes are the
// generated contract's, restated nowhere: `weekly` and `exceptions` are
// the projection's own types, the instant facts are its UTC ISO strings,
// and `timezone` is the tenant zone those instants are formatted in.

import type {
  PublicScheduleException,
  PublicWeeklyInterval,
} from '../contract';

export interface HoursSectionData {
  /** The tenant's IANA timezone — the only bridge from instants to walls. */
  timezone: string;
  /** Server-computed at request time; the renderer never reads a clock. */
  is_open_now: boolean;
  /** UTC instant the current open interval ends, when open. */
  closes_at: string | null;
  /** UTC instant of the next opening, when closed and one exists. */
  next_opens_at: string | null;
  weekly: PublicWeeklyInterval[];
  /** Upcoming overrides, bounded by the projection's forward window. */
  exceptions: PublicScheduleException[];
}
