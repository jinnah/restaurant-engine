import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router';
import type { BusinessSummary } from '@restaurant-engine/api-client';
import { asApiFailure } from '../api/failure';
import { mapFailure, type FormFailure } from '../components/formErrors';
import { ErrorSummary } from '../components/StatusPanels';
import {
  useLifecycleAction,
  usePlatformBusiness,
  type LifecycleAction,
} from './businessData';
import { ConfirmDialog } from './ConfirmDialog';
import { statusBadgeClass } from './statusBadge';
import styles from './platform.module.css';

interface ActionSpec {
  action: LifecycleAction;
  label: string;
  title: string;
  body: string;
  confirmLabel: string;
  danger: boolean;
  typed: boolean;
}

/**
 * Presentation of the M2B lifecycle state machine
 * (provisioning → active ⇄ suspended → closed). Only transitions legal
 * from the current status are offered; the server remains authoritative
 * and an out-of-date view surfaces its honest 409.
 */
function availableActions(status: string): ActionSpec[] {
  switch (status) {
    case 'provisioning':
      return [
        {
          action: 'activate',
          label: 'Activate',
          title: 'Activate this business?',
          body: 'Activation requires at least one owner membership. The business becomes live on its subdomain.',
          confirmLabel: 'Activate',
          danger: false,
          typed: false,
        },
      ];
    case 'active':
      return [
        {
          action: 'suspend',
          label: 'Suspend',
          title: 'Suspend this business?',
          body: 'The public storefront disappears immediately. Data is kept and the business can be reactivated.',
          confirmLabel: 'Suspend',
          danger: true,
          typed: false,
        },
      ];
    case 'suspended':
      return [
        {
          action: 'reactivate',
          label: 'Reactivate',
          title: 'Reactivate this business?',
          body: 'The business returns to active and its storefront becomes public again.',
          confirmLabel: 'Reactivate',
          danger: false,
          typed: false,
        },
        {
          action: 'close',
          label: 'Close',
          title: 'Close this business permanently?',
          body: 'Closing is terminal: a closed business can never be reopened. Its data is retained for audit.',
          confirmLabel: 'Close permanently',
          danger: true,
          typed: true,
        },
      ];
    default:
      return [];
  }
}

function DetailField({ term, children }: { term: string; children: string }) {
  return (
    <>
      <dt>{term}</dt>
      <dd>{children}</dd>
    </>
  );
}

export function BusinessDetailPage() {
  const params = useParams();
  const businessId = params['businessId'] ?? '';
  const query = usePlatformBusiness(businessId);
  const lifecycle = useLifecycleAction(businessId);
  const [confirming, setConfirming] = useState<ActionSpec | null>(null);
  const [failure, setFailure] = useState<FormFailure | null>(null);

  useEffect(() => {
    document.title = 'Business — Restaurant Engine';
  }, []);

  if (query.isPending) {
    return (
      <p role="status" className={styles.loading}>
        Loading business…
      </p>
    );
  }
  if (query.isError) {
    return (
      <div role="alert" className={styles.errorPanel}>
        <p>This business could not be loaded.</p>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.secondary}
            onClick={() => {
              void query.refetch();
            }}
          >
            Try again
          </button>
          <Link to="/platform/businesses" className={styles.rowLink}>
            Back to businesses
          </Link>
        </div>
      </div>
    );
  }

  const business: BusinessSummary = query.data;

  function runAction(spec: ActionSpec) {
    if (lifecycle.isPending) {
      return;
    }
    setFailure(null);
    lifecycle.mutate(spec.action, {
      onSuccess: () => {
        setConfirming(null);
      },
      onError: (error: unknown) => {
        setConfirming(null);
        setFailure(
          mapFailure(
            asApiFailure(error),
            'The lifecycle change could not be applied.',
          ),
        );
      },
    });
  }

  return (
    <div>
      <section className={styles.section} aria-labelledby="business-title">
        <h2 id="business-title">
          {business.name}{' '}
          <span className={statusBadgeClass(business.status)}>
            {business.status}
          </span>
        </h2>
        {failure !== null && <ErrorSummary failure={failure} />}
        <dl className={styles.detail}>
          <DetailField term="Slug">{business.slug}</DetailField>
          <DetailField term="Currency">{business.currency}</DetailField>
          <DetailField term="Timezone">{business.timezone}</DetailField>
          <DetailField term="Created">
            {new Date(business.created_at).toLocaleString()}
          </DetailField>
          <DetailField term="Updated">
            {new Date(business.updated_at).toLocaleString()}
          </DetailField>
        </dl>
      </section>

      <section className={styles.section} aria-labelledby="lifecycle-title">
        <h2 id="lifecycle-title">Lifecycle</h2>
        {business.status === 'closed' ? (
          <p className={styles.empty}>
            This business is closed. Closure is terminal; its records remain
            available in the audit trail.
          </p>
        ) : (
          <div className={styles.actions}>
            {availableActions(business.status).map((spec) => (
              <button
                key={spec.action}
                type="button"
                className={spec.danger ? styles.danger : styles.submit}
                onClick={() => {
                  setFailure(null);
                  setConfirming(spec);
                }}
              >
                {spec.label}
              </button>
            ))}
          </div>
        )}
      </section>

      {confirming !== null && (
        <ConfirmDialog
          title={confirming.title}
          confirmLabel={confirming.confirmLabel}
          danger={confirming.danger}
          requireText={confirming.typed ? business.name : undefined}
          pending={lifecycle.isPending}
          onConfirm={() => {
            runAction(confirming);
          }}
          onCancel={() => {
            setConfirming(null);
          }}
        >
          <p>{confirming.body}</p>
        </ConfirmDialog>
      )}
    </div>
  );
}
