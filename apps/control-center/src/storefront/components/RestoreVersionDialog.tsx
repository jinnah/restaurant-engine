import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import type { DraftView } from '@restaurant-engine/api-client';
import { asApiFailure } from '../../api/failure';
import { classifyFailure } from '../../api/failures';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Dialog } from '../../components/Dialog';
import { useNotify } from '../../components/NotificationProvider';
import { formatDateTime } from '../format';
import { useRestoreVersion, useStorefrontOverview } from '../storefrontData';
import styles from '../storefront.module.css';

interface Props {
  businessId: string;
  versionId: string;
  versionNumber: number;
  onClose: () => void;
}

/**
 * The restore confirmation (ADR-022 §8): offered for archived versions
 * only, it refetches the overview when it opens and uses the FRESH
 * draft's exact lock version — never a value remembered from earlier
 * navigation. The copy states the whole consequence: the current draft's
 * content is replaced, nothing is published, history is untouched. On
 * success the owner is returned to the editor to review; publication
 * stays a later, separate, explicit action. A missing draft (defensive —
 * unreachable while history exists) renders an explanation, not a guess.
 */
export function RestoreVersionDialog({
  businessId,
  versionId,
  versionNumber,
  onClose,
}: Props) {
  const navigate = useNavigate();
  const notify = useNotify();
  const overview = useStorefrontOverview(businessId);
  const restore = useRestoreVersion(businessId);
  const [freshDraft, setFreshDraft] = useState<DraftView | null | undefined>(
    undefined,
  );
  const [error, setError] = useState<string | null>(null);

  const { refetch } = overview;
  useEffect(() => {
    let live = true;
    void refetch().then((result) => {
      if (live) {
        setFreshDraft(result.data?.draft ?? null);
      }
    });
    return () => {
      live = false;
    };
  }, [refetch]);

  if (freshDraft === undefined) {
    return (
      <Dialog
        title={`Restore version ${String(versionNumber)}?`}
        onCancel={onClose}
      >
        <p role="status" className={styles.loading}>
          Checking the current draft…
        </p>
        <div className={styles.actions}>
          <button type="button" className={styles.secondary} onClick={onClose}>
            Cancel
          </button>
        </div>
      </Dialog>
    );
  }

  if (freshDraft === null) {
    return (
      <Dialog
        title={`Restore version ${String(versionNumber)}?`}
        onCancel={onClose}
      >
        <p>
          Restoring needs an existing draft to restore into, and this business
          has none yet. Save a draft first, then restore.
        </p>
        <div className={styles.actions}>
          <button type="button" className={styles.secondary} onClick={onClose}>
            Close
          </button>
        </div>
      </Dialog>
    );
  }

  return (
    <ConfirmDialog
      title={`Restore version ${String(versionNumber)}?`}
      confirmLabel="Restore to draft"
      danger
      pending={restore.isPending}
      onCancel={onClose}
      onConfirm={() => {
        setError(null);
        restore.mutate(
          {
            versionId,
            body: { expected_lock_version: freshDraft.lock_version },
          },
          {
            onSuccess: () => {
              notify({
                message: `Version ${String(versionNumber)} restored to your draft.`,
              });
              void navigate(`/businesses/${businessId}/storefront`);
            },
            onError: (unknownError: unknown) => {
              const failure = asApiFailure(unknownError);
              setError(
                classifyFailure(failure) === 'conflict'
                  ? `The draft changed while you were deciding. Close this dialog and try again. (${failure.message})`
                  : failure.message,
              );
            },
          },
        );
      }}
    >
      <p>
        This replaces your current draft&rsquo;s content (last saved{' '}
        {formatDateTime(freshDraft.updated_at)}) with version{' '}
        {String(versionNumber)}. It does <strong>not</strong> publish anything,
        and your version history is unchanged.
      </p>
      <p>
        Afterwards you can review and preview the restored draft, and publish it
        only when you choose to.
      </p>
      {error !== null && (
        <p role="alert" className={styles.fieldErrorText}>
          {error}
        </p>
      )}
    </ConfirmDialog>
  );
}
