import { scopedLabel } from '../../components/ScopedLabel';
import {
  SECTION_TYPE_LABELS,
  sectionSummary,
  type ConfigSection,
} from '../composition';
import styles from '../storefront.module.css';

interface Props {
  section: ConfigSection;
  index: number;
  count: number;
  /** How many mapped server errors point into this section. */
  serverErrorCount: number;
  /** False renders the read-only card (closed business, or saving). */
  canEdit: boolean;
  onEdit: () => void;
  onRemove: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onToggleEnabled: (enabled: boolean) => void;
}

/**
 * One section's summary card (ADR-022 §4): type, a one-line content
 * summary, its enabled state, and the keyboard-first Move up / Move down
 * / Edit / Remove actions. Every action is scoped by the section's type
 * label for assistive technology, since five cards carry the same verbs.
 */
export function SectionCard({
  section,
  index,
  count,
  serverErrorCount,
  canEdit,
  onEdit,
  onRemove,
  onMoveUp,
  onMoveDown,
  onToggleEnabled,
}: Props) {
  const label = SECTION_TYPE_LABELS[section.type];
  const summary = sectionSummary(section);
  const checkboxId = `section-enabled-${section.type}`;
  return (
    <li className={styles.sectionRow}>
      <div className={styles.sectionRowBody}>
        <strong>{label}</strong>
        {summary !== null && (
          <div className={styles.sectionSummaryText}>{summary}</div>
        )}
        {serverErrorCount > 0 && (
          <p role="alert" className={styles.fieldErrorText}>
            {serverErrorCount === 1
              ? 'One field needs attention — open Edit to fix it.'
              : `${String(serverErrorCount)} fields need attention — open Edit to fix them.`}
          </p>
        )}
      </div>
      {!section.enabled && <span className={styles.disabledBadge}>Hidden</span>}
      {canEdit && (
        <div className={styles.actions}>
          <label className={styles.inlineCheck} htmlFor={checkboxId}>
            <input
              id={checkboxId}
              type="checkbox"
              checked={section.enabled}
              onChange={(event) => {
                onToggleEnabled(event.target.checked);
              }}
            />
            Show
          </label>
          <button
            type="button"
            className={styles.quiet}
            disabled={index === 0}
            aria-label={scopedLabel('Move up', label)}
            onClick={onMoveUp}
          >
            Move up
          </button>
          <button
            type="button"
            className={styles.quiet}
            disabled={index === count - 1}
            aria-label={scopedLabel('Move down', label)}
            onClick={onMoveDown}
          >
            Move down
          </button>
          <button
            type="button"
            className={styles.secondary}
            aria-label={scopedLabel('Edit', label)}
            onClick={onEdit}
          >
            Edit
          </button>
          <button
            type="button"
            className={styles.quiet}
            aria-label={scopedLabel('Remove', label)}
            onClick={onRemove}
          >
            Remove
          </button>
        </div>
      )}
    </li>
  );
}
