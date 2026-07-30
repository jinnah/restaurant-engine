import type { PublicContactSection } from '../../lib/contract';
import { mailtoHref, telHref } from '../../lib/contact-links';
import styles from './sections.module.css';

// Structured contact facts only — deliberately no hours of any kind (M5).
// Phone and email become links only when they have an unambiguous link
// form (lib/contact-links); otherwise they render as the plain text the
// owner wrote.
export function ContactSection({ section }: { section: PublicContactSection }) {
  const { heading, address_lines, phone, email } = section.props;
  const tel = phone === null ? null : telHref(phone);
  const mailto = email === null ? null : mailtoHref(email);
  return (
    <section className={styles.section}>
      <h2 className={styles.heading}>{heading}</h2>
      <address className={styles.contactList}>
        {address_lines.map((line) => (
          <p key={line} className={styles.contactLine}>
            {line}
          </p>
        ))}
        {phone === null ? null : (
          <p className={styles.contactLine}>
            {tel === null ? (
              phone
            ) : (
              <a href={tel} className={styles.contactLink}>
                {phone}
              </a>
            )}
          </p>
        )}
        {email === null ? null : (
          <p className={styles.contactLine}>
            {mailto === null ? (
              email
            ) : (
              <a href={mailto} className={styles.contactLink}>
                {email}
              </a>
            )}
          </p>
        )}
      </address>
    </section>
  );
}
