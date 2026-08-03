// The order drawer (M7C, ADR-027): the D6 counter projection with its
// PII and append-only timeline, the D1/D4 machine offered as exactly the
// legal commands, the in-drawer second step for a consequential refusal,
// the honest answer to a raced 409, the D7 estimate as durations, and
// the D12 print ticket.

import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import type {
  AdminOrderDetail,
  OrderEstimateSet,
} from '@restaurant-engine/api-client';
import { renderApp } from './support/render';
import type { ClientOverrides } from './support/mockClient';
import {
  adminOrderDetail,
  adminOrderList,
  adminOrderSummary,
  apiError,
  envelope,
  hoursSettings,
  makeClient,
  membership,
  ok,
  orderMetrics,
  sessionView,
} from './support/mockClient';

const BUSINESS = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';
const ORDERS = `/businesses/${BUSINESS}/orders`;
const CSRF = 'csrf-token-1';
const ORDER_ID = '7d9e2b1c-0f34-4e6a-9b1d-2c3e4f5a6b7c';

/** A board carrying one ticket in `status`, with the drawer scripted. */
function drawerClient(
  detail: AdminOrderDetail,
  orders: ClientOverrides['orders'] = {},
) {
  return makeClient({
    auth: {
      getSession: vi.fn(async () =>
        ok(sessionView({ memberships: [membership({ role: 'staff' })] })),
      ),
    },
    hours: { get: vi.fn(async () => ok(hoursSettings())) },
    orders: {
      list: vi.fn(async () =>
        ok(adminOrderList([adminOrderSummary({ status: detail.status })])),
      ),
      metrics: vi.fn(async () => ok(orderMetrics())),
      get: vi.fn(async () => ok(detail)),
      ...orders,
    },
  });
}

async function openDrawer(detail: AdminOrderDetail, orders = {}) {
  const view = renderApp(ORDERS, drawerClient(detail, orders));
  fireEvent.click(await screen.findByRole('button', { name: /#1/ }));
  // The dialog opens at once — titled from the ticket, so the counter is
  // never looking at an anonymous box — and fills when the detail lands.
  const dialog = await screen.findByRole('dialog', { name: 'Order #1' });
  await within(dialog).findByText('Pay at pickup');
  return { ...view, dialog };
}

describe('the drawer', () => {
  test('opens on a ticket with the full projection and the timeline (D6)', async () => {
    await openDrawer(
      adminOrderDetail({
        customer_email: 'amina@example.com',
        order_instructions: 'Please add extra napkins',
        lines: [
          {
            display_name: 'Clay-oven lamb',
            quantity: 2,
            base_price_minor: 1250,
            item_instructions: 'No chilli',
            options: [
              {
                group_name: 'Spice',
                option_name: 'Mild',
                price_delta_minor: 0,
              },
            ],
            line_total_minor: 2500,
          },
        ],
      }),
    );

    const dialog = screen.getByRole('dialog', { name: 'Order #1' });
    // PII is the point of this surface (D6), under the named capability.
    expect(within(dialog).getByText('Amina Rahman')).toBeInTheDocument();
    expect(within(dialog).getByText('(716) 555-0142')).toBeInTheDocument();
    expect(within(dialog).getByText('amina@example.com')).toBeInTheDocument();
    // The kitchen's own text — the field the public projection omits.
    expect(within(dialog).getByText('“No chilli”')).toBeInTheDocument();
    // The order note reads on screen and again on the printed ticket.
    expect(
      within(dialog).getAllByText('“Please add extra napkins”'),
    ).toHaveLength(2);
    expect(within(dialog).getByText('Mild')).toBeInTheDocument();
    expect(within(dialog).getByText('2 × Clay-oven lamb')).toBeInTheDocument();
    // The append-only trail, in operational language (D7: events only).
    expect(within(dialog).getByText(/^New — /)).toBeInTheDocument();
  });

  test('offers exactly the legal commands for the current status (D1/D4)', async () => {
    await openDrawer(adminOrderDetail());
    const dialog = screen.getByRole('dialog', { name: 'Order #1' });
    for (const label of ['Accept', 'Decline', 'Cancel', 'Print ticket']) {
      expect(
        within(dialog).getByRole('button', { name: label }),
      ).toBeInTheDocument();
    }
    expect(
      within(dialog).queryByRole('button', { name: 'Mark ready' }),
    ).toBeNull();
    expect(
      within(dialog).queryByRole('button', { name: 'Complete' }),
    ).toBeNull();
  });

  test('a ready order can only be completed', async () => {
    await openDrawer(adminOrderDetail({ status: 'ready' }));
    const dialog = screen.getByRole('dialog', { name: 'Order #1' });
    expect(
      within(dialog).getByRole('button', { name: 'Complete' }),
    ).toBeInTheDocument();
    for (const label of ['Accept', 'Decline', 'Mark ready']) {
      expect(within(dialog).queryByRole('button', { name: label })).toBeNull();
    }
  });

  test('accepting sends the named command with the CSRF token and says so', async () => {
    const accept = vi.fn(async () =>
      ok(adminOrderDetail({ status: 'accepted' })),
    );
    await openDrawer(adminOrderDetail(), { accept });

    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));
    await waitFor(() => {
      expect(accept).toHaveBeenCalledWith(BUSINESS, ORDER_ID, CSRF);
    });
    expect(await screen.findByText('Order accepted.')).toBeInTheDocument();
  });

  test('declining takes a deliberate second step inside the same dialog', async () => {
    const reject = vi.fn(async () =>
      ok(adminOrderDetail({ status: 'rejected' })),
    );
    await openDrawer(adminOrderDetail(), { reject });

    fireEvent.click(screen.getByRole('button', { name: 'Decline' }));
    expect(reject).not.toHaveBeenCalled();
    // One dialog at a time: the confirmation is in this drawer, and the
    // destructive control takes focus with its consequence attached.
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    const confirm = screen.getByRole('button', { name: 'Decline order #1' });
    expect(confirm).toHaveFocus();
    expect(
      screen.getByText('Decline this order? The customer sees it immediately.'),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Keep it' }));
    expect(reject).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Decline' }));
    fireEvent.click(screen.getByRole('button', { name: 'Decline order #1' }));
    await waitFor(() => {
      expect(reject).toHaveBeenCalledWith(BUSINESS, ORDER_ID, CSRF);
    });
    expect(await screen.findByText('Order declined.')).toBeInTheDocument();
  });

  test('a raced command answers with the truth, not a guess (D1)', async () => {
    const accept = vi.fn(async () =>
      apiError(
        409,
        envelope('invalid_state', 'Order is not in a state that allows this.'),
      ),
    );
    const get = vi.fn(async () => ok(adminOrderDetail()));
    await openDrawer(adminOrderDetail(), { accept, get });

    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));
    expect(
      await screen.findByText(
        'This order changed on another device — showing the latest.',
      ),
    ).toBeInTheDocument();
    // The losing device refetches rather than inventing a status.
    await waitFor(() => {
      expect(get.mock.calls.length).toBeGreaterThan(1);
    });
  });

  test('the estimate is a duration, offered only while it is legal (D7)', async () => {
    let sent: string | null | undefined;
    const setEstimate = vi.fn(
      async (_businessId: string, _orderId: string, body: OrderEstimateSet) => {
        sent = body.estimated_ready_at;
        return ok(adminOrderDetail({ status: 'accepted' }));
      },
    );
    await openDrawer(adminOrderDetail({ status: 'accepted' }), { setEstimate });

    const before = Date.now();
    fireEvent.click(screen.getByRole('button', { name: '20 min' }));
    await waitFor(() => {
      expect(setEstimate).toHaveBeenCalledWith(
        BUSINESS,
        ORDER_ID,
        { estimated_ready_at: expect.any(String) },
        CSRF,
      );
    });
    // A duration read at the moment of the tap — never a wall-clock time
    // the device's own timezone could misread.
    const ahead = (new Date(sent ?? '').getTime() - before) / 60_000;
    expect(ahead).toBeGreaterThan(19);
    expect(ahead).toBeLessThanOrEqual(21);
    expect(await screen.findByText('Estimate set.')).toBeInTheDocument();
    // Nothing is set yet, so there is nothing to clear.
    expect(screen.queryByRole('button', { name: 'Clear estimate' })).toBeNull();
  });

  test('a set estimate shows its time and can be cleared', async () => {
    const setEstimate = vi.fn(async () =>
      ok(adminOrderDetail({ status: 'accepted', estimated_ready_at: null })),
    );
    await openDrawer(
      adminOrderDetail({
        status: 'accepted',
        estimated_ready_at: '2026-08-07T15:45:00Z',
      }),
      { setEstimate },
    );

    expect(screen.getByText(/now 11:45 AM/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Clear estimate' }));
    await waitFor(() => {
      expect(setEstimate).toHaveBeenCalledWith(
        BUSINESS,
        ORDER_ID,
        { estimated_ready_at: null },
        CSRF,
      );
    });
    expect(await screen.findByText('Estimate cleared.')).toBeInTheDocument();
  });

  test('a submitted order is not offered an estimate yet (D7)', async () => {
    await openDrawer(adminOrderDetail());
    expect(screen.queryByRole('button', { name: '20 min' })).toBeNull();
  });

  test('the print ticket carries what the kitchen needs (D12)', async () => {
    const print = vi.fn();
    vi.stubGlobal('print', print);
    try {
      const { view } = await openDrawer(
        adminOrderDetail({
          order_instructions: 'Ring the bell',
          lines: [
            {
              display_name: 'Clay-oven lamb',
              quantity: 2,
              base_price_minor: 1250,
              item_instructions: 'No chilli',
              options: [],
              line_total_minor: 2500,
            },
          ],
        }),
      );

      const ticket = view.container.querySelector(
        'section[aria-label="Print ticket"]',
      );
      expect(ticket).not.toBeNull();
      const text = ticket?.textContent ?? '';
      expect(text).toContain('#1');
      expect(text).toContain('Amina Rahman');
      expect(text).toContain('2 × Clay-oven lamb');
      expect(text).toContain('No chilli');
      expect(text).toContain('Ring the bell');

      fireEvent.click(screen.getByRole('button', { name: 'Print ticket' }));
      expect(print).toHaveBeenCalledTimes(1);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  // M7D: the drawer's dismissal used to be Escape alone, which is a
  // keyboard exit on a surface built for a counter-top tablet.
  test('closes from a control, not only from the keyboard', async () => {
    await openDrawer(adminOrderDetail());
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
  });

  test('a drawer whose detail failed to load can still be closed', async () => {
    renderApp(
      ORDERS,
      drawerClient(adminOrderDetail(), {
        get: vi.fn(async () =>
          apiError(500, envelope('internal_error', 'Something broke.')),
        ),
      }),
    );
    fireEvent.click(await screen.findByRole('button', { name: /#1/ }));
    const dialog = await screen.findByRole('dialog', { name: 'Order #1' });
    expect(
      await within(dialog).findByText('The order could not be loaded.'),
    ).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
  });
});
