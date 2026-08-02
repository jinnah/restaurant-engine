import { useState } from 'react';
import type {
  HoursInterval,
  HoursSettings,
  WeeklyIntervalIn,
} from '@restaurant-engine/api-client';
import type { FormFailure } from '../../components/formErrors';
import { useNotify } from '../../components/NotificationProvider';
import { ErrorSummary } from '../../components/StatusPanels';
import { hoursFailure, useSetWeekly } from '../hoursData';
import {
  DAY_NAMES,
  MINUTES_PER_DAY,
  firstWeeklyGapDate,
  isoDateLabel,
  minuteLabel,
} from '../time';
import {
  IntervalRowsEditor,
  intervalLabel,
  rowError,
  rowFromInterval,
  rowToInterval,
  type IntervalRowValue,
} from './IntervalRowsEditor';
import styles from '../hours.module.css';

/** Real transitions happen in the small hours; 05:00+ is never in a gap. */
const GAP_SCAN_BEFORE_MINUTE = 5 * 60;

/** The weekly schedule as seven editable row lists (day 0 = Monday). */
function daysFromWeekly(weekly: HoursSettings['weekly']): IntervalRowValue[][] {
  const days: IntervalRowValue[][] = DAY_NAMES.map(() => []);
  const sorted = [...weekly].sort(
    (a, b) => a.day_of_week - b.day_of_week || a.opens_minute - b.opens_minute,
  );
  for (const interval of sorted) {
    days[interval.day_of_week]?.push(rowFromInterval(interval));
  }
  return days;
}

/** The full-replacement payload, canonically ordered (day, then opens). */
function toWeeklySet(days: IntervalRowValue[][]): {
  intervals: WeeklyIntervalIn[];
} {
  const intervals: WeeklyIntervalIn[] = [];
  days.forEach((rows, day) => {
    const encoded = rows
      .map(rowToInterval)
      .filter((interval): interval is HoursInterval => interval !== null)
      .sort((a, b) => a.opens_minute - b.opens_minute);
    for (const interval of encoded) {
      intervals.push({
        day_of_week: day,
        opens_minute: interval.opens_minute,
        closes_minute: interval.closes_minute,
      });
    }
  });
  return { intervals };
}

/**
 * Same-day overlap: encoded rows sorted by opening, each must open at or
 * after the previous close. Incomplete rows are skipped — they carry
 * their own row error. Overnight spill into the NEXT day's openings is
 * deliberately left to the server's week-circle validation; its 422
 * message surfaces in the form-level summary.
 */
function dayHasOverlap(rows: IntervalRowValue[]): boolean {
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

/**
 * Non-blocking DST-gap warnings for one row's boundaries. Each boundary
 * is resolved to the local day it actually falls on (an overnight close
 * belongs to the following day) and scanned only when its wall minute is
 * in the small hours. The server rule the copy describes is ADR-025
 * timekeeping rule 3: the boundary moves to the end of the gap.
 */
function rowGapWarnings(
  dayOfWeek: number,
  row: IntervalRowValue,
  timezone: string,
): string[] {
  const interval = rowToInterval(row);
  if (interval === null) {
    return [];
  }
  const boundaries = [
    { day: dayOfWeek, minute: interval.opens_minute },
    {
      day:
        (dayOfWeek + Math.floor(interval.closes_minute / MINUTES_PER_DAY)) % 7,
      minute: interval.closes_minute % MINUTES_PER_DAY,
    },
  ];
  const warnings: string[] = [];
  for (const boundary of boundaries) {
    if (boundary.minute >= GAP_SCAN_BEFORE_MINUTE) {
      continue;
    }
    const gapDate = firstWeeklyGapDate(boundary.day, boundary.minute, timezone);
    if (gapDate !== null) {
      warnings.push(
        `${minuteLabel(boundary.minute)} does not exist on ${isoDateLabel(gapDate)} in ${timezone} (clocks jump forward) — on that date it takes effect at the end of the jump.`,
      );
    }
  }
  return [...new Set(warnings)];
}

interface WeeklyHoursEditorProps {
  businessId: string;
  settings: HoursSettings;
  canEdit: boolean;
}

/**
 * The recurring weekly schedule: seven days of interval rows and ONE
 * explicit Save performing the full-week replacement (ADR-025's API
 * shape — per-row saves would make overlap a cross-request problem).
 * State is seeded from the loaded settings once and reset only by a
 * successful save, to the server-normalized result.
 */
export function WeeklyHoursEditor({
  businessId,
  settings,
  canEdit,
}: WeeklyHoursEditorProps) {
  const notify = useNotify();
  const setWeekly = useSetWeekly(businessId);
  const [days, setDays] = useState<IntervalRowValue[][]>(() =>
    daysFromWeekly(settings.weekly),
  );
  const [baseline, setBaseline] = useState<IntervalRowValue[][]>(() =>
    daysFromWeekly(settings.weekly),
  );
  const [failure, setFailure] = useState<FormFailure | null>(null);

  if (!canEdit) {
    // Read-only presentation (staff, or a closed business): the schedule
    // itself, not a forest of disabled inputs.
    return (
      <section aria-labelledby="weekly-hours-title" className={styles.panel}>
        <h3 id="weekly-hours-title">Weekly hours</h3>
        <ul className={styles.readOnlyDays}>
          {DAY_NAMES.map((name, day) => {
            const intervals = settings.weekly
              .filter((interval) => interval.day_of_week === day)
              .sort((a, b) => a.opens_minute - b.opens_minute);
            return (
              <li key={name}>
                <strong>{name}</strong>{' '}
                {intervals.length === 0
                  ? 'Closed'
                  : intervals.map(intervalLabel).join(', ')}
              </li>
            );
          })}
        </ul>
      </section>
    );
  }

  const dirty = JSON.stringify(days) !== JSON.stringify(baseline);
  const hasRowError = days.some((rows) =>
    rows.some((row) => rowError(row) !== null),
  );
  const hasOverlap = days.some(dayHasOverlap);
  const pending = setWeekly.isPending;

  function save() {
    if (pending) {
      return;
    }
    setFailure(null);
    setWeekly.mutate(toWeeklySet(days), {
      onSuccess: (saved) => {
        // The baseline becomes the server-normalized result, pristine.
        setDays(daysFromWeekly(saved.weekly));
        setBaseline(daysFromWeekly(saved.weekly));
        notify({ message: 'Weekly hours saved.' });
      },
      onError: (error: unknown) => {
        setFailure(
          hoursFailure(error, 'The weekly schedule could not be saved.'),
        );
      },
    });
  }

  return (
    <section aria-labelledby="weekly-hours-title" className={styles.panel}>
      <h3 id="weekly-hours-title">Weekly hours</h3>
      {failure !== null && <ErrorSummary failure={failure} />}
      {DAY_NAMES.map((name, day) => {
        const rows = days[day] ?? [];
        const overlap = dayHasOverlap(rows);
        return (
          <fieldset key={name} className={styles.dayFieldset}>
            <legend>{name}</legend>
            {rows.length === 0 && <p className={styles.mutedText}>Closed.</p>}
            <IntervalRowsEditor
              rows={rows}
              onChange={(next) => {
                setDays(
                  days.map((current, currentDay) =>
                    currentDay === day ? next : current,
                  ),
                );
              }}
              disabled={pending}
              idPrefix={`weekly-${String(day)}`}
              scope={name}
              renderRowWarning={(row) =>
                rowGapWarnings(day, row, settings.timezone).map((warning) => (
                  <p key={warning} className={styles.warningText}>
                    {warning}
                  </p>
                ))
              }
            />
            {overlap && (
              <p className={styles.fieldErrorText}>
                These hours overlap. Adjust the times on {name} so intervals do
                not run into each other.
              </p>
            )}
          </fieldset>
        );
      })}
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.submit}
          disabled={pending || !dirty || hasRowError || hasOverlap}
          onClick={save}
        >
          {pending ? 'Saving…' : 'Save weekly hours'}
        </button>
        {dirty && !pending && (
          <span className={styles.mutedText} role="status">
            You have unsaved changes.
          </span>
        )}
      </div>
    </section>
  );
}
