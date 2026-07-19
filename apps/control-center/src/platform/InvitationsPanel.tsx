import { useState, type FormEvent } from 'react';
import type {
  InvitationIssueResponse,
  InvitationSummary,
} from '@restaurant-engine/api-client';
import { asApiFailure } from '../api/failure';
import { mapFailure, type FormFailure } from '../components/formErrors';
import { ErrorSummary } from '../components/StatusPanels';
import { ConfirmDialog } from './ConfirmDialog';
import {
  useCreateInvitation,
  usePlatformInvitations,
  useRevokeInvitation,
} from './invitationData';
import { OneTimeTokenReveal } from './OneTimeTokenReveal';
import styles from './platform.module.css';

const PAGE_SIZE = 10;
const ROLES = ['owner', 'manager', 'staff'] as const;

interface InvitationsPanelProps {
  businessId: string;
  /** Lifecycle status: issuance is offered only while it is legal. */
  businessStatus: string;
}

/**
 * Pending-invitation administration for one business: issue (with the
 * one-time token reveal), list, and revoke. The raw token never leaves
 * this component's transient state.
 */
export function InvitationsPanel({
  businessId,
  businessStatus,
}: InvitationsPanelProps) {
  const [offset, setOffset] = useState(0);
  const invitations = usePlatformInvitations(businessId, {
    limit: PAGE_SIZE,
    offset,
  });
  const create = useCreateInvitation(businessId);
  const revoke = useRevokeInvitation(businessId);

  const [email, setEmail] = useState('');
  const [role, setRole] = useState<(typeof ROLES)[number]>('owner');
  const [failure, setFailure] = useState<FormFailure | null>(null);
  // The raw token lives only here, in transient component state: a
  // route change, sign-out, or dead session unmounts the panel and the
  // token goes with it. Nothing ever writes it to a cache or store.
  const [issued, setIssued] = useState<InvitationIssueResponse | null>(null);
  const [revoking, setRevoking] = useState<InvitationSummary | null>(null);

  const canIssue =
    businessStatus === 'provisioning' || businessStatus === 'active';

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (create.isPending) {
      return;
    }
    // A new attempt immediately discards any previously revealed token.
    setIssued(null);
    setFailure(null);
    create.mutate(
      { email, role },
      {
        onSuccess: (response) => {
          setEmail('');
          setIssued(response);
        },
        onError: (error: unknown) => {
          setFailure(
            mapFailure(
              asApiFailure(error),
              'The invitation could not be issued.',
            ),
          );
        },
      },
    );
  }

  function confirmRevoke(invitation: InvitationSummary) {
    if (revoke.isPending) {
      return;
    }
    setFailure(null);
    revoke.mutate(invitation.invitation_id, {
      onSuccess: () => {
        setRevoking(null);
      },
      onError: (error: unknown) => {
        setRevoking(null);
        setFailure(
          mapFailure(
            asApiFailure(error),
            'The invitation could not be revoked.',
          ),
        );
      },
    });
  }

  return (
    <section className={styles.section} aria-labelledby="invitations-title">
      <h2 id="invitations-title">Invitations</h2>
      {failure !== null && <ErrorSummary failure={failure} />}
      {issued !== null && (
        <OneTimeTokenReveal
          token={issued.token}
          heading="Invitation issued"
          onDismiss={() => {
            setIssued(null);
          }}
        >
          <p>
            For <strong>{issued.email}</strong> as{' '}
            <strong>{issued.role}</strong>, valid until{' '}
            {new Date(issued.expires_at).toLocaleString()}.
          </p>
        </OneTimeTokenReveal>
      )}

      {canIssue ? (
        <form noValidate onSubmit={onSubmit}>
          <div className={styles.field}>
            <label htmlFor="invite-email">Email</label>
            <input
              id="invite-email"
              name="email"
              type="email"
              autoComplete="off"
              required
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
              }}
              aria-invalid={failure?.fields['email'] !== undefined}
              aria-describedby={
                failure?.fields['email'] !== undefined
                  ? 'invite-email-error'
                  : undefined
              }
            />
            {failure?.fields['email'] !== undefined && (
              <p id="invite-email-error" className={styles.fieldError}>
                {failure.fields['email']}
              </p>
            )}
          </div>
          <div className={styles.field}>
            <label htmlFor="invite-role">Role</label>
            <select
              id="invite-role"
              name="role"
              value={role}
              onChange={(event) => {
                setRole(event.target.value as (typeof ROLES)[number]);
              }}
            >
              {ROLES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            className={styles.submit}
            disabled={create.isPending}
          >
            {create.isPending ? 'Issuing…' : 'Issue invitation'}
          </button>
        </form>
      ) : (
        <p className={styles.empty}>
          Invitations can be issued only while the business is provisioning or
          active. Pending invitations below can still be revoked.
        </p>
      )}

      <h3>Pending</h3>
      {invitations.isPending && (
        <p role="status" className={styles.loading}>
          Loading invitations…
        </p>
      )}
      {invitations.isError && (
        <div role="alert" className={styles.errorPanel}>
          <p>The invitations could not be loaded.</p>
          <button
            type="button"
            className={styles.secondary}
            onClick={() => {
              void invitations.refetch();
            }}
          >
            Try again
          </button>
        </div>
      )}
      {invitations.isSuccess && invitations.data.items.length === 0 && (
        <p className={styles.empty}>No pending invitations.</p>
      )}
      {invitations.isSuccess && invitations.data.items.length > 0 && (
        <>
          <ul className={styles.list}>
            {invitations.data.items.map((invitation) => (
              <li key={invitation.invitation_id} className={styles.row}>
                <div className={styles.rowMeta}>
                  <p className={styles.rowText}>{invitation.email}</p>
                  <p className={styles.rowSub}>
                    {invitation.role} · {invitation.state} · expires{' '}
                    {new Date(invitation.expires_at).toLocaleString()}
                  </p>
                </div>
                <button
                  type="button"
                  className={styles.danger}
                  aria-label={`Revoke invitation for ${invitation.email}`}
                  onClick={() => {
                    setFailure(null);
                    setRevoking(invitation);
                  }}
                >
                  Revoke
                </button>
              </li>
            ))}
          </ul>
          <div className={styles.pager}>
            <button
              type="button"
              className={styles.secondary}
              disabled={offset === 0}
              onClick={() => {
                setOffset(Math.max(0, offset - PAGE_SIZE));
              }}
            >
              Previous
            </button>
            <p className={styles.pagerInfo}>
              Showing {offset + 1}–{offset + invitations.data.items.length} of{' '}
              {invitations.data.total}
            </p>
            <button
              type="button"
              className={styles.secondary}
              disabled={offset + PAGE_SIZE >= invitations.data.total}
              onClick={() => {
                setOffset(offset + PAGE_SIZE);
              }}
            >
              Next
            </button>
          </div>
        </>
      )}

      {revoking !== null && (
        <ConfirmDialog
          title={`Revoke the invitation for ${revoking.email}?`}
          confirmLabel="Revoke"
          danger
          pending={revoke.isPending}
          onConfirm={() => {
            confirmRevoke(revoking);
          }}
          onCancel={() => {
            setRevoking(null);
          }}
        >
          <p>
            The invitation token stops working immediately. A new invitation can
            be issued afterwards.
          </p>
        </ConfirmDialog>
      )}
    </section>
  );
}
