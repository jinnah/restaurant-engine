import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import { renderApp } from './support/render';
import {
  apiError,
  draftView,
  envelope,
  makeClient,
  membership,
  ok,
  sessionView,
  storefrontConfig,
  storefrontOverview,
} from './support/mockClient';

const BUSINESS = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';

function ownerClient(
  overrides: Parameters<typeof makeClient>[0] = {},
  businessStatus = 'active',
) {
  return makeClient({
    auth: {
      getSession: vi.fn(async () =>
        ok(
          sessionView({
            memberships: [
              membership({ role: 'owner', business_status: businessStatus }),
            ],
          }),
        ),
      ),
    },
    ...overrides,
  });
}

function contactConfig() {
  return storefrontConfig({
    sections: [
      {
        id: 'contact',
        type: 'contact',
        enabled: true,
        props: {
          heading: 'Find us',
          address_lines: ['12 Main Street', 'Buffalo, NY 14201'],
          phone: null,
          email: null,
        },
      },
    ],
  });
}

function galleryConfig() {
  return storefrontConfig({
    sections: [
      {
        id: 'gallery',
        type: 'gallery',
        enabled: true,
        props: {
          heading: 'Gallery',
          images: [
            {
              media_id: '00000000-0000-4000-8000-0000000000a1',
              alt_text: 'First dish',
            },
            {
              media_id: '00000000-0000-4000-8000-0000000000a2',
              alt_text: null,
            },
          ],
        },
      },
    ],
  });
}

describe('dialog structure and focus', () => {
  test('no native form is ever nested inside another (and the editor needs none)', async () => {
    const client = ownerClient({
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ config: contactConfig() }),
            }),
          ),
        ),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront`, client);
    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit Contact' }),
    );
    await screen.findByRole('dialog');
    expect(document.querySelectorAll('form form')).toHaveLength(0);
  });

  test('opening a section dialog moves focus into it; Escape returns it', async () => {
    const client = ownerClient({
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ config: contactConfig() }),
            }),
          ),
        ),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront`, client);
    const edit = await screen.findByRole('button', { name: 'Edit Contact' });
    // jsdom clicks do not move focus; give the trigger real focus so the
    // dialog's focus-return contract is observable.
    edit.focus();
    fireEvent.click(edit);
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveFocus();
    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(edit).toHaveFocus();
  });

  test('a failed save publishes a focused, announced error summary', async () => {
    const client = ownerClient({
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ config: contactConfig() }),
            }),
          ),
        ),
        putDraft: vi.fn(async () =>
          apiError(
            422,
            envelope('validation_error', 'One media reference is not usable.'),
          ),
        ),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront`, client);
    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit Contact' }),
    );
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Heading'), {
      target: { value: 'Visit us' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Save draft' }));

    const alert = await screen.findByText('One media reference is not usable.');
    const summary = alert.closest('[role="alert"]');
    expect(summary).not.toBeNull();
    expect(summary).toHaveFocus();
  });
});

describe('contact address lines (the contract-pinned affordance)', () => {
  test('the add control disables at four lines and says why', async () => {
    const client = ownerClient({
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ config: contactConfig() }),
            }),
          ),
        ),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront`, client);
    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit Contact' }),
    );
    const dialog = await screen.findByRole('dialog');
    const add = within(dialog).getByRole('button', {
      name: 'Add address line',
    });
    fireEvent.click(add); // 3
    fireEvent.click(add); // 4
    expect(add).toBeDisabled();
    expect(
      within(dialog).getByText('An address can have up to 4 lines.'),
    ).toBeInTheDocument();
    // Removing a line re-enables the affordance.
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Remove address line 4' }),
    );
    expect(add).toBeEnabled();
  });
});

describe('gallery editing', () => {
  test('reorders and removes staged photos with keyboard-reachable controls', async () => {
    const client = ownerClient({
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ config: galleryConfig() }),
            }),
          ),
        ),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront`, client);
    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit Gallery' }),
    );
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('First dish')).toBeInTheDocument();
    expect(within(dialog).getByText('Marked decorative')).toBeInTheDocument();

    // Move the first photo down, then remove it.
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Move photo 1 down' }),
    );
    const rows = within(dialog).getAllByRole('listitem');
    expect(within(rows[1] as HTMLElement).getByText('First dish')).toBeTruthy();
    fireEvent.click(
      within(dialog).getByRole('button', { name: 'Remove photo 2' }),
    );
    expect(within(dialog).queryByText('First dish')).toBeNull();
  });

  test('the storefront picker stages a selection and states the claim contract', async () => {
    const client = ownerClient({
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ config: galleryConfig() }),
            }),
          ),
        ),
      },
      media: {
        listAssets: vi.fn(async () =>
          ok({
            items: [
              {
                id: '00000000-0000-4000-8000-0000000000b1',
                kind: 'image' as const,
                original_filename: 'terrace.jpg',
                source_format: 'jpeg' as const,
                status: 'pending' as const,
                pending_expires_at: '2026-08-01T00:00:00Z',
                byte_size: 12345,
                width: 800,
                height: 600,
                variants: [],
                created_at: '2026-07-30T00:00:00Z',
                updated_at: '2026-07-30T00:00:00Z',
              },
            ],
            total: 1,
            limit: 50,
            offset: 0,
          }),
        ),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront`, client);
    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit Gallery' }),
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Add photo' }));

    // The picker replaced the section dialog (never two focus traps).
    expect(await screen.findByText('terrace.jpg')).toBeInTheDocument();
    expect(screen.queryByText('Photos')).toBeNull();
    // Pending honesty and the staging contract, verbatim concerns of E-11.
    expect(screen.getByText(/Not used yet — expires/)).toBeInTheDocument();
    expect(
      screen.getByText(/kept in the editor until you save the draft/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/nothing becomes public until you publish/),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByText('terrace.jpg'));
    fireEvent.click(
      screen.getByLabelText(
        'This image is decorative — it adds nothing beyond the surrounding text',
      ),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Use this image' }));

    // Back in the section dialog with the staged third photo; nothing was
    // saved or claimed (no PUT happened).
    expect(await screen.findByText('Photos')).toBeInTheDocument();
    expect(
      screen.getAllByText('Marked decorative').length,
    ).toBeGreaterThanOrEqual(2);
    expect(client.storefront.putDraft).not.toHaveBeenCalled();
  });
});

describe('dirty-navigation protection', () => {
  test('leaving the editor with unsaved changes asks first', async () => {
    const client = ownerClient({
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ config: contactConfig() }),
            }),
          ),
        ),
      },
      catalog: { getMenu: vi.fn(async () => ok({ categories: [] })) },
    });
    const { router } = renderApp(`/businesses/${BUSINESS}/storefront`, client);
    fireEvent.click(
      await screen.findByRole('button', { name: 'Edit Contact' }),
    );
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Heading'), {
      target: { value: 'Changed' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply' }));
    await screen.findByText(/You have unsaved changes/);
    // The banner and the guard read the same dirty flag, but the guard
    // reaches the router through an effect: react-router re-registers the
    // blocker function *after* the commit that painted the banner. Give
    // React that turn before navigating — on a loaded CI runner the
    // navigation could otherwise outrun the registration and slip through
    // unblocked, which is what made this test intermittent (twice
    // observed: runs 30652179044 and 30810894048).
    await act(async () => {});

    void router.navigate(`/businesses/${BUSINESS}/menu`);
    expect(
      await screen.findByText('Your storefront draft has unsaved changes.'),
    ).toBeInTheDocument();
    // Blocked means blocked: the route has not moved while the question
    // is on screen.
    expect(router.state.location.pathname).toBe(
      `/businesses/${BUSINESS}/storefront`,
    );
    // Staying keeps the route and the values.
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(
        `/businesses/${BUSINESS}/storefront`,
      );
    });
    expect(screen.getByText('Changed')).toBeInTheDocument();
  });
});

describe('failure presentation', () => {
  test('a network failure renders the retryable error panel', async () => {
    const get = vi.fn(
      async (): Promise<
        ReturnType<
          typeof ok<import('@restaurant-engine/api-client').StorefrontOverview>
        >
      > => apiError(null),
    );
    const client = ownerClient({ storefront: { get } });
    renderApp(`/businesses/${BUSINESS}/storefront`, client);
    expect(
      await screen.findByText('The storefront could not be loaded.'),
    ).toBeInTheDocument();
    get.mockImplementation(async () =>
      ok(storefrontOverview({ draft: draftView() })),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText(/Last saved/)).toBeInTheDocument();
  });

  test('an unexpected 403 renders honestly instead of being treated as impossible', async () => {
    const client = ownerClient({
      storefront: {
        get: vi.fn(async () =>
          apiError(
            403,
            envelope(
              'permission_denied',
              'You do not have permission to do that.',
            ),
          ),
        ),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront`, client);
    expect(
      await screen.findByText('The storefront could not be loaded.'),
    ).toBeInTheDocument();
  });
});
