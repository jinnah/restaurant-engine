import type { ReactNode } from 'react';
import type { HoursInterval } from '@restaurant-engine/api-client';
import { CheckboxField } from '../../components/FormField';
import { scopedLabel } from '../../components/ScopedLabel';
import {
  MINUTES_PER_DAY,
  minuteLabel,
  minuteToTimeInput,
  timeInputToMinute,
} from '../time';
import styles from '../hours.module.css';

/** The D1 per-day ceiling (backend `MAX_INTERVALS_PER_DAY`). */
export const MAX_INTERVALS_PER_DAY = 4;

/**
 * One editable interval as the inputs speak it: `<input type="time">`
 * values plus the explicit overnight choice. Empty strings are incomplete
 * rows, never zero minutes.
 */
export interface IntervalRowValue {
  opens: string;
  closes: string;
  nextDay: boolean;
}

export function emptyRow(): IntervalRowValue {
  return { opens: '', closes: '', nextDay: false };
}

/** An editor row for a stored interval (D1 → inputs). */
export function rowFromInterval(interval: HoursInterval): IntervalRowValue {
  return {
    opens: minuteToTimeInput(interval.opens_minute),
    // The wall value is closes mod a day; 24:00 exactly (closes_minute
    // 1440) is midnight ending the day — 00:00 with the next-day flag.
    closes: minuteToTimeInput(interval.closes_minute),
    nextDay: interval.closes_minute >= MINUTES_PER_DAY,
  };
}

/** D1-encode a row, or null while it is incomplete or unparsable. */
export function rowToInterval(row: IntervalRowValue): HoursInterval | null {
  const opens = timeInputToMinute(row.opens);
  const closes = timeInputToMinute(row.closes);
  if (opens === null || closes === null) {
    return null;
  }
  return {
    opens_minute: opens,
    closes_minute: row.nextDay ? closes + MINUTES_PER_DAY : closes,
  };
}

/**
 * The row's save-blocking problem, or null. Shown while editing but never
 * enforced against typing — only Save is blocked (the server re-validates
 * everything regardless).
 */
export function rowError(row: IntervalRowValue): string | null {
  const interval = rowToInterval(row);
  if (interval === null) {
    return 'Enter both an opening and a closing time.';
  }
  if (interval.closes_minute <= interval.opens_minute) {
    return 'Closing time must be after opening time. For hours past midnight, check "Closes next day".';
  }
  if (interval.closes_minute - interval.opens_minute > MINUTES_PER_DAY) {
    return 'One interval may not be longer than 24 hours.';
  }
  return null;
}

/** A friendly label for a stored interval ("5:00 PM – 2:00 AM (next day)"). */
export function intervalLabel(interval: HoursInterval): string {
  const closesWall = interval.closes_minute % MINUTES_PER_DAY;
  const suffix = interval.closes_minute >= MINUTES_PER_DAY ? ' (next day)' : '';
  return `${minuteLabel(interval.opens_minute)} – ${minuteLabel(closesWall)}${suffix}`;
}

interface IntervalRowsEditorProps {
  rows: IntervalRowValue[];
  onChange: (rows: IntervalRowValue[]) => void;
  /** Pending lock while a save is in flight. */
  disabled: boolean;
  /** Unique id stem for this editor's inputs ("weekly-0", "exception"). */
  idPrefix: string;
  /** Accessible-name context for row actions ("Monday", "this date"). */
  scope: string;
  /** Optional non-blocking warning content under one row (DST gaps). */
  renderRowWarning?: (row: IntervalRowValue, index: number) => ReactNode;
}

/**
 * A controlled list of open intervals: opening and closing time inputs
 * plus the explicit "Closes next day" choice that carries the D1 overnight
 * encoding. Validation renders inline and blocks only Save — never typing
 * — so a row can pass through invalid states on its way to a valid one.
 */
export function IntervalRowsEditor({
  rows,
  onChange,
  disabled,
  idPrefix,
  scope,
  renderRowWarning,
}: IntervalRowsEditorProps) {
  function updateRow(index: number, patch: Partial<IntervalRowValue>) {
    onChange(
      rows.map((row, current) =>
        current === index ? { ...row, ...patch } : row,
      ),
    );
  }

  return (
    <div className={styles.intervalRows}>
      {rows.map((row, index) => {
        const error = rowError(row);
        const rowName = `${scope} hours ${String(index + 1)}`;
        const opensId = `${idPrefix}-${String(index)}-opens`;
        const closesId = `${idPrefix}-${String(index)}-closes`;
        const errorId = `${idPrefix}-${String(index)}-error`;
        return (
          // Index keys are correct here: rows are fully controlled values
          // with no per-row internal state to preserve across removals.
          <div key={index} className={styles.intervalRow}>
            <div className={styles.intervalInputs}>
              <div className={styles.timeField}>
                <label htmlFor={opensId}>Opens</label>
                <input
                  id={opensId}
                  type="time"
                  value={row.opens}
                  disabled={disabled}
                  aria-invalid={error !== null}
                  aria-describedby={error !== null ? errorId : undefined}
                  onChange={(event) => {
                    updateRow(index, { opens: event.target.value });
                  }}
                />
              </div>
              <div className={styles.timeField}>
                <label htmlFor={closesId}>Closes</label>
                <input
                  id={closesId}
                  type="time"
                  value={row.closes}
                  disabled={disabled}
                  aria-invalid={error !== null}
                  aria-describedby={error !== null ? errorId : undefined}
                  onChange={(event) => {
                    updateRow(index, { closes: event.target.value });
                  }}
                />
              </div>
              <CheckboxField
                id={`${idPrefix}-${String(index)}-next-day`}
                label="Closes next day"
                checked={row.nextDay}
                disabled={disabled}
                onChange={(event) => {
                  updateRow(index, { nextDay: event.target.checked });
                }}
              />
              <button
                type="button"
                className={styles.quiet}
                disabled={disabled}
                aria-label={scopedLabel('Remove', rowName)}
                onClick={() => {
                  onChange(rows.filter((_, current) => current !== index));
                }}
              >
                Remove
              </button>
            </div>
            {error !== null && (
              <p id={errorId} className={styles.fieldErrorText}>
                {error}
              </p>
            )}
            {renderRowWarning?.(row, index)}
          </div>
        );
      })}
      <button
        type="button"
        className={styles.secondary}
        disabled={disabled || rows.length >= MAX_INTERVALS_PER_DAY}
        aria-label={scopedLabel('Add hours to', scope)}
        onClick={() => {
          onChange([...rows, emptyRow()]);
        }}
      >
        Add hours
      </button>
    </div>
  );
}
