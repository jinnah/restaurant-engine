// The application notification system (M3E, ADR-018 ruling 6): visible,
// announced, keyboard-dismissible, never focus-stealing, and never used for
// failures.

import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import {
  NOTIFICATION_TIMEOUT_MS,
  NotificationProvider,
  useNotify,
} from '../src/components/NotificationProvider';

afterEach(() => {
  vi.useRealTimers();
});

function Publisher({ message = 'Item saved.' }: { message?: string }) {
  const notify = useNotify();
  return (
    <button
      type="button"
      onClick={() => {
        notify({ message });
      }}
    >
      publish
    </button>
  );
}

function renderProvider(ui = <Publisher />) {
  return render(<NotificationProvider>{ui}</NotificationProvider>);
}

test('the live region is mounted from the start, before any message exists', () => {
  renderProvider();
  const region = screen.getByRole('log');
  expect(region).toHaveAttribute('aria-live', 'polite');
  // Empty at mount is the point: a region created together with its first
  // message is frequently never announced.
  expect(region).toBeEmptyDOMElement();
});

test('a published notification is rendered visibly inside the live region', () => {
  renderProvider();
  fireEvent.click(screen.getByRole('button', { name: 'publish' }));
  const message = screen.getByText('Item saved.');
  expect(message).toBeInTheDocument();
  expect(screen.getByRole('log')).toContainElement(message);
});

test('publishing does not move focus away from the user', () => {
  renderProvider();
  const trigger = screen.getByRole('button', { name: 'publish' });
  trigger.focus();
  fireEvent.click(trigger);
  expect(screen.getByText('Item saved.')).toBeInTheDocument();
  expect(document.activeElement).toBe(trigger);
});

test('the dismiss action is a labelled button that removes the notification', () => {
  renderProvider();
  fireEvent.click(screen.getByRole('button', { name: 'publish' }));
  fireEvent.click(screen.getByRole('button', { name: 'Dismiss: Item saved.' }));
  expect(screen.queryByText('Item saved.')).not.toBeInTheDocument();
});

test('a notification dismisses itself after the timeout', () => {
  vi.useFakeTimers();
  renderProvider();
  fireEvent.click(screen.getByRole('button', { name: 'publish' }));
  expect(screen.getByText('Item saved.')).toBeInTheDocument();
  act(() => {
    vi.advanceTimersByTime(NOTIFICATION_TIMEOUT_MS + 10);
  });
  expect(screen.queryByText('Item saved.')).not.toBeInTheDocument();
});

test('the timer pauses while the notification holds focus', () => {
  vi.useFakeTimers();
  renderProvider();
  fireEvent.click(screen.getByRole('button', { name: 'publish' }));
  // A keyboard user tabbing toward Dismiss must not have it vanish first.
  fireEvent.focus(screen.getByRole('button', { name: 'Dismiss: Item saved.' }));
  act(() => {
    vi.advanceTimersByTime(NOTIFICATION_TIMEOUT_MS * 3);
  });
  expect(screen.getByText('Item saved.')).toBeInTheDocument();

  fireEvent.blur(screen.getByRole('button', { name: 'Dismiss: Item saved.' }));
  act(() => {
    vi.advanceTimersByTime(NOTIFICATION_TIMEOUT_MS + 10);
  });
  expect(screen.queryByText('Item saved.')).not.toBeInTheDocument();
});

test('the timer pauses while the region is hovered', () => {
  vi.useFakeTimers();
  renderProvider();
  fireEvent.click(screen.getByRole('button', { name: 'publish' }));
  fireEvent.mouseEnter(screen.getByRole('log'));
  act(() => {
    vi.advanceTimersByTime(NOTIFICATION_TIMEOUT_MS * 3);
  });
  expect(screen.getByText('Item saved.')).toBeInTheDocument();
});

test('at most three notifications are visible; the oldest is evicted', () => {
  function Multi() {
    const notify = useNotify();
    return (
      <button
        type="button"
        onClick={() => {
          for (const n of ['one', 'two', 'three', 'four']) {
            notify({ message: n });
          }
        }}
      >
        publish
      </button>
    );
  }
  renderProvider(<Multi />);
  fireEvent.click(screen.getByRole('button', { name: 'publish' }));
  expect(screen.queryByText('one')).not.toBeInTheDocument();
  for (const n of ['two', 'three', 'four']) {
    expect(screen.getByText(n)).toBeInTheDocument();
  }
});

test('useNotify outside the provider fails loudly rather than silently', () => {
  // Rendering the hook with no provider must throw, not no-op: a silently
  // swallowed confirmation is worse than a crash in development.
  const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
  expect(() => render(<Publisher />)).toThrow(/NotificationProvider/);
  spy.mockRestore();
});
