import type { PublicHoursSection } from '../contract';
import type { HoursSectionData } from './hours-data';
import {
  formatExceptionDate,
  formatExceptionHours,
  formatInstantDayTime,
  formatInstantTime,
  weeklyRows,
} from './hours-format';
import styles from './sections.module.css';

// The hours section carries heading, intro, and the status-line toggle
// only — the schedule itself is the availability projection's answer
// (ADR-025 D5), composed at render time exactly as the menu section
// composes with the public menu. `hoursData` is that composition (null
// when the page carries no availability data, e.g. the workspace
// preview); the section then renders its authored copy alone, the
// MenuSection degradation precedent. The open/closed facts are computed
// server-side by the hours domain — nothing here reads a clock.
export function HoursSection({
  section,
  hoursData,
}: {
  section: PublicHoursSection;
  hoursData: HoursSectionData | null;
}) {
  const { heading, intro, show_open_now } = section.props;
  return (
    <section className={styles.section} data-section-type="hours">
      <h2 className={styles.heading}>{heading}</h2>
      {intro === null ? null : <p className={styles.intro}>{intro}</p>}
      {hoursData === null ? null : (
        <>
          {show_open_now ? <StatusLine data={hoursData} /> : null}
          <dl className={styles.hoursWeek}>
            {weeklyRows(hoursData.weekly).map((row) => (
              <div key={row.day} className={styles.hoursRow}>
                <dt className={styles.hoursDay}>{row.day}</dt>
                <dd className={styles.hoursTimes}>{row.hours}</dd>
              </div>
            ))}
          </dl>
          {hoursData.exceptions.length === 0 ? null : (
            <div className={styles.hoursExceptions}>
              <h3 className={styles.hoursExceptionsHeading}>Special hours</h3>
              <ul className={styles.hoursExceptionList}>
                {hoursData.exceptions.map((exception) => (
                  <li
                    key={exception.exception_date}
                    className={styles.hoursExceptionItem}
                  >
                    <span className={styles.hoursExceptionDate}>
                      {formatExceptionDate(exception.exception_date)}
                    </span>{' '}
                    <span>{formatExceptionHours(exception)}</span>
                    {exception.note === null ? null : (
                      <span className={styles.hoursExceptionNote}>
                        {' '}
                        — {exception.note}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}

// The live status line: the projection's server-computed facts, formatted
// in the tenant timezone. When the business is open and a closing instant
// exists, the closing wall time follows; when closed, the next opening
// (if any) follows. A business with no upcoming opening states only
// "Closed now" — nothing is fabricated.
function StatusLine({ data }: { data: HoursSectionData }) {
  if (data.is_open_now) {
    return (
      <p className={styles.hoursStatus} data-open="true">
        <strong>Open now</strong>
        {data.closes_at === null
          ? null
          : ` · closes ${formatInstantTime(data.closes_at, data.timezone)}`}
      </p>
    );
  }
  return (
    <p className={styles.hoursStatus} data-open="false">
      <strong>Closed now</strong>
      {data.next_opens_at === null
        ? null
        : ` · opens ${formatInstantDayTime(data.next_opens_at, data.timezone)}`}
    </p>
  );
}
