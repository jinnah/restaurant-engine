// The order tracker (M6C, ADR-026): polling presentation of the public
// order projection, the D11 two-step customer cancellation, and the
// honest terminal states. Fetch is stubbed; timers are faked where the
// polling cadence is the subject.

import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';

import {
  OrderTracker,
  POLL_INTERVAL_MS,
} from '../components/ordering/OrderTracker';

const TOKEN = 'tok-abc';

function orderView(status: string) {
  return {
    business: {
      name: 'Corner Kitchen',
      slug: 'corner-kitchen',
      timezone: 'America/New_York',
      currency: 'USD',
    },
    order_number: 7,
    status,
    placed_at: '2026-08-07T15:00:00Z',
    business_timezone: 'America/New_York',
    pickup_kind: 'asap',
    promised_pickup_at: '2026-08-07T15:30:00Z',
    currency: 'USD',
    subtotal_minor: 2500,
    tax_minor: 0,
    total_minor: 2500,
    lines: [
      {
        display_name: 'House roast chicken',
        quantity: 2,
        base_price_minor: 1250,
        options: [
          { group_name: 'Size', option_name: 'Full', price_delta_minor: 0 },
        ],
        line_total_minor: 2500,
      },
    ],
  };
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function envelope(code: string) {
  return {
    error: { code, message: 'refused', correlation_id: null, details: null },
  };
}

beforeEach(() => {
  vi.unstubAllGlobals();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('the order tracker', () => {
  test('renders the snapshot in the tenant timezone', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(200, orderView('submitted')))),
    );
    render(<OrderTracker token={TOKEN} />);
    expect(await screen.findByText('Order #7')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Order received');
    // 15:30 UTC on 2026-08-07 is 11:30 AM in America/New_York.
    expect(screen.getByText(/11:30 AM/)).toBeInTheDocument();
    expect(screen.getByText(/2 × House roast chicken/)).toBeInTheDocument();
    expect(screen.getByText('Full')).toBeInTheDocument();
  });

  test('polls the tracking GET and stops once the status is terminal', async () => {
    vi.useFakeTimers();
    const answers = [
      orderView('submitted'),
      orderView('cancelled'),
      orderView('cancelled'),
    ];
    const stub = vi.fn(() =>
      Promise.resolve(
        jsonResponse(200, answers.shift() ?? orderView('cancelled')),
      ),
    );
    vi.stubGlobal('fetch', stub);
    render(<OrderTracker token={TOKEN} />);
    // Flush the mount effect's fetch (microtasks only — no timers).
    await act(async () => {});
    expect(stub).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    });
    expect(stub).toHaveBeenCalledTimes(2);
    // Terminal now: no further polls, ever.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
    });
    expect(stub).toHaveBeenCalledTimes(2);
  });

  test('cancellation is two-step and renders the cancelled order', async () => {
    const stub = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      return Promise.resolve(
        jsonResponse(
          200,
          url.endsWith('/cancel')
            ? orderView('cancelled')
            : orderView('submitted'),
        ),
      );
    });
    vi.stubGlobal('fetch', stub);
    render(<OrderTracker token={TOKEN} />);
    fireEvent.click(
      await screen.findByRole('button', { name: /cancel this order/i }),
    );
    // Nothing was sent yet: the confirmation is explicit.
    expect(
      stub.mock.calls.filter((call) => String(call[0]).endsWith('/cancel')),
    ).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: /yes, cancel it/i }));
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('Cancelled');
    });
    expect(
      screen.queryByRole('button', { name: /cancel this order/i }),
    ).toBeNull();
  });

  test('a 409 on cancel is the honest "too late" answer with a fresh read', async () => {
    let status = 'submitted';
    const stub = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/cancel')) {
        status = 'accepted';
        return Promise.resolve(jsonResponse(409, envelope('invalid_state')));
      }
      return Promise.resolve(jsonResponse(200, orderView(status)));
    });
    vi.stubGlobal('fetch', stub);
    render(<OrderTracker token={TOKEN} />);
    fireEvent.click(
      await screen.findByRole('button', { name: /cancel this order/i }),
    );
    fireEvent.click(screen.getByRole('button', { name: /yes, cancel it/i }));
    expect(
      await screen.findByText(/no longer be cancelled online/i),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(
        'Accepted by the restaurant',
      );
    });
  });

  test('an unknown token is the honest not-found state', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(404, envelope('not_found')))),
    );
    render(<OrderTracker token={TOKEN} />);
    expect(
      await screen.findByText(/no order was found for this link/i),
    ).toBeInTheDocument();
  });

  test('a transport failure keeps retrying, honestly', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('offline'))),
    );
    render(<OrderTracker token={TOKEN} />);
    expect(
      await screen.findByText(/could not be loaded right now/i),
    ).toBeInTheDocument();
  });
});
