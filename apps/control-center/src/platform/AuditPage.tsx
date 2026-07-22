import { useEffect, useState, type FormEvent } from 'react';
import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import type {
  AuditAction,
  AuditEventSummary,
} from '@restaurant-engine/api-client';
import { useApiClient } from '../api/ClientProvider';
import { unwrapPrivileged } from '../api/failures';
import { platformKeys } from './keys';
import { FormField } from '../components/FormField';
import styles from './platform.module.css';

const PAGE_SIZE = 50;

/**
 * Filterable action choices. Each literal is compile-checked against the
 * generated AuditAction union, so a renamed or removed backend action
 * fails the typecheck here instead of silently drifting; a newly added
 * action is still filterable server-side and appears in results — it
 * just needs a line here to be offered as a choice.
 */
const ACTION_CHOICES: AuditAction[] = [
  'auth.login_succeeded',
  'auth.login_failed',
  'auth.login_throttled',
  'auth.logout',
  'auth.password_reset_issued',
  'auth.password_reset_completed',
  'user.platform_admin_created',
  'business.created',
  'business.activated',
  'business.suspended',
  'business.reactivated',
  'business.closed',
  'business.invitation_issued',
  'business.invitation_revoked',
  'business.invitation_accepted',
  'business.entitlement_granted',
  'business.entitlement_revoked',
];

interface AuditFilters {
  action?: AuditAction;
  businessId?: string;
  actorUserId?: string;
  occurredAfter?: string;
  occurredBefore?: string;
}

function toUtcIso(local: string): string | undefined {
  if (local === '') {
    return undefined;
  }
  const parsed = new Date(local);
  return Number.isNaN(parsed.getTime()) ? undefined : parsed.toISOString();
}

function EventRow({ event }: { event: AuditEventSummary }) {
  const details = event.details ?? {};
  const detailEntries = Object.entries(details);
  return (
    <li className={styles.row}>
      <div className={styles.rowMeta}>
        <p className={styles.rowText}>{event.action}</p>
        <p className={styles.rowSub}>
          #{event.id} · {new Date(event.occurred_at).toLocaleString()} · actor{' '}
          {event.actor_user_id ?? 'system'} ·{' '}
          {event.business_id === null
            ? 'platform scope'
            : `business ${event.business_id}`}
          {event.target_type !== null &&
            ` · target ${event.target_type} ${event.target_id ?? ''}`}
          {detailEntries.length > 0 &&
            ` · ${detailEntries
              .map(([key, value]) => `${key}: ${String(value)}`)
              .join(', ')}`}
        </p>
      </div>
    </li>
  );
}

export function AuditPage() {
  const client = useApiClient();
  const queryClient = useQueryClient();

  // Draft filter inputs; applied filters drive the query key so Apply
  // is an explicit, announced transition (no per-keystroke fetching).
  const [action, setAction] = useState('');
  const [businessId, setBusinessId] = useState('');
  const [actorUserId, setActorUserId] = useState('');
  const [after, setAfter] = useState('');
  const [before, setBefore] = useState('');
  const [applied, setApplied] = useState<AuditFilters>({});

  useEffect(() => {
    document.title = 'Audit — Restaurant Engine';
  }, []);

  const events = useInfiniteQuery({
    queryKey: platformKeys.audit(applied),
    initialPageParam: undefined as number | undefined,
    queryFn: async ({ pageParam }) =>
      unwrapPrivileged(
        queryClient,
        await client.platform.listAuditEvents({
          limit: PAGE_SIZE,
          beforeId: pageParam,
          action: applied.action,
          businessId: applied.businessId,
          actorUserId: applied.actorUserId,
          occurredAfter: applied.occurredAfter,
          occurredBefore: applied.occurredBefore,
        }),
      ),
    getNextPageParam: (lastPage) => lastPage.next_before_id ?? undefined,
  });

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    setApplied({
      action: action === '' ? undefined : (action as AuditAction),
      businessId: businessId === '' ? undefined : businessId,
      actorUserId: actorUserId === '' ? undefined : actorUserId,
      occurredAfter: toUtcIso(after),
      occurredBefore: toUtcIso(before),
    });
  }

  const allEvents = events.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <section className={styles.section} aria-labelledby="audit-title">
      <h2 id="audit-title">Audit trail</h2>
      <p className={styles.hint}>
        The platform-wide record of administrative and authentication activity,
        newest first. Records are immutable.
      </p>

      <form noValidate onSubmit={applyFilters}>
        <div className={styles.field}>
          <label htmlFor="audit-action">Action</label>
          <select
            id="audit-action"
            value={action}
            onChange={(event) => {
              setAction(event.target.value);
            }}
          >
            <option value="">Any action</option>
            {ACTION_CHOICES.map((choice) => (
              <option key={choice} value={choice}>
                {choice}
              </option>
            ))}
          </select>
        </div>
        <FormField
          id="audit-business"
          label="Business ID"
          type="text"
          autoComplete="off"
          spellCheck={false}
          value={businessId}
          onChange={(event) => {
            setBusinessId(event.target.value);
          }}
        />
        <FormField
          id="audit-actor"
          label="Actor user ID"
          type="text"
          autoComplete="off"
          spellCheck={false}
          value={actorUserId}
          onChange={(event) => {
            setActorUserId(event.target.value);
          }}
        />
        <FormField
          id="audit-after"
          label="Occurred after"
          type="datetime-local"
          value={after}
          onChange={(event) => {
            setAfter(event.target.value);
          }}
        />
        <FormField
          id="audit-before"
          label="Occurred before"
          type="datetime-local"
          value={before}
          onChange={(event) => {
            setBefore(event.target.value);
          }}
        />
        <div className={styles.actions}>
          <button type="submit" className={styles.submit}>
            Apply filters
          </button>
          <button
            type="button"
            className={styles.secondary}
            onClick={() => {
              void events.refetch();
            }}
          >
            Refresh
          </button>
        </div>
      </form>

      {events.isPending && (
        <p role="status" className={styles.loading}>
          Loading audit events…
        </p>
      )}
      {events.isError && (
        <div role="alert" className={styles.errorPanel}>
          <p>The audit trail could not be loaded.</p>
          <button
            type="button"
            className={styles.secondary}
            onClick={() => {
              void events.refetch();
            }}
          >
            Try again
          </button>
        </div>
      )}
      {events.isSuccess && allEvents.length === 0 && (
        <p className={styles.empty}>No audit events match these filters.</p>
      )}
      {events.isSuccess && allEvents.length > 0 && (
        <>
          <ul className={styles.list} aria-label="Audit events">
            {allEvents.map((event) => (
              <EventRow key={event.id} event={event} />
            ))}
          </ul>
          {events.hasNextPage && (
            <button
              type="button"
              className={styles.secondary}
              disabled={events.isFetchingNextPage}
              onClick={() => {
                void events.fetchNextPage();
              }}
            >
              {events.isFetchingNextPage ? 'Loading…' : 'Load older events'}
            </button>
          )}
        </>
      )}
    </section>
  );
}
