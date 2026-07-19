import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { vi, expect, test } from 'vitest';
import type { AuditEventSummary } from '@restaurant-engine/api-client';
import { adminSessionView, makeClient, ok } from './support/mockClient';
import { renderApp } from './support/render';

function auditEvent(
  overrides: Partial<AuditEventSummary> = {},
): AuditEventSummary {
  return {
    id: 42,
    action: 'business.created',
    actor_user_id: '9c1e5b7a-3d2f-4a6b-8c0d-1e2f3a4b5c6d',
    business_id: '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001',
    target_type: 'business',
    target_id: '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001',
    occurred_at: '2026-07-19T00:00:00Z',
    correlation_id: null,
    details: { name: 'Shalik' },
    ...overrides,
  };
}

function adminClient(overrides: Parameters<typeof makeClient>[0] = {}) {
  return makeClient({
    auth: { getSession: vi.fn(async () => ok(adminSessionView())) },
    ...overrides,
  });
}

test('the audit stream renders events with actor, scope, and details', async () => {
  const listAuditEvents = vi.fn(async () =>
    ok({
      items: [
        auditEvent(),
        auditEvent({
          id: 41,
          action: 'auth.login_succeeded',
          business_id: null,
          target_type: null,
          target_id: null,
          details: null,
        }),
      ],
      next_before_id: null,
    }),
  );
  renderApp('/platform/audit', adminClient({ platform: { listAuditEvents } }));

  const list = await screen.findByRole('list', { name: /audit events/i });
  expect(within(list).getByText('business.created')).toBeInTheDocument();
  expect(within(list).getByText(/name: Shalik/)).toBeInTheDocument();
  expect(within(list).getByText('auth.login_succeeded')).toBeInTheDocument();
  expect(within(list).getByText(/platform scope/)).toBeInTheDocument();
  expect(listAuditEvents).toHaveBeenCalledWith(
    expect.objectContaining({ limit: 50, beforeId: undefined }),
  );
  // A fully consumed stream offers no load-more.
  expect(screen.queryByRole('button', { name: /load older/i })).toBeNull();
});

test('load-more follows the cursor and appends older events', async () => {
  const listAuditEvents = vi
    .fn()
    .mockResolvedValueOnce(
      ok({
        items: [auditEvent({ id: 42, action: 'business.created' })],
        next_before_id: 42,
      }),
    )
    .mockResolvedValueOnce(
      ok({
        items: [auditEvent({ id: 7, action: 'auth.logout', details: null })],
        next_before_id: null,
      }),
    );
  renderApp('/platform/audit', adminClient({ platform: { listAuditEvents } }));

  const list = await screen.findByRole('list', { name: /audit events/i });
  await within(list).findByText('business.created');
  fireEvent.click(screen.getByRole('button', { name: /load older events/i }));

  expect(await within(list).findByText('auth.logout')).toBeInTheDocument();
  // Newer events remain rendered above the appended page.
  expect(within(list).getByText('business.created')).toBeInTheDocument();
  expect(listAuditEvents).toHaveBeenLastCalledWith(
    expect.objectContaining({ beforeId: 42 }),
  );
  expect(screen.queryByRole('button', { name: /load older/i })).toBeNull();
});

test('applying filters queries with them and resets the stream', async () => {
  const listAuditEvents = vi
    .fn()
    .mockResolvedValueOnce(ok({ items: [auditEvent()], next_before_id: null }))
    .mockResolvedValueOnce(
      ok({
        items: [auditEvent({ id: 10, action: 'business.suspended' })],
        next_before_id: null,
      }),
    );
  renderApp('/platform/audit', adminClient({ platform: { listAuditEvents } }));

  const list = await screen.findByRole('list', { name: /audit events/i });
  await within(list).findByText('business.created');
  fireEvent.change(screen.getByLabelText(/^action$/i), {
    target: { value: 'business.suspended' },
  });
  fireEvent.change(screen.getByLabelText(/business id/i), {
    target: { value: '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001' },
  });
  fireEvent.click(screen.getByRole('button', { name: /apply filters/i }));

  // The filtered query replaces the list element; re-query it fresh.
  await waitFor(() => {
    const refreshed = screen.getByRole('list', { name: /audit events/i });
    expect(
      within(refreshed).getByText('business.suspended'),
    ).toBeInTheDocument();
  });
  expect(listAuditEvents).toHaveBeenLastCalledWith(
    expect.objectContaining({
      action: 'business.suspended',
      businessId: '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001',
      beforeId: undefined,
    }),
  );
});

test('refresh explicitly refetches the stream', async () => {
  const listAuditEvents = vi
    .fn()
    .mockResolvedValueOnce(ok({ items: [], next_before_id: null }))
    .mockResolvedValueOnce(
      ok({ items: [auditEvent({ id: 50 })], next_before_id: null }),
    );
  renderApp('/platform/audit', adminClient({ platform: { listAuditEvents } }));

  expect(await screen.findByText(/no audit events match/i)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /refresh/i }));
  const list = await screen.findByRole('list', { name: /audit events/i });
  expect(within(list).getByText('business.created')).toBeInTheDocument();
  await waitFor(() => {
    expect(listAuditEvents).toHaveBeenCalledTimes(2);
  });
});
