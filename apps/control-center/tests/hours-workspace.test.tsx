// The hours workspace (M5C, ADR-025) through the real route table with
// the injected facade fake: read access for every role (D7), the weekly
// full-replacement editor with its D1 encoding and DST-gap warning, the
// per-date exception dialog, and the full-document fulfillment form.

import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import type {
  ApiResult,
  ErrorEnvelope,
  HoursSettings,
} from '@restaurant-engine/api-client';
import { renderApp } from './support/render';
import {
  apiError,
  envelope,
  fulfillmentOut,
  hoursSettings,
  makeClient,
  membership,
  ok,
  scheduleException,
  sessionView,
} from './support/mockClient';

const BUSINESS = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';
const HOURS = `/businesses/${BUSINESS}/hours`;
const CSRF = 'csrf-token-1';

function authedClient(
  role: 'owner' | 'manager' | 'staff',
  overrides: Parameters<typeof makeClient>[0] = {},
  businessStatus = 'active',
) {
  return makeClient({
    auth: {
      getSession: vi.fn(async () =>
        ok(
          sessionView({
            memberships: [
              membership({ role, business_status: businessStatus }),
            ],
          }),
        ),
      ),
    },
    ...overrides,
  });
}

/** Mon 17:00 – 02:00 the following day: the canonical overnight interval. */
const OVERNIGHT_MONDAY = {
  day_of_week: 0,
  opens_minute: 1020,
  closes_minute: 1560,
};

describe('access and navigation (D7)', () => {
  test('staff see the Hours navigation even though Storefront is absent', async () => {
    renderApp(
      HOURS,
      authedClient('staff', {
        hours: { get: vi.fn(async () => ok(hoursSettings())) },
      }),
    );
    expect(
      await screen.findByRole('link', { name: 'Hours' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'Storefront' }),
    ).not.toBeInTheDocument();
  });

  test('staff get the schedule read-only: the role note and no mutating controls', async () => {
    renderApp(
      HOURS,
      authedClient('staff', {
        hours: {
          get: vi.fn(async () =>
            ok(
              hoursSettings({
                weekly: [OVERNIGHT_MONDAY],
                exceptions: [scheduleException()],
              }),
            ),
          ),
        },
      }),
    );
    expect(
      await screen.findByText(
        'You can view the schedule; only owners and managers can change it.',
      ),
    ).toBeInTheDocument();
    // The schedule itself is fully readable…
    expect(
      screen.getByText('5:00 PM – 2:00 AM (next day)'),
    ).toBeInTheDocument();
    expect(screen.getByText('Closed all day')).toBeInTheDocument();
    // …but nothing offers a write.
    expect(
      screen.queryByRole('button', { name: 'Save weekly hours' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Add exception' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Save fulfillment settings' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Add hours/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /^Edit/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /^Remove/ }),
    ).not.toBeInTheDocument();
  });

  test.each(['owner', 'manager'] as const)(
    'a %s is offered every editing control',
    async (role) => {
      const { view } = renderApp(
        HOURS,
        authedClient(role, {
          hours: { get: vi.fn(async () => ok(hoursSettings())) },
        }),
      );
      expect(
        await screen.findByRole('button', { name: 'Save weekly hours' }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'Add exception' }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'Save fulfillment settings' }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: 'Add hours to Monday' }),
      ).toBeEnabled();
      view.unmount();
    },
  );

  test('a closed business is readable but offers an owner no mutations', async () => {
    renderApp(
      HOURS,
      authedClient(
        'owner',
        {
          hours: {
            get: vi.fn(async () =>
              ok(
                hoursSettings({
                  weekly: [OVERNIGHT_MONDAY],
                  exceptions: [scheduleException()],
                }),
              ),
            ),
          },
        },
        'closed',
      ),
    );
    expect(
      await screen.findByText(
        'This business is closed. Its hours are kept for the record and can no longer be changed.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('5:00 PM – 2:00 AM (next day)'),
    ).toBeInTheDocument();
    for (const name of [
      'Save weekly hours',
      'Add exception',
      'Save fulfillment settings',
    ]) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument();
    }
    expect(
      screen.queryByRole('button', { name: /^Remove/ }),
    ).not.toBeInTheDocument();
  });

  test('a failed load is an alert with a retry, never a blank page', async () => {
    // makeClient's default hours.get is the backend's neutral 404.
    renderApp(HOURS, authedClient('owner'));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('The hours could not be loaded.');
    expect(
      within(alert).getByRole('button', { name: 'Try again' }),
    ).toBeInTheDocument();
  });
});

describe('page facts', () => {
  test('renders the timezone, the weekly values, exceptions, and fulfillment', async () => {
    renderApp(
      HOURS,
      authedClient('owner', {
        hours: {
          get: vi.fn(async () =>
            ok(
              hoursSettings({
                weekly: [OVERNIGHT_MONDAY],
                exceptions: [
                  scheduleException({
                    exception_date: '2026-12-25',
                    intervals: [],
                    note: 'Christmas',
                  }),
                  scheduleException({
                    exception_date: '2026-12-26',
                    intervals: [{ opens_minute: 660, closes_minute: 1260 }],
                    note: null,
                  }),
                ],
              }),
            ),
          ),
        },
      }),
    );
    expect(
      await screen.findByText('All times are local to America/New_York.'),
    ).toBeInTheDocument();

    // The weekly editor speaks the D1 encoding backwards: wall times plus
    // the explicit next-day choice.
    const monday = screen.getByRole('group', { name: 'Monday' });
    expect(within(monday).getByLabelText('Opens')).toHaveValue('17:00');
    expect(within(monday).getByLabelText('Closes')).toHaveValue('02:00');
    expect(within(monday).getByLabelText('Closes next day')).toBeChecked();

    // Exceptions state their whole meaning: date, closure or hours, note.
    expect(screen.getByText('Dec 25, 2026')).toBeInTheDocument();
    expect(screen.getByText('Closed all day')).toBeInTheDocument();
    expect(screen.getByText('“Christmas”')).toBeInTheDocument();
    expect(screen.getByText('Dec 26, 2026')).toBeInTheDocument();
    expect(screen.getByText('11:00 AM – 9:00 PM')).toBeInTheDocument();

    // Fulfillment shows the effective values and says they are defaults.
    expect(screen.getByLabelText('Lead time (minutes)')).toHaveValue(20);
    expect(screen.getByText(/platform defaults/)).toBeInTheDocument();
  });
});

describe('weekly editing', () => {
  test('adding an interval and saving sends the exact full-week payload', async () => {
    const saved = hoursSettings({
      weekly: [{ day_of_week: 0, opens_minute: 540, closes_minute: 1050 }],
      fulfillment: fulfillmentOut(),
    });
    const setWeekly = vi.fn(async () => ok(saved));
    renderApp(
      HOURS,
      authedClient('owner', {
        hours: { get: vi.fn(async () => ok(hoursSettings())), setWeekly },
      }),
    );

    fireEvent.click(
      await screen.findByRole('button', { name: 'Add hours to Monday' }),
    );
    const monday = screen.getByRole('group', { name: 'Monday' });
    fireEvent.change(within(monday).getByLabelText('Opens'), {
      target: { value: '09:00' },
    });
    fireEvent.change(within(monday).getByLabelText('Closes'), {
      target: { value: '17:30' },
    });

    const save = screen.getByRole('button', { name: 'Save weekly hours' });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() => {
      expect(setWeekly).toHaveBeenCalledWith(
        BUSINESS,
        {
          intervals: [
            { day_of_week: 0, opens_minute: 540, closes_minute: 1050 },
          ],
        },
        CSRF,
      );
    });
    expect(await screen.findByText('Weekly hours saved.')).toBeInTheDocument();
    // The baseline reset to the server result: pristine again.
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'Save weekly hours' }),
      ).toBeDisabled();
    });
  });

  test('the next-day box adds 1440 and the button locks while pending', async () => {
    let resolveSave: ((result: ApiResult<HoursSettings>) => void) | undefined;
    const setWeekly = vi.fn(
      () =>
        new Promise<ApiResult<HoursSettings>>((resolve) => {
          resolveSave = resolve;
        }),
    );
    renderApp(
      HOURS,
      authedClient('owner', {
        hours: { get: vi.fn(async () => ok(hoursSettings())), setWeekly },
      }),
    );

    fireEvent.click(
      await screen.findByRole('button', { name: 'Add hours to Monday' }),
    );
    const monday = screen.getByRole('group', { name: 'Monday' });
    fireEvent.change(within(monday).getByLabelText('Opens'), {
      target: { value: '17:00' },
    });
    fireEvent.change(within(monday).getByLabelText('Closes'), {
      target: { value: '02:00' },
    });
    fireEvent.click(within(monday).getByLabelText('Closes next day'));

    fireEvent.click(screen.getByRole('button', { name: 'Save weekly hours' }));
    expect(
      await screen.findByRole('button', { name: 'Saving…' }),
    ).toBeDisabled();
    expect(setWeekly).toHaveBeenCalledWith(
      BUSINESS,
      { intervals: [OVERNIGHT_MONDAY] },
      CSRF,
    );

    resolveSave?.(ok(hoursSettings({ weekly: [OVERNIGHT_MONDAY] })));
    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'Save weekly hours' }),
      ).toBeDisabled();
    });
  });

  test('same-day overlap is a day-level error that blocks Save', async () => {
    renderApp(
      HOURS,
      authedClient('owner', {
        hours: {
          get: vi.fn(async () =>
            ok(
              hoursSettings({
                weekly: [
                  { day_of_week: 0, opens_minute: 540, closes_minute: 1050 },
                ],
              }),
            ),
          ),
        },
      }),
    );
    fireEvent.click(
      await screen.findByRole('button', { name: 'Add hours to Monday' }),
    );
    const monday = screen.getByRole('group', { name: 'Monday' });
    fireEvent.change(within(monday).getAllByLabelText('Opens')[1] as Element, {
      target: { value: '10:00' },
    });
    fireEvent.change(within(monday).getAllByLabelText('Closes')[1] as Element, {
      target: { value: '11:00' },
    });
    expect(
      screen.getByText(
        'These hours overlap. Adjust the times on Monday so intervals do not run into each other.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Save weekly hours' }),
    ).toBeDisabled();
  });

  test('closes before opens without the next-day box blocks Save', async () => {
    renderApp(
      HOURS,
      authedClient('owner', {
        hours: { get: vi.fn(async () => ok(hoursSettings())) },
      }),
    );
    fireEvent.click(
      await screen.findByRole('button', { name: 'Add hours to Monday' }),
    );
    const monday = screen.getByRole('group', { name: 'Monday' });
    fireEvent.change(within(monday).getByLabelText('Opens'), {
      target: { value: '17:00' },
    });
    fireEvent.change(within(monday).getByLabelText('Closes'), {
      target: { value: '02:00' },
    });
    expect(
      screen.getByText(
        'Closing time must be after opening time. For hours past midnight, check "Closes next day".',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Save weekly hours' }),
    ).toBeDisabled();
  });

  test('a small-hours boundary warns about the DST gap without blocking', async () => {
    // Sat 20:00 – 02:30 the following day: the close falls on Sunday
    // 02:30, which does not exist on 2026-03-08 in New York. Date is
    // frozen (Date only — timers stay real) so the 53-week scan starts
    // from a known day.
    vi.useFakeTimers({ now: new Date(Date.UTC(2026, 1, 1)), toFake: ['Date'] });
    try {
      renderApp(
        HOURS,
        authedClient('owner', {
          hours: {
            get: vi.fn(async () =>
              ok(
                hoursSettings({
                  weekly: [
                    {
                      day_of_week: 5,
                      opens_minute: 1200,
                      closes_minute: 1590,
                    },
                  ],
                }),
              ),
            ),
          },
        }),
      );
      expect(
        await screen.findByText(
          '2:30 AM does not exist on Mar 8, 2026 in America/New_York (clocks jump forward) — on that date it takes effect at the end of the jump.',
        ),
      ).toBeInTheDocument();
      // Non-blocking: the schedule is saveable the moment it is dirty.
      fireEvent.click(
        screen.getByRole('button', { name: 'Add hours to Monday' }),
      );
      const monday = screen.getByRole('group', { name: 'Monday' });
      fireEvent.change(within(monday).getByLabelText('Opens'), {
        target: { value: '09:00' },
      });
      fireEvent.change(within(monday).getByLabelText('Closes'), {
        target: { value: '17:00' },
      });
      expect(
        screen.getByRole('button', { name: 'Save weekly hours' }),
      ).toBeEnabled();
    } finally {
      vi.useRealTimers();
    }
  });

  test('a weekly 422 surfaces the envelope message and its field errors', async () => {
    const setWeekly = vi.fn(async () =>
      apiError(
        422,
        envelope('validation_error', 'The schedule is not valid.', [
          {
            field: 'intervals',
            code: 'overlap',
            message: 'Tuesday overlaps Monday night.',
          },
        ]),
      ),
    );
    renderApp(
      HOURS,
      authedClient('owner', {
        hours: { get: vi.fn(async () => ok(hoursSettings())), setWeekly },
      }),
    );
    fireEvent.click(
      await screen.findByRole('button', { name: 'Add hours to Monday' }),
    );
    const monday = screen.getByRole('group', { name: 'Monday' });
    fireEvent.change(within(monday).getByLabelText('Opens'), {
      target: { value: '09:00' },
    });
    fireEvent.change(within(monday).getByLabelText('Closes'), {
      target: { value: '17:00' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save weekly hours' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      'The schedule is not valid. Tuesday overlaps Monday night.',
    );
  });
});

describe('exceptions', () => {
  test('a closed-all-day exception with a note sends the exact payload', async () => {
    const setException = vi.fn(async () =>
      ok(
        hoursSettings({
          exceptions: [
            scheduleException({
              exception_date: '2026-12-25',
              intervals: [],
              note: 'Christmas Day',
            }),
          ],
        }),
      ),
    );
    renderApp(
      HOURS,
      authedClient('owner', {
        hours: { get: vi.fn(async () => ok(hoursSettings())), setException },
      }),
    );
    fireEvent.click(
      await screen.findByRole('button', { name: 'Add exception' }),
    );
    const dialog = screen.getByRole('dialog', { name: 'Add an exception' });
    fireEvent.change(within(dialog).getByLabelText('Date'), {
      target: { value: '2026-12-25' },
    });
    fireEvent.click(within(dialog).getByLabelText('Closed all day'));
    fireEvent.change(within(dialog).getByLabelText('Note (optional)'), {
      target: { value: 'Christmas Day' },
    });
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Save exception' }),
    );

    await waitFor(() => {
      expect(setException).toHaveBeenCalledWith(
        BUSINESS,
        '2026-12-25',
        { intervals: [], note: 'Christmas Day' },
        CSRF,
      );
    });
    // The dialog closed, the success was announced, the list updated.
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(await screen.findByText('Exception saved.')).toBeInTheDocument();
    expect(screen.getByText('Dec 25, 2026')).toBeInTheDocument();
  });

  test('the bounded-window 422 surfaces inside the dialog, values kept', async () => {
    const windowEnvelope: ErrorEnvelope = {
      error: {
        code: 'validation_error',
        message: 'The date is outside the allowed window.',
        correlation_id: null,
        field_errors: [],
        details: { window_start: '2026-07-03', window_end: '2028-02-03' },
      },
    };
    const setException = vi.fn(async () => apiError(422, windowEnvelope));
    renderApp(
      HOURS,
      authedClient('owner', {
        hours: { get: vi.fn(async () => ok(hoursSettings())), setException },
      }),
    );
    fireEvent.click(
      await screen.findByRole('button', { name: 'Add exception' }),
    );
    const dialog = screen.getByRole('dialog', { name: 'Add an exception' });
    fireEvent.change(within(dialog).getByLabelText('Date'), {
      target: { value: '2030-01-01' },
    });
    fireEvent.click(within(dialog).getByLabelText('Closed all day'));
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Save exception' }),
    );

    expect(
      await within(dialog).findByText(
        'The date is outside the allowed window.',
      ),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText(
        'Exceptions can be set between Jul 3, 2026 and Feb 3, 2028.',
      ),
    ).toBeInTheDocument();
    // Still open, values preserved for correction.
    expect(within(dialog).getByLabelText('Date')).toHaveValue('2030-01-01');
  });

  test('editing an existing date keeps the date fixed and sends its hours', async () => {
    const setException = vi.fn(async () => ok(hoursSettings()));
    renderApp(
      HOURS,
      authedClient('owner', {
        hours: {
          get: vi.fn(async () =>
            ok(
              hoursSettings({
                exceptions: [
                  scheduleException({
                    exception_date: '2026-12-26',
                    intervals: [{ opens_minute: 660, closes_minute: 1260 }],
                    note: null,
                  }),
                ],
              }),
            ),
          ),
          setException,
        },
      }),
    );
    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit Dec 26, 2026' }),
    );
    const dialog = screen.getByRole('dialog', { name: 'Edit Dec 26, 2026' });
    const date = within(dialog).getByLabelText('Date');
    expect(date).toHaveValue('2026-12-26');
    expect(date).toBeDisabled();
    expect(within(dialog).getByLabelText('Opens')).toHaveValue('11:00');
    fireEvent.change(within(dialog).getByLabelText('Closes'), {
      target: { value: '20:00' },
    });
    fireEvent.change(within(dialog).getByLabelText('Note (optional)'), {
      target: { value: 'Boxing Day hours' },
    });
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Save exception' }),
    );
    await waitFor(() => {
      expect(setException).toHaveBeenCalledWith(
        BUSINESS,
        '2026-12-26',
        {
          intervals: [{ opens_minute: 660, closes_minute: 1200 }],
          note: 'Boxing Day hours',
        },
        CSRF,
      );
    });
  });

  test('Remove flows through the ConfirmDialog to deleteException', async () => {
    const deleteException = vi.fn(async () => ok({ status: 'deleted' }));
    renderApp(
      HOURS,
      authedClient('owner', {
        hours: {
          get: vi.fn(async () =>
            ok(
              hoursSettings({
                exceptions: [
                  scheduleException({ exception_date: '2026-12-25' }),
                ],
              }),
            ),
          ),
          deleteException,
        },
      }),
    );
    fireEvent.click(
      await screen.findByRole('button', { name: 'Remove Dec 25, 2026' }),
    );
    const dialog = screen.getByRole('dialog', {
      name: 'Remove the exception for Dec 25, 2026?',
    });
    expect(
      within(dialog).getByText(/weekly schedule takes over again/),
    ).toBeInTheDocument();
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Remove exception' }),
    );
    await waitFor(() => {
      expect(deleteException).toHaveBeenCalledWith(
        BUSINESS,
        '2026-12-25',
        CSRF,
      );
    });
    expect(await screen.findByText('Exception removed.')).toBeInTheDocument();
  });

  test('the dialog warns when a chosen date puts a boundary in the gap', async () => {
    renderApp(
      HOURS,
      authedClient('owner', {
        hours: { get: vi.fn(async () => ok(hoursSettings())) },
      }),
    );
    fireEvent.click(
      await screen.findByRole('button', { name: 'Add exception' }),
    );
    const dialog = screen.getByRole('dialog', { name: 'Add an exception' });
    fireEvent.change(within(dialog).getByLabelText('Date'), {
      target: { value: '2026-03-08' },
    });
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Add hours to this date' }),
    );
    fireEvent.change(within(dialog).getByLabelText('Opens'), {
      target: { value: '02:30' },
    });
    fireEvent.change(within(dialog).getByLabelText('Closes'), {
      target: { value: '05:00' },
    });
    expect(
      within(dialog).getByText(
        '2:30 AM does not exist on Mar 8, 2026 in America/New_York (clocks jump forward) — on that date it takes effect at the end of the jump.',
      ),
    ).toBeInTheDocument();
  });
});

describe('fulfillment', () => {
  test('changing the lead time sends the exact full document', async () => {
    const setFulfillment = vi.fn(async () =>
      ok(
        hoursSettings({
          fulfillment: fulfillmentOut({
            lead_time_minutes: 45,
            is_configured: true,
          }),
        }),
      ),
    );
    renderApp(
      HOURS,
      authedClient('owner', {
        hours: { get: vi.fn(async () => ok(hoursSettings())), setFulfillment },
      }),
    );
    fireEvent.change(await screen.findByLabelText('Lead time (minutes)'), {
      target: { value: '45' },
    });
    fireEvent.click(
      screen.getByRole('button', { name: 'Save fulfillment settings' }),
    );
    await waitFor(() => {
      expect(setFulfillment).toHaveBeenCalledWith(
        BUSINESS,
        {
          pickup_enabled: false,
          asap_enabled: true,
          lead_time_minutes: 45,
          slot_interval_minutes: 15,
          last_order_before_close_minutes: 30,
          max_days_ahead: 0,
        },
        CSRF,
      );
    });
    expect(
      await screen.findByText('Fulfillment settings saved.'),
    ).toBeInTheDocument();
    // The saved row is no longer the defaults; the note withdraws.
    await waitFor(() => {
      expect(screen.queryByText(/platform defaults/)).not.toBeInTheDocument();
    });
  });

  test('the number inputs carry the policy bounds as min/max', async () => {
    renderApp(
      HOURS,
      authedClient('owner', {
        hours: { get: vi.fn(async () => ok(hoursSettings())) },
      }),
    );
    const leadTime = await screen.findByLabelText('Lead time (minutes)');
    expect(leadTime).toHaveAttribute('min', '0');
    expect(leadTime).toHaveAttribute('max', '1440');
    const slot = screen.getByLabelText('Slot interval (minutes)');
    expect(slot).toHaveAttribute('min', '5');
    expect(slot).toHaveAttribute('max', '120');
    const lastOrder = screen.getByLabelText(
      'Last order before close (minutes)',
    );
    expect(lastOrder).toHaveAttribute('min', '0');
    expect(lastOrder).toHaveAttribute('max', '240');
    const daysAhead = screen.getByLabelText('Orders ahead (days)');
    expect(daysAhead).toHaveAttribute('min', '0');
    expect(daysAhead).toHaveAttribute('max', '30');
  });

  test('an out-of-bounds value blocks Save with an inline field error', async () => {
    renderApp(
      HOURS,
      authedClient('owner', {
        hours: { get: vi.fn(async () => ok(hoursSettings())) },
      }),
    );
    const slot = await screen.findByLabelText('Slot interval (minutes)');
    fireEvent.change(slot, { target: { value: '3' } });
    expect(
      screen.getByText('Use a value between 5 and 120.'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Save fulfillment settings' }),
    ).toBeDisabled();
  });
});
