import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import styles from './notifications.module.css';

export interface NotificationInput {
  message: string;
  /** Success is the default; `info` is for neutral, non-celebratory news. */
  tone?: 'success' | 'info';
}

interface Notification extends NotificationInput {
  id: number;
}

/**
 * There is deliberately no `error` tone. Failures are persistent and inline
 * — an ErrorSummary next to the action that failed, plus per-field errors —
 * because an auto-dismissing error is an error the operator can miss
 * (ADR-018 ruling 6).
 */
export type Notify = (input: NotificationInput) => void;

const NotifyContext = createContext<Notify | null>(null);

/** Publish a success or information notification. */
export function useNotify(): Notify {
  const notify = useContext(NotifyContext);
  if (notify === null) {
    throw new Error('useNotify must be used inside NotificationProvider');
  }
  return notify;
}

/** How long a notification stays before dismissing itself. */
export const NOTIFICATION_TIMEOUT_MS = 6000;
/** Beyond this, older notifications are evicted rather than stacking. */
const MAX_VISIBLE = 3;

/**
 * The application notification system (M3E).
 *
 * The live region is mounted from application start, empty: a region created
 * in the same tick as its first message is frequently not announced at all,
 * which is the usual reason hand-rolled toasts are silent for screen-reader
 * users.
 *
 * Focus is never moved into a notification — interrupting someone right
 * after a successful save is a regression, not a courtesy. The dismiss
 * button is reachable by Tab, and the auto-dismiss timer pauses while the
 * notification is hovered or contains focus so it cannot vanish out from
 * under a keyboard user reaching for it.
 */
export function NotificationProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Notification[]>([]);
  const [held, setHeld] = useState(false);
  const nextId = useRef(0);

  const notify = useCallback<Notify>((input) => {
    nextId.current += 1;
    const item: Notification = { id: nextId.current, ...input };
    setItems((current) => [...current, item].slice(-MAX_VISIBLE));
  }, []);

  const dismiss = useCallback((id: number) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  // One timer for the oldest notification; it restarts whenever the queue
  // head changes. Paused entirely while the region is hovered or focused.
  const oldest = items[0];
  useEffect(() => {
    if (oldest === undefined || held) {
      return;
    }
    const timer = setTimeout(() => {
      dismiss(oldest.id);
    }, NOTIFICATION_TIMEOUT_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [oldest, held, dismiss]);

  const value = useMemo(() => notify, [notify]);

  return (
    <NotifyContext.Provider value={value}>
      {children}
      {/* Always rendered, even when empty — see the doc comment.
          role="log" rather than role="status": a queue where entries are
          added in order and older ones disappear is exactly what `log`
          describes, and it keeps the app-wide notification region out of the
          `status` namespace that individual pages use for their own loading
          and result announcements. */}
      <div
        className={styles.region}
        role="log"
        aria-live="polite"
        aria-atomic="false"
        aria-label="Notifications"
        onMouseEnter={() => {
          setHeld(true);
        }}
        onMouseLeave={() => {
          setHeld(false);
        }}
        onFocus={() => {
          setHeld(true);
        }}
        onBlur={() => {
          setHeld(false);
        }}
      >
        {items.map((item) => (
          <div
            key={item.id}
            className={item.tone === 'info' ? styles.info : styles.notification}
          >
            <p className={styles.message}>{item.message}</p>
            <button
              type="button"
              className={styles.dismiss}
              aria-label={`Dismiss: ${item.message}`}
              onClick={() => {
                dismiss(item.id);
              }}
            >
              Dismiss
            </button>
          </div>
        ))}
      </div>
    </NotifyContext.Provider>
  );
}
