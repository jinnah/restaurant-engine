import { fireEvent, screen, waitFor } from '@testing-library/react';
import { vi, expect, test } from 'vitest';
import {
  adminSessionView,
  apiError,
  business,
  envelope,
  makeClient,
  ok,
} from './support/mockClient';
import { renderApp } from './support/render';

function adminClient(overrides: Parameters<typeof makeClient>[0] = {}) {
  return makeClient({
    auth: { getSession: vi.fn(async () => ok(adminSessionView())) },
    ...overrides,
  });
}

function page(
  items: ReturnType<typeof business>[],
  total: number,
  limit = 25,
  offset = 0,
) {
  return ok({ items, total, limit, offset });
}

test('the businesses list renders rows with status badges', async () => {
  const listBusinesses = vi.fn(async () =>
    page(
      [
        business({ id: 'b1', name: 'Shalik', slug: 'shalik' }),
        business({
          id: 'b2',
          name: 'Mayer Doa',
          slug: 'mayer-doa',
          status: 'active',
        }),
      ],
      2,
    ),
  );
  renderApp(
    '/platform/businesses',
    adminClient({ platform: { listBusinesses } }),
  );

  expect(
    await screen.findByRole('link', { name: /shalik/i }),
  ).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /mayer doa/i })).toBeInTheDocument();
  expect(screen.getByText('provisioning')).toBeInTheDocument();
  expect(screen.getByText('active')).toBeInTheDocument();
  expect(listBusinesses).toHaveBeenCalledWith({ limit: 25, offset: 0 });
});

test('an empty platform shows the honest empty state', async () => {
  const listBusinesses = vi.fn(async () => page([], 0));
  renderApp(
    '/platform/businesses',
    adminClient({ platform: { listBusinesses } }),
  );
  expect(
    await screen.findByText(/no businesses exist yet/i),
  ).toBeInTheDocument();
});

test('pagination requests the next offset and disables edges', async () => {
  const listBusinesses = vi
    .fn()
    .mockResolvedValueOnce(
      page([business({ id: 'b1', name: 'First Page Biz' })], 26, 25, 0),
    )
    .mockResolvedValueOnce(
      page([business({ id: 'b26', name: 'Second Page Biz' })], 26, 25, 25),
    );
  renderApp(
    '/platform/businesses',
    adminClient({ platform: { listBusinesses } }),
  );

  await screen.findByRole('link', { name: /first page biz/i });
  expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled();
  expect(screen.getByText(/showing 1–1 of 26/i)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: /next/i }));
  await screen.findByRole('link', { name: /second page biz/i });
  expect(listBusinesses).toHaveBeenLastCalledWith({ limit: 25, offset: 25 });
  expect(screen.getByRole('button', { name: /next/i })).toBeDisabled();
  expect(screen.getByRole('button', { name: /previous/i })).toBeEnabled();
});

test('a failed list load is retryable', async () => {
  const listBusinesses = vi
    .fn()
    .mockResolvedValueOnce(apiError(503, null))
    .mockResolvedValueOnce(page([business({ name: 'Recovered Biz' })], 1));
  renderApp(
    '/platform/businesses',
    adminClient({ platform: { listBusinesses } }),
  );

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent(/could not be loaded/i);
  fireEvent.click(screen.getByRole('button', { name: /try again/i }));
  expect(
    await screen.findByRole('link', { name: /recovered biz/i }),
  ).toBeInTheDocument();
});

test('creating a business sends the CSRF token and refreshes the list', async () => {
  const created = business({ id: 'new-1', name: 'Fresh Biz', slug: 'fresh' });
  const createBusiness = vi.fn(async () => ok(created, 201));
  const listBusinesses = vi
    .fn()
    .mockResolvedValueOnce(page([], 0))
    .mockResolvedValue(page([created], 1));
  renderApp(
    '/platform/businesses',
    adminClient({ platform: { createBusiness, listBusinesses } }),
  );

  await screen.findByText(/no businesses exist yet/i);
  fireEvent.change(screen.getByLabelText(/name/i), {
    target: { value: 'Fresh Biz' },
  });
  fireEvent.change(screen.getByLabelText(/slug/i), {
    target: { value: 'fresh' },
  });
  fireEvent.click(screen.getByRole('button', { name: /create business/i }));

  expect(await screen.findByRole('status')).toHaveTextContent(
    /business created/i,
  );
  expect(createBusiness).toHaveBeenCalledWith(
    { name: 'Fresh Biz', slug: 'fresh' },
    'csrf-token-1',
  );
  // Success cleared the form and refreshed the list.
  expect(screen.getByLabelText(/name/i)).toHaveValue('');
  expect(
    await screen.findByRole('link', { name: /fresh biz/i }),
  ).toBeInTheDocument();
});

test('a slug conflict lands on the slug field', async () => {
  const createBusiness = vi.fn(async () =>
    apiError(409, envelope('conflict', 'That slug is already in use.')),
  );
  const listBusinesses = vi.fn(async () => page([], 0));
  renderApp(
    '/platform/businesses',
    adminClient({ platform: { createBusiness, listBusinesses } }),
  );

  await screen.findByText(/no businesses exist yet/i);
  fireEvent.change(screen.getByLabelText(/name/i), {
    target: { value: 'Dup' },
  });
  fireEvent.change(screen.getByLabelText(/slug/i), {
    target: { value: 'shalik' },
  });
  fireEvent.click(screen.getByRole('button', { name: /create business/i }));

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent(/some fields need attention/i);
  expect(alert).toHaveFocus();
  const slugInput = screen.getByLabelText(/slug/i);
  expect(slugInput).toHaveAccessibleDescription(/already in use/i);
  expect(slugInput).toHaveAttribute('aria-invalid', 'true');
});

test('422 field errors map to their inputs', async () => {
  const createBusiness = vi.fn(async () =>
    apiError(
      422,
      envelope('validation_error', 'Validation failed.', [
        { field: 'body.slug', code: 'pattern', message: 'Use a-z, 0-9, -.' },
      ]),
    ),
  );
  const listBusinesses = vi.fn(async () => page([], 0));
  renderApp(
    '/platform/businesses',
    adminClient({ platform: { createBusiness, listBusinesses } }),
  );

  await screen.findByText(/no businesses exist yet/i);
  fireEvent.change(screen.getByLabelText(/name/i), {
    target: { value: 'X' },
  });
  fireEvent.change(screen.getByLabelText(/slug/i), {
    target: { value: 'BAD SLUG' },
  });
  fireEvent.click(screen.getByRole('button', { name: /create business/i }));

  await screen.findByRole('alert');
  expect(screen.getByLabelText(/slug/i)).toHaveAccessibleDescription(
    /use a-z/i,
  );
});

test('a privileged 401 on the list clears the session and routes to login', async () => {
  const listBusinesses = vi.fn(async () =>
    apiError(401, envelope('authentication_required', 'Sign in required.')),
  );
  const { router } = renderApp(
    '/platform/businesses',
    adminClient({ platform: { listBusinesses } }),
  );

  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/login');
  });
  expect(router.state.location.search).toBe(
    '?next=' + encodeURIComponent('/platform/businesses'),
  );
});
