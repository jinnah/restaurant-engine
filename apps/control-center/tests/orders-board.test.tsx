// The order board (M7C, ADR-027) through the real route table with the
// injected facade fake: every role operates it (D2), the status chips,
// the search and the tenant-day filter drive the D6 query, the
// filter-independent new-order watch raises the D10 alert with its
// off-by-default chime, the overdue indicator, the metrics strip (D11),
// the cursor "load older" that keeps history from being silently
// truncated, and the owner/manager pause control (D8).

import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import type {
  AdminOrderSummary,
  OrderListParams,
} from '@restaurant-engine/api-client';
import { renderApp } from './support/render';
import type { ClientOverrides } from './support/mockClient';
import {
  adminOrderList,
  adminOrderSummary,
  hoursSettings,
  fulfillmentOut,
  makeClient,
  membership,
  minutesFromNow,
  ok,
  orderMetrics,
  sessionView,
} from './support/mockClient';
import { CHIME_STORAGE_KEY } from '../src/orders/OrdersPage';

const BUSINESS = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';
const ORDERS = `/businesses/${BUSINESS}/orders`;
const CSRF = 'csrf-token-1';
const SECOND_ID = 'b2222222-2222-4222-8222-222222222222';

function authedClient(
  role: 'owner' | 'manager' | 'staff',
  overrides: Parameters<typeof makeClient>[0] = {},
) {
  return makeClient({
    auth: {
      getSession: vi.fn(async () =>
        ok(sessionView({ memberships: [membership({ role })] })),
      ),
    },
    hours: { get: vi.fn(async () => ok(hoursSettings())) },
    ...overrides,
  });
}

/** True for the filter-independent watch (ruling D10), which asks for
 *  submitted orders and nothing else — never for a board page. */
function isIncomingWatch(params?: OrderListParams): boolean {
  return (
    params?.q === undefined &&
    params?.day === undefined &&
    params?.status?.length === 1 &&
    params.status[0] === 'submitted'
  );
}

/**
 * A list fake that answers the watch and the board separately, the way
 * the server does: the board sees what its filters ask for, the watch
 * always sees the submitted queue.
 */
function listFake(
  board: AdminOrderSummary[],
  incoming: () => AdminOrderSummary[],
) {
  return vi.fn(async (_businessId: string, params?: OrderListParams) =>
    ok(adminOrderList(isIncomingWatch(params) ? incoming() : board)),
  );
}

function boardClient(
  role: 'owner' | 'manager' | 'staff',
  list: NonNullable<ClientOverrides['orders']>['list'],
  overrides: ClientOverrides = {},
) {
  return authedClient(role, {
    orders: { list, metrics: vi.fn(async () => ok(orderMetrics())) },
    ...overrides,
  });
}

describe('the board', () => {
  test('staff see the Orders navigation and the tickets (D2)', async () => {
    const submitted = adminOrderSummary();
    const rows = [
      submitted,
      adminOrderSummary({
        id: SECOND_ID,
        order_number: 2,
        status: 'preparing',
        customer_name: 'Bashir Chowdhury',
      }),
    ];
    renderApp(
      ORDERS,
      boardClient(
        'staff',
        listFake(rows, () => [submitted]),
      ),
    );

    expect(
      await screen.findByRole('link', { name: 'Orders' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('#1')).toBeInTheDocument();
    expect(screen.getByText('Amina Rahman')).toBeInTheDocument();
    // Operational language, never raw status values (docs/08).
    expect(screen.getByText('New', { selector: 'span' })).toBeInTheDocument();
    expect(
      screen.getByText('Preparing', { selector: 'span' }),
    ).toBeInTheDocument();
    expect(screen.getAllByText('$25.00').length).toBeGreaterThan(0);
  });

  test('the default view is every active status; a chip narrows it (D6)', async () => {
    const submitted = adminOrderSummary();
    const preparing = adminOrderSummary({
      id: SECOND_ID,
      order_number: 2,
      status: 'preparing',
    });
    const list = vi.fn(async (_businessId: string, params?: OrderListParams) =>
      ok(
        adminOrderList(
          params?.status?.length === 1 && params.status[0] === 'submitted'
            ? [submitted]
            : [submitted, preparing],
        ),
      ),
    );
    renderApp(ORDERS, boardClient('owner', list));

    await screen.findByText('#1');
    expect(list).toHaveBeenCalledWith(BUSINESS, {
      status: ['submitted', 'accepted', 'preparing', 'ready'],
    });
    expect(screen.getByText('#2')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^New/ }));
    await waitFor(() => {
      expect(screen.queryByText('#2')).toBeNull();
    });
    expect(screen.getByRole('button', { name: /^New/ })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  test('search debounces into the q filter and spans every status (D6)', async () => {
    vi.useFakeTimers();
    try {
      const list = listFake([adminOrderSummary()], () => []);
      renderApp(ORDERS, boardClient('owner', list));
      await vi.waitFor(() => {
        expect(list).toHaveBeenCalled();
      });
      fireEvent.change(screen.getByLabelText('Search'), {
        target: { value: 'bashir' },
      });
      await vi.advanceTimersByTimeAsync(400);
      await vi.waitFor(() => {
        // No status filter travels with a search: an order somebody asks
        // about by name is rarely still "New".
        expect(list).toHaveBeenCalledWith(BUSINESS, { q: 'bashir' });
      });
    } finally {
      vi.useRealTimers();
    }
  });

  test('the day filter asks for one tenant calendar day and says so', async () => {
    const list = listFake([adminOrderSummary()], () => []);
    renderApp(ORDERS, boardClient('owner', list));
    await screen.findByText('#1');

    fireEvent.change(screen.getByLabelText('Day'), {
      target: { value: '2026-08-01' },
    });
    await waitFor(() => {
      expect(list).toHaveBeenCalledWith(BUSINESS, {
        status: ['submitted', 'accepted', 'preparing', 'ready'],
        day: '2026-08-01',
      });
    });
    expect(screen.getByText(/Showing one past day/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Back to live' }));
    await waitFor(() => {
      expect(screen.queryByText(/Showing one past day/)).toBeNull();
    });
  });

  test('a full page offers the cursor rather than truncating silently', async () => {
    const first = adminOrderSummary({ order_number: 9 });
    const older = adminOrderSummary({ id: SECOND_ID, order_number: 8 });
    const list = vi.fn(
      async (_businessId: string, params?: OrderListParams) => {
        if (isIncomingWatch(params)) {
          return ok(adminOrderList([]));
        }
        return params?.before_number === undefined
          ? ok(adminOrderList([first], 9))
          : ok(adminOrderList([older]));
      },
    );
    renderApp(ORDERS, boardClient('owner', list));

    await screen.findByText('#9');
    fireEvent.click(screen.getByRole('button', { name: 'Load older orders' }));
    expect(await screen.findByText('#8')).toBeInTheDocument();
    expect(screen.getByText('#9')).toBeInTheDocument();
    expect(list).toHaveBeenCalledWith(
      BUSINESS,
      expect.objectContaining({ before_number: 9 }),
    );
  });

  test('the overdue indicator marks late active orders only', async () => {
    const late = adminOrderSummary({
      status: 'accepted',
      placed_at: minutesFromNow(-45),
      promised_pickup_at: minutesFromNow(-15),
    });
    const waiting = adminOrderSummary({
      id: SECOND_ID,
      order_number: 2,
      status: 'ready',
      placed_at: minutesFromNow(-45),
      promised_pickup_at: minutesFromNow(-15),
    });
    renderApp(
      ORDERS,
      boardClient(
        'owner',
        listFake([late, waiting], () => []),
      ),
    );

    await screen.findByText('#1');
    // Ready owes the customer nothing more, so only the accepted one is late.
    expect(screen.getAllByText('Overdue')).toHaveLength(1);
  });

  test('the metrics strip renders todays computed numbers (D11)', async () => {
    renderApp(
      ORDERS,
      boardClient(
        'owner',
        listFake([adminOrderSummary()], () => []),
      ),
    );
    await screen.findByText('#1');
    expect(screen.getByText('Today')).toBeInTheDocument();
    expect(screen.getByText('Sales')).toBeInTheDocument();
    // Money in the currency the metrics themselves carry — never guessed
    // from a row, because a quiet morning has no rows.
    expect(screen.getByText('$50.00')).toBeInTheDocument();
    expect(screen.getByText('9m')).toBeInTheDocument();
    expect(screen.getByText('Clay-oven lamb')).toBeInTheDocument();
  });

  test('a watch revealing an unseen order alerts on any filter; the chime is opt-in (D10)', async () => {
    window.localStorage.clear();
    const first = adminOrderSummary();
    const second = adminOrderSummary({ id: SECOND_ID, order_number: 2 });
    let submitted = [first];
    const list = listFake([first], () => submitted);
    const { queryClient } = renderApp(ORDERS, boardClient('owner', list));

    await screen.findByText('#1');
    // The first watch answer seeds "seen" — no alert on arrival at work.
    expect(screen.queryByText(/new order/)).toBeNull();
    // The chime toggle is off by default and persists when enabled.
    const toggle = screen.getByLabelText('New-order sound');
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);
    expect(window.localStorage.getItem(CHIME_STORAGE_KEY)).toBe('on');

    // Read the finished orders, the way staff do between rushes…
    fireEvent.click(screen.getByRole('button', { name: 'Finished' }));
    submitted = [first, second];
    await queryClient.refetchQueries();

    // …and the arrival still shouts, because the watch is filter-blind.
    expect(await screen.findByText('1 new order')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show new orders' }));
    expect(screen.queryByText('1 new order')).toBeNull();
    expect(screen.getByRole('button', { name: /^New/ })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  test('an empty view says what is absent, not a generic shrug', async () => {
    renderApp(
      ORDERS,
      boardClient(
        'owner',
        listFake([], () => []),
      ),
    );
    expect(
      await screen.findByText('No active orders right now.'),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Ready' }));
    expect(
      await screen.findByText('Nothing is waiting for pickup.'),
    ).toBeInTheDocument();
  });
});

describe('the pause control (D8)', () => {
  test('an owner pauses with a note and a duration; the banner offers resume', async () => {
    let sent:
      { paused: boolean; note?: string; resume_at?: string } | undefined;
    const setOrderingPause = vi.fn(
      async (
        _businessId: string,
        body: { paused: boolean; note?: string; resume_at?: string },
      ) => {
        sent = body;
        return ok(
          hoursSettings({
            fulfillment: fulfillmentOut({
              ordering_paused: true,
              pause_note: 'Back after the rush',
              is_configured: true,
            }),
          }),
        );
      },
    );
    renderApp(
      ORDERS,
      boardClient(
        'owner',
        listFake([], () => []),
        {
          hours: {
            get: vi.fn(async () => ok(hoursSettings())),
            setOrderingPause,
          },
        },
      ),
    );

    fireEvent.click(
      await screen.findByRole('button', { name: 'Pause ordering…' }),
    );
    fireEvent.change(screen.getByLabelText(/customer-visible note/i), {
      target: { value: 'Back after the rush' },
    });
    // A duration, not a wall clock: the device may not be in the
    // restaurant's timezone, and "in an hour" is what a pause means.
    fireEvent.change(screen.getByLabelText('Resume'), {
      target: { value: '60' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Pause ordering' }));

    await waitFor(() => {
      expect(setOrderingPause).toHaveBeenCalledWith(
        BUSINESS,
        expect.objectContaining({
          paused: true,
          note: 'Back after the rush',
        }),
        CSRF,
      );
    });
    const minutesAhead =
      (new Date(sent?.resume_at ?? '').getTime() - Date.now()) / 60_000;
    expect(minutesAhead).toBeGreaterThan(55);
    expect(minutesAhead).toBeLessThanOrEqual(60);

    expect(await screen.findByText('Ordering is paused.')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Resume ordering' }),
    ).toBeInTheDocument();
  });

  test('staff see the paused banner but no pause or resume control', async () => {
    renderApp(
      ORDERS,
      boardClient(
        'staff',
        listFake([], () => []),
        {
          hours: {
            get: vi.fn(async () =>
              ok(
                hoursSettings({
                  fulfillment: fulfillmentOut({
                    ordering_paused: true,
                    is_configured: true,
                  }),
                }),
              ),
            ),
          },
        },
      ),
    );

    expect(await screen.findByText('Ordering is paused.')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Resume ordering' }),
    ).toBeNull();
    expect(
      screen.queryByRole('button', { name: 'Pause ordering…' }),
    ).toBeNull();
  });
});
