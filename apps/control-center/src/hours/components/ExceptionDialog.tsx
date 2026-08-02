import { useState, type FormEvent } from 'react';
import type {
  HoursInterval,
  ScheduleExceptionOut,
} from '@restaurant-engine/api-client';
import { Dialog } from '../../components/Dialog';
import { CheckboxField, FormField } from '../../components/FormField';
import type { FormFailure } from '../../components/formErrors';
import { useNotify } from '../../components/NotificationProvider';
import { ErrorSummary } from '../../components/StatusPanels';
import { exceptionWindow, hoursFailure, useSetException } from '../hoursData';
import {
  MINUTES_PER_DAY,
  isoDateLabel,
  minuteLabel,
  wallTimeExists,
} from '../time';
import {
  IntervalRowsEditor,
  rowError,
  rowFromInterval,
  rowToInterval,
  type IntervalRowValue,
} from './IntervalRowsEditor';
import styles from '../hours.module.css';

/** The D6 note bound (backend `MAX_NOTE_LENGTH`). */
const MAX_NOTE = 120;
/** Real transitions happen in the small hours; 05:00+ is never in a gap. */
const GAP_SCAN_BEFORE_MINUTE = 5 * 60;

/** `isoDate` shifted forward by whole days (UTC math — no zone involved). */
function datePlusDays(isoDate: string, daysAhead: number): string {
  const [year, month, day] = isoDate.split('-').map(Number);
  if (year === undefined || month === undefined || day === undefined) {
    return isoDate;
  }
  return new Date(Date.UTC(year, month - 1, day + daysAhead))
    .toISOString()
    .slice(0, 10);
}

/**
 * Non-blocking DST-gap warnings for one row on the chosen date. Unlike
 * the weekly editor there is no scan: the date is known, so each small-
 * hours boundary is checked directly. An overnight close is labelled with
 * the following date — the day that wall time actually falls on.
 */
function rowDateGapWarnings(
  isoDate: string,
  row: IntervalRowValue,
  timezone: string,
): string[] {
  const interval = rowToInterval(row);
  if (interval === null || isoDate === '') {
    return [];
  }
  const warnings: string[] = [];
  for (const minute of [interval.opens_minute, interval.closes_minute]) {
    const wall = minute % MINUTES_PER_DAY;
    if (wall >= GAP_SCAN_BEFORE_MINUTE) {
      continue;
    }
    if (!wallTimeExists(isoDate, minute, timezone)) {
      const onDate = datePlusDays(
        isoDate,
        Math.floor(minute / MINUTES_PER_DAY),
      );
      warnings.push(
        `${minuteLabel(wall)} does not exist on ${isoDateLabel(onDate)} in ${timezone} (clocks jump forward) — on that date it takes effect at the end of the jump.`,
      );
    }
  }
  return [...new Set(warnings)];
}

/** Same-day overlap over the encoded rows (incomplete rows skipped). */
function rowsOverlap(rows: IntervalRowValue[]): boolean {
  const encoded = rows
    .map(rowToInterval)
    .filter((interval): interval is HoursInterval => interval !== null)
    .sort((a, b) => a.opens_minute - b.opens_minute);
  for (let index = 1; index < encoded.length; index += 1) {
    const previous = encoded[index - 1];
    const current = encoded[index];
    if (
      previous !== undefined &&
      current !== undefined &&
      current.opens_minute < previous.closes_minute
    ) {
      return true;
    }
  }
  return false;
}

interface ExceptionDialogProps {
  businessId: string;
  timezone: string;
  /** Present when editing an existing date's override; the date is fixed. */
  existing: ScheduleExceptionOut | null;
  onClose: () => void;
}

/**
 * One date's complete override: special hours, or closed all day, with
 * the optional D6 note. Saving PUTs the whole date (`intervals: []` IS
 * "closed all day"; removing the override entirely is the panel's Remove
 * action, so absence and closure stay distinct intents). A 422 — the
 * bounded write window included — renders inside the dialog, values
 * preserved.
 */
export function ExceptionDialog({
  businessId,
  timezone,
  existing,
  onClose,
}: ExceptionDialogProps) {
  const notify = useNotify();
  const setException = useSetException(businessId);
  const [date, setDate] = useState(existing?.exception_date ?? '');
  const [closedAllDay, setClosedAllDay] = useState(
    existing !== null && existing.intervals.length === 0,
  );
  const [rows, setRows] = useState<IntervalRowValue[]>(() =>
    (existing?.intervals ?? []).map(rowFromInterval),
  );
  const [note, setNote] = useState(existing?.note ?? '');
  const [localError, setLocalError] = useState<string | null>(null);
  const [failure, setFailure] = useState<FormFailure | null>(null);
  const [writeWindow, setWriteWindow] = useState<{
    start: string;
    end: string;
  } | null>(null);

  const pending = setException.isPending;
  const overlap = !closedAllDay && rowsOverlap(rows);

  function save(event: FormEvent) {
    event.preventDefault();
    if (pending) {
      return;
    }
    setLocalError(null);
    if (date === '') {
      setLocalError('Choose a date for this exception.');
      return;
    }
    if (!closedAllDay && rows.length === 0) {
      setLocalError(
        'Add hours for this date, or mark it closed all day. To remove the exception instead, use Remove on the list.',
      );
      return;
    }
    if (
      !closedAllDay &&
      (rows.some((row) => rowError(row) !== null) || overlap)
    ) {
      setLocalError('Fix the highlighted hours before saving.');
      return;
    }
    const intervals = closedAllDay
      ? []
      : rows
          .map(rowToInterval)
          .filter((interval): interval is HoursInterval => interval !== null)
          .sort((a, b) => a.opens_minute - b.opens_minute);
    setFailure(null);
    setWriteWindow(null);
    setException.mutate(
      {
        date,
        body: { intervals, note: note.trim() === '' ? null : note },
      },
      {
        onSuccess: () => {
          // Close before notifying: a notification published while the
          // dialog is open sits behind its focus trap (ADR-018 ruling 6).
          onClose();
          notify({ message: 'Exception saved.' });
        },
        onError: (error: unknown) => {
          setFailure(hoursFailure(error, 'The exception could not be saved.'));
          setWriteWindow(exceptionWindow(error));
        },
      },
    );
  }

  return (
    <Dialog
      title={
        existing === null
          ? 'Add an exception'
          : `Edit ${isoDateLabel(existing.exception_date)}`
      }
      pending={pending}
      onCancel={onClose}
      className={styles.exceptionDialog}
    >
      {failure !== null && <ErrorSummary failure={failure} />}
      {writeWindow !== null && (
        <p className={styles.mutedText}>
          Exceptions can be set between {isoDateLabel(writeWindow.start)} and{' '}
          {isoDateLabel(writeWindow.end)}.
        </p>
      )}
      <form noValidate onSubmit={save}>
        <FormField
          id="exception-date"
          name="exception_date"
          label="Date"
          type="date"
          value={date}
          disabled={existing !== null}
          hint={
            existing !== null
              ? 'The date cannot change — remove this exception and add another instead.'
              : undefined
          }
          onChange={(event) => {
            setDate(event.target.value);
          }}
        />
        <CheckboxField
          id="exception-closed"
          label="Closed all day"
          hint="On this date the business does not open at all."
          checked={closedAllDay}
          disabled={pending}
          onChange={(event) => {
            setClosedAllDay(event.target.checked);
          }}
        />
        {!closedAllDay && (
          <>
            <IntervalRowsEditor
              rows={rows}
              onChange={setRows}
              disabled={pending}
              idPrefix="exception"
              scope="this date"
              renderRowWarning={(row) =>
                rowDateGapWarnings(date, row, timezone).map((warning) => (
                  <p key={warning} className={styles.warningText}>
                    {warning}
                  </p>
                ))
              }
            />
            {overlap && (
              <p className={styles.fieldErrorText}>
                These hours overlap. Adjust the times so intervals do not run
                into each other.
              </p>
            )}
          </>
        )}
        <FormField
          id="exception-note"
          name="note"
          label="Note (optional)"
          hint='A short public label for the date, such as "Closed for Eid".'
          value={note}
          maxLength={MAX_NOTE}
          autoComplete="off"
          onChange={(event) => {
            setNote(event.target.value);
          }}
        />
        {localError !== null && (
          <p role="alert" className={styles.fieldErrorText}>
            {localError}
          </p>
        )}
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.secondary}
            onClick={onClose}
            disabled={pending}
          >
            Cancel
          </button>
          <button type="submit" className={styles.submit} disabled={pending}>
            {pending ? 'Saving…' : 'Save exception'}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
