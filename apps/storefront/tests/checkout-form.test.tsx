// Checkout (M6C, ADR-026): the honest states of the placement command.
// The transport is a stubbed global fetch; what is under test is the
// payload discipline (D2 idempotency, D7 consents, D8 expected total)
// and the rendered truth of every typed 409.

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';

import { CheckoutForm } from '../components/ordering/CheckoutForm';
import { addLine, emptyCart } from '../lib/cart';
import { CART_STORAGE_KEY, loadCart, saveCart } from '../lib/cart-storage';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

const LINE = {
  item_id: '00000000-0000-0000-0000-000000000101',
  name: 'House roast chicken',
  base_price_minor: 1250,
  quantity: 2,
  item_instructions: null,
  options: [],
};

const SLOTS = ['2026-08-07T16:00:00Z', '2026-08-07T16:15:00Z'];

type FetchStub = ReturnType<typeof vi.fn>;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function envelope(code: string, details: Record<string, unknown> = {}) {
  return {
    error: { code, message: 'refused', correlation_id: null, details },
  };
}

/** A fetch stub answering the slot GET and queuing placement answers. */
function stubFetch(placementAnswers: Array<() => Response>): FetchStub {
  const stub = vi.fn((input: RequestInfo | URL) => {
    const url = String(input instanceof Request ? input.url : input);
    if (url.includes('/pickup-slots')) {
      return Promise.resolve(jsonResponse(200, { slots: SLOTS }));
    }
    const next = placementAnswers.shift();
    if (next === undefined) {
      throw new Error('unexpected placement request');
    }
    return Promise.resolve(next());
  });
  vi.stubGlobal('fetch', stub);
  return stub;
}

async function placementBodies(stub: FetchStub): Promise<unknown[]> {
  const bodies: unknown[] = [];
  for (const call of stub.mock.calls) {
    const url = String(call[0]);
    if (url.endsWith('/api/v1/public/orders')) {
      const init = call[1] as RequestInit;
      bodies.push(JSON.parse(String(init.body)));
    }
  }
  return bodies;
}

function seededCart(): void {
  saveCart(addLine(emptyCart(), LINE).cart);
}

function fillContact(): void {
  fireEvent.change(screen.getByLabelText('Name'), {
    target: { value: 'Alex Diner' },
  });
  fireEvent.change(screen.getByLabelText('Phone'), {
    target: { value: '716-555-0100' },
  });
}

function placedResponse(): Response {
  return jsonResponse(201, {
    tracking_token: 'tok-abc',
    order: { order_number: 7 },
  });
}

function renderForm(asapEnabled = true): void {
  render(
    <CheckoutForm
      currency="USD"
      timezone="America/New_York"
      asapEnabled={asapEnabled}
    />,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  push.mockReset();
  vi.unstubAllGlobals();
});

describe('the checkout surface', () => {
  test('an empty cart is the honest empty state', async () => {
    stubFetch([]);
    renderForm();
    expect(await screen.findByText(/your order is empty/i)).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /browse the menu/i }),
    ).toHaveAttribute('href', '/menu');
  });

  test('renders the cart with exact totals and never-pre-checked consents', async () => {
    stubFetch([]);
    seededCart();
    renderForm();
    expect(await screen.findByText('House roast chicken')).toBeInTheDocument();
    expect(screen.getAllByText('$25.00').length).toBeGreaterThan(0);
    const consents = screen.getAllByRole('checkbox');
    expect(consents).toHaveLength(2);
    for (const consent of consents) {
      expect(consent).not.toBeChecked();
    }
  });

  test('placement sends the D2/D7/D8 payload, clears the cart, navigates', async () => {
    const stub = stubFetch([placedResponse]);
    seededCart();
    renderForm();
    await screen.findByText('House roast chicken');
    fillContact();
    fireEvent.click(screen.getByRole('button', { name: /place order/i }));
    await waitFor(() => {
      expect(push).toHaveBeenCalledWith('/order/track/tok-abc');
    });
    const [payload] = (await placementBodies(stub)) as [
      Record<string, unknown>,
    ];
    expect(payload).toMatchObject({
      lines: [
        {
          item_id: LINE.item_id,
          quantity: 2,
          option_ids: [],
          item_instructions: null,
        },
      ],
      customer_name: 'Alex Diner',
      customer_phone: '716-555-0100',
      customer_email: null,
      order_instructions: null,
      consent_updates: false,
      consent_marketing: false,
      pickup_kind: 'asap',
      requested_pickup_at: null,
      expected_total_minor: 2500,
    });
    expect(typeof payload['idempotency_key']).toBe('string');
    expect(window.localStorage.getItem(CART_STORAGE_KEY)).toBeNull();
  });

  test('scheduled pickup requires a chosen slot and submits it', async () => {
    const stub = stubFetch([placedResponse]);
    seededCart();
    renderForm(false); // ASAP off: scheduling is the only choice.
    await screen.findByText('House roast chicken');
    fillContact();
    expect(screen.queryByText(/as soon as possible/i)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /place order/i }));
    expect(
      await screen.findByText(/choose a pickup time/i),
    ).toBeInTheDocument();
    fireEvent.change(await screen.findByLabelText(/choose a time/i), {
      target: { value: SLOTS[0] },
    });
    fireEvent.click(screen.getByRole('button', { name: /place order/i }));
    await waitFor(() => {
      expect(push).toHaveBeenCalled();
    });
    const [payload] = (await placementBodies(stub)) as [
      Record<string, unknown>,
    ];
    expect(payload).toMatchObject({
      pickup_kind: 'scheduled',
      requested_pickup_at: SLOTS[0],
    });
  });

  test('missing contact fields block the request entirely', async () => {
    const stub = stubFetch([]);
    seededCart();
    renderForm();
    await screen.findByText('House roast chicken');
    fireEvent.click(screen.getByRole('button', { name: /place order/i }));
    expect(await screen.findByText(/enter a name/i)).toBeInTheDocument();
    expect(await placementBodies(stub)).toHaveLength(0);
  });

  test('cart_stale marks the offending line and mints a fresh key on retry', async () => {
    const stub = stubFetch([
      () =>
        jsonResponse(
          409,
          envelope('cart_stale', {
            problems: [{ reason: 'item_unavailable', line_index: 0 }],
          }),
        ),
      placedResponse,
    ]);
    seededCart();
    renderForm();
    await screen.findByText('House roast chicken');
    fillContact();
    fireEvent.click(screen.getByRole('button', { name: /place order/i }));
    expect(await screen.findByText(/sold out right now/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /place order/i }));
    await waitFor(() => {
      expect(push).toHaveBeenCalled();
    });
    const bodies = (await placementBodies(stub)) as Array<
      Record<string, unknown>
    >;
    expect(bodies).toHaveLength(2);
    // D2: the refused command's key is dead; the retry is a new command.
    expect(bodies[0]?.['idempotency_key']).not.toBe(
      bodies[1]?.['idempotency_key'],
    );
  });

  test('price_changed adopts the authoritative total for the deliberate retry', async () => {
    const stub = stubFetch([
      () =>
        jsonResponse(
          409,
          envelope('price_changed', {
            expected_total_minor: 2500,
            total_minor: 2700,
            subtotal_minor: 2700,
          }),
        ),
      placedResponse,
    ]);
    seededCart();
    renderForm();
    await screen.findByText('House roast chicken');
    fillContact();
    fireEvent.click(screen.getByRole('button', { name: /place order/i }));
    expect(
      await screen.findByText(/prices changed while you were ordering/i),
    ).toBeInTheDocument();
    expect(screen.getByText('Total (updated)')).toBeInTheDocument();
    expect(screen.getAllByText('$27.00').length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: /place order/i }));
    await waitFor(() => {
      expect(push).toHaveBeenCalled();
    });
    const bodies = (await placementBodies(stub)) as Array<
      Record<string, unknown>
    >;
    expect(bodies[1]?.['expected_total_minor']).toBe(2700);
  });

  test('slot_unavailable clears the choice and refreshes the listing', async () => {
    const stub = stubFetch([
      () =>
        jsonResponse(
          409,
          envelope('slot_unavailable', {
            promised_pickup_at: SLOTS[0],
          }),
        ),
    ]);
    seededCart();
    renderForm(false);
    await screen.findByText('House roast chicken');
    fillContact();
    fireEvent.change(await screen.findByLabelText(/choose a time/i), {
      target: { value: SLOTS[0] },
    });
    fireEvent.click(screen.getByRole('button', { name: /place order/i }));
    expect(
      await screen.findByText(/no longer available — choose another/i),
    ).toBeInTheDocument();
    // The slot listing was refetched: one initial GET plus the refresh.
    const slotGets = stub.mock.calls.filter((call) =>
      String(call[0]).includes('/pickup-slots'),
    );
    expect(slotGets.length).toBe(2);
  });

  test('a mid-checkout pause is honest and keeps the order (D8)', async () => {
    stubFetch([
      () =>
        jsonResponse(
          409,
          envelope('ordering_paused', {
            note: 'Back after the dinner rush',
            resume_at: '2026-08-07T23:00:00Z',
          }),
        ),
    ]);
    seededCart();
    renderForm();
    await screen.findByText('House roast chicken');
    fillContact();
    fireEvent.click(screen.getByRole('button', { name: /place order/i }));
    const notice = await screen.findByText(/ordering was just paused/i);
    expect(notice).toHaveTextContent('Back after the dinner rush');
    expect(notice).toHaveTextContent(/back around/i);
    // The cart is untouched: resuming finds the order where it was.
    expect(loadCart().lines).toHaveLength(1);
  });

  test('a 404 is the honest "ordering is gone" state', async () => {
    stubFetch([() => jsonResponse(404, envelope('not_found'))]);
    seededCart();
    renderForm();
    await screen.findByText('House roast chicken');
    fillContact();
    fireEvent.click(screen.getByRole('button', { name: /place order/i }));
    expect(
      await screen.findByText(/online ordering is not available right now/i),
    ).toBeInTheDocument();
  });

  test('a transport failure promises no duplicate on retry', async () => {
    stubFetch([
      () => {
        throw new TypeError('network down');
      },
    ]);
    seededCart();
    renderForm();
    await screen.findByText('House roast chicken');
    fillContact();
    fireEvent.click(screen.getByRole('button', { name: /place order/i }));
    expect(await screen.findByText(/could not be placed/i)).toBeInTheDocument();
  });

  test('editing the cart returns a stale refusal to the idle state', async () => {
    stubFetch([
      () =>
        jsonResponse(
          409,
          envelope('cart_stale', {
            problems: [{ reason: 'item_unavailable', line_index: 0 }],
          }),
        ),
    ]);
    seededCart();
    renderForm();
    await screen.findByText('House roast chicken');
    fillContact();
    fireEvent.click(screen.getByRole('button', { name: /place order/i }));
    await screen.findByText(/sold out right now/i);
    fireEvent.click(
      screen.getByRole('button', { name: /remove house roast chicken/i }),
    );
    expect(screen.queryByText(/sold out right now/i)).toBeNull();
    expect(loadCart().lines).toHaveLength(0);
  });
});
