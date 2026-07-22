import { useEffect } from 'react';
import { useBeforeUnload, useBlocker } from 'react-router';
import { ConfirmDialog } from '../../components/ConfirmDialog';

/**
 * Guard an in-progress edit against navigation.
 *
 * Two mechanisms, because they cover different exits: `useBlocker` catches
 * in-app navigation and can show a real dialog; `useBeforeUnload` catches a
 * tab close or reload, where the browser owns the prompt and we can only ask
 * for one.
 *
 * `when` must go false *before* a successful save navigates, or the
 * application's own redirect would prompt the user about work that was just
 * saved.
 */
export function UnsavedChangesPrompt({
  when,
  message,
}: {
  when: boolean;
  message: string;
}) {
  const blocker = useBlocker(when);

  useBeforeUnload(
    // The browser ignores the string and shows its own text; returning a
    // value is what triggers the prompt at all.
    (event) => {
      if (when) {
        event.preventDefault();
      }
    },
  );

  useEffect(() => {
    if (!when && blocker.state === 'blocked') {
      blocker.reset();
    }
  }, [when, blocker]);

  if (blocker.state !== 'blocked') {
    return null;
  }

  return (
    <ConfirmDialog
      title="Leave without saving?"
      confirmLabel="Leave"
      danger
      pending={false}
      onConfirm={() => {
        blocker.proceed();
      }}
      onCancel={() => {
        blocker.reset();
      }}
    >
      <p>{message}</p>
    </ConfirmDialog>
  );
}
