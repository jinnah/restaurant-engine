import { useState } from 'react';
import type {
  HoursSettings,
  ScheduleExceptionOut,
} from '@restaurant-engine/api-client';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import type { FormFailure } from '../../components/formErrors';
import { useNotify } from '../../components/NotificationProvider';
import { ErrorSummary } from '../../components/StatusPanels';
import { scopedLabel } from '../../components/ScopedLabel';
import { hoursFailure, useDeleteException } from '../hoursData';
import { isoDateLabel } from '../time';
import { intervalLabel } from './IntervalRowsEditor';
import { ExceptionDialog } from './ExceptionDialog';
import styles from '../hours.module.css';

type DialogState =
  | { mode: 'add' }
  | { mode: 'edit'; exception: ScheduleExceptionOut }
  | { mode: 'remove'; exception: ScheduleExceptionOut }
  | null;

interface ExceptionsPanelProps {
  businessId: string;
  settings: HoursSettings;
  canEdit: boolean;
}

/**
 * Date-specific overrides in the bounded window around today. Each row
 * states its whole meaning — the date, "Closed all day" or the special
 * hours, and the customer-visible note — because an exception replaces
 * that date's weekly schedule entirely (ADR-025). Removing one is the
 * DELETE route: the weekly schedule resumes, which is different from
 * closing the day.
 */
export function ExceptionsPanel({
  businessId,
  settings,
  canEdit,
}: ExceptionsPanelProps) {
  const notify = useNotify();
  const deleteException = useDeleteException(businessId);
  const [dialog, setDialog] = useState<DialogState>(null);
  const [failure, setFailure] = useState<FormFailure | null>(null);

  return (
    <section aria-labelledby="exceptions-title" className={styles.panel}>
      <h3 id="exceptions-title">Exceptions</h3>
      {failure !== null && <ErrorSummary failure={failure} />}
      {settings.exceptions.length === 0 ? (
        <p className={styles.mutedText}>
          No exceptions. Holidays, closures, and one-off special hours go here;
          every other date follows the weekly schedule.
        </p>
      ) : (
        <ul className={styles.exceptionList}>
          {settings.exceptions.map((exception) => (
            <li key={exception.exception_date} className={styles.exceptionRow}>
              <div className={styles.exceptionBody}>
                <strong>{isoDateLabel(exception.exception_date)}</strong>{' '}
                {exception.intervals.length === 0
                  ? 'Closed all day'
                  : exception.intervals.map(intervalLabel).join(', ')}
                {exception.note !== null && (
                  <span className={styles.mutedText}>
                    {' '}
                    &ldquo;{exception.note}&rdquo;
                  </span>
                )}
              </div>
              {canEdit && (
                <div className={styles.exceptionActions}>
                  <button
                    type="button"
                    className={styles.quiet}
                    aria-label={scopedLabel(
                      'Edit',
                      isoDateLabel(exception.exception_date),
                    )}
                    onClick={() => {
                      setDialog({ mode: 'edit', exception });
                    }}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className={styles.quiet}
                    aria-label={scopedLabel(
                      'Remove',
                      isoDateLabel(exception.exception_date),
                    )}
                    onClick={() => {
                      setDialog({ mode: 'remove', exception });
                    }}
                  >
                    Remove
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && (
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.secondary}
            onClick={() => {
              setFailure(null);
              setDialog({ mode: 'add' });
            }}
          >
            Add exception
          </button>
        </div>
      )}

      {dialog !== null && dialog.mode !== 'remove' && (
        <ExceptionDialog
          businessId={businessId}
          timezone={settings.timezone}
          existing={dialog.mode === 'edit' ? dialog.exception : null}
          onClose={() => {
            setDialog(null);
          }}
        />
      )}

      {dialog !== null && dialog.mode === 'remove' && (
        <ConfirmDialog
          title={`Remove the exception for ${isoDateLabel(dialog.exception.exception_date)}?`}
          confirmLabel="Remove exception"
          danger
          pending={deleteException.isPending}
          onCancel={() => {
            setDialog(null);
          }}
          onConfirm={() => {
            setFailure(null);
            deleteException.mutate(dialog.exception.exception_date, {
              onSuccess: () => {
                setDialog(null);
                notify({ message: 'Exception removed.' });
              },
              onError: (error: unknown) => {
                setDialog(null);
                setFailure(
                  hoursFailure(error, 'The exception could not be removed.'),
                );
              },
            });
          }}
        >
          <p>
            The weekly schedule takes over again for{' '}
            {isoDateLabel(dialog.exception.exception_date)}. This is not the
            same as closing that day — to close it, edit the exception and mark
            it closed all day instead.
          </p>
        </ConfirmDialog>
      )}
    </section>
  );
}
