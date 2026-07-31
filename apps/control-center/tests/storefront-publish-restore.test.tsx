import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import { storefrontKeys } from '../src/storefront/keys';
import { renderApp } from './support/render';
import {
  draftView,
  makeClient,
  membership,
  ok,
  previewProjection,
  sessionView,
  storefrontOverview,
  versionDetail,
} from './support/mockClient';

const BUSINESS = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';
const ARCHIVED = '33333333-3333-4333-8333-333333333332';

function authedClient(
  role: 'owner' | 'manager',
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

describe('publishing (owner only, saved non-dirty draft, explicit confirmation)', () => {
  test('publish confirms, carries the saved lock version, and applies the returned overview', async () => {
    const publish = vi.fn(async () =>
      ok(
        storefrontOverview({
          draft: draftView({ lock_version: 0 }),
          published: {
            id: '33333333-3333-4333-8333-333333333331',
            version_number: 1,
            design_variant: 'classic' as const,
            schema_version: 1,
            published_at: '2026-07-30T12:00:00Z',
            published_by_user_id: '2f6b8d4e-1a3c-4f5b-8e9d-0c1a2b3c4d5e',
          },
        }),
      ),
    );
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () =>
          ok(storefrontOverview({ draft: draftView({ lock_version: 5 }) })),
        ),
        publish,
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront`, client);

    fireEvent.click(await screen.findByRole('button', { name: 'Publish…' }));
    const dialog = await screen.findByRole('dialog');
    expect(
      within(dialog).getByText(/makes this saved draft your live storefront/),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Publish' }));

    await waitFor(() => {
      expect(publish).toHaveBeenCalledTimes(1);
    });
    const [, body] = publish.mock.calls[0] as unknown as [
      string,
      { expected_lock_version: number },
    ];
    expect(body.expected_lock_version).toBe(5);
    expect(
      await screen.findByText('Storefront published.'),
    ).toBeInTheDocument();
    // The returned overview is authoritative: version 1 now shows.
    expect(await screen.findByText(/Version 1 —/)).toBeInTheDocument();
  });

  test('a dirty draft disables publishing and says why', async () => {
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({
                lock_version: 2,
                config: {
                  schema_version: 1,
                  theme: {
                    accent: '#a34b2a',
                    palette: 'warm',
                    type_pairing: 'humanist',
                  },
                  sections: [
                    {
                      id: 'hero',
                      type: 'hero',
                      enabled: true,
                      props: {
                        heading: 'Welcome',
                        subheading: null,
                        image: null,
                        primary_action: 'none',
                      },
                    },
                  ],
                },
              }),
            }),
          ),
        ),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront`, client);
    expect(
      await screen.findByRole('button', { name: 'Publish…' }),
    ).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: 'Edit Hero' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Heading'), {
      target: { value: 'Edited' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply' }));

    expect(
      await screen.findByText(/Save your draft before publishing/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Publish…' })).toBeDisabled();
    // No hidden auto-publish anywhere: nothing was called.
    expect(client.storefront.publish).not.toHaveBeenCalled();
  });

  test('managers see no publish affordance', async () => {
    const client = authedClient('manager', {
      storefront: {
        get: vi.fn(async () => ok(storefrontOverview({ draft: draftView() }))),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront`, client);
    expect(
      await screen.findByRole('button', { name: 'Save draft' }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Publish…' })).toBeNull();
  });

  test('a closed business offers no mutations at all', async () => {
    const client = authedClient(
      'owner',
      {
        storefront: {
          get: vi.fn(async () =>
            ok(storefrontOverview({ draft: draftView() })),
          ),
        },
      },
      'closed',
    );
    renderApp(`/businesses/${BUSINESS}/storefront`, client);
    expect(
      await screen.findByText(/closed, so the storefront is read-only/),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save draft' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Publish…' })).toBeNull();
  });
});

describe('restore (archived only, fresh concurrency state, never publishes)', () => {
  function archivedDetailClient(
    role: 'owner' | 'manager',
    overrides: Parameters<typeof makeClient>[0] = {},
  ) {
    return authedClient(role, {
      storefront: {
        getVersion: vi.fn(async () =>
          ok(
            versionDetail({
              id: ARCHIVED,
              version_number: 2,
              state: 'archived',
            }),
          ),
        ),
        ...overrides.storefront,
      },
      ...overrides,
    });
  }

  test('restore refetches the overview when the dialog opens and uses the fresh lock version', async () => {
    const get = vi.fn(async () =>
      ok(storefrontOverview({ draft: draftView({ lock_version: 3 }) })),
    );
    const restoreVersion = vi.fn(async () =>
      ok(draftView({ lock_version: 4, source_version_id: ARCHIVED })),
    );
    const client = archivedDetailClient('owner', {
      storefront: {
        getVersion: vi.fn(async () =>
          ok(
            versionDetail({
              id: ARCHIVED,
              version_number: 2,
              state: 'archived',
            }),
          ),
        ),
        get,
        restoreVersion,
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront/history/${ARCHIVED}`, client);

    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Restore this version to the draft',
      }),
    );
    // The dialog fetched fresh state; a newer lock arrives before confirm.
    get.mockImplementation(async () =>
      ok(storefrontOverview({ draft: draftView({ lock_version: 7 }) })),
    );

    // The dialog swaps from its loading shell to the confirmation once the
    // fresh overview arrives, so queries go through screen, not a captured
    // (and by then detached) dialog node.
    expect(
      await screen.findByText(/replaces your current draft/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /publish anything, and your version history is unchanged/,
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Restore to draft' }));
    await waitFor(() => {
      expect(restoreVersion).toHaveBeenCalledTimes(1);
    });
    const [, versionId, body] = restoreVersion.mock.calls[0] as unknown as [
      string,
      string,
      { expected_lock_version: number },
    ];
    expect(versionId).toBe(ARCHIVED);
    // The dialog's mount-time refetch supplied lock 3 (the later change to
    // 7 arrived after the dialog snapshot — the server's 409 remains the
    // authority if it went stale).
    expect(body.expected_lock_version).toBe(3);
    // Returned to the editor for review; nothing was published.
    expect(
      await screen.findByText('Version 2 restored to your draft.'),
    ).toBeInTheDocument();
    expect(client.storefront.publish).not.toHaveBeenCalled();
  });

  test('with no draft the dialog explains instead of guessing a lock version', async () => {
    const client = archivedDetailClient('owner', {
      storefront: {
        getVersion: vi.fn(async () =>
          ok(
            versionDetail({
              id: ARCHIVED,
              version_number: 2,
              state: 'archived',
            }),
          ),
        ),
        get: vi.fn(async () => ok(storefrontOverview())),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront/history/${ARCHIVED}`, client);
    fireEvent.click(
      await screen.findByRole('button', {
        name: 'Restore this version to the draft',
      }),
    );
    expect(
      await screen.findByText(/needs an existing draft to restore into/),
    ).toBeInTheDocument();
    expect(client.storefront.restoreVersion).not.toHaveBeenCalled();
  });

  test('managers see no restore affordance; the published row offers none either', async () => {
    const client = archivedDetailClient('manager');
    renderApp(`/businesses/${BUSINESS}/storefront/history/${ARCHIVED}`, client);
    expect(
      await screen.findByRole('heading', { name: /Version 2 \(archived\)/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('button', {
        name: 'Restore this version to the draft',
      }),
    ).toBeNull();
  });
});

describe('no stale preview flash (ADR-022 §6)', () => {
  test('a cached projection for an older draft is never rendered for a newer one', async () => {
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({
                lock_version: 5,
                updated_at: '2026-07-30T11:00:00Z',
              }),
            }),
          ),
        ),
        preview: vi.fn(async () =>
          ok(
            previewProjection({
              sections: [
                {
                  id: 'hero',
                  type: 'hero',
                  props: {
                    heading: 'Fresh projection',
                    subheading: null,
                    image: null,
                    primary_action: 'none',
                  },
                },
              ],
            }),
          ),
        ),
      },
    });
    const { queryClient } = renderApp(
      `/businesses/${BUSINESS}/storefront/preview`,
      client,
    );
    // A projection for the PREVIOUS draft sits in the cache under its own
    // key. The page must never render it for the current draft.
    queryClient.setQueryData(
      storefrontKeys.preview(BUSINESS, 4, '2026-07-30T10:00:00Z'),
      previewProjection({
        sections: [
          {
            id: 'hero',
            type: 'hero',
            props: {
              heading: 'Stale projection',
              subheading: null,
              image: null,
              primary_action: 'none',
            },
          },
        ],
      }),
    );

    expect(await screen.findByText('Fresh projection')).toBeInTheDocument();
    expect(screen.queryByText('Stale projection')).toBeNull();
  });

  test('saving removes every cached preview projection', async () => {
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () =>
          ok(storefrontOverview({ draft: draftView({ lock_version: 2 }) })),
        ),
        putDraft: vi.fn(async () => ok(draftView({ lock_version: 3 }))),
      },
    });
    const { queryClient } = renderApp(
      `/businesses/${BUSINESS}/storefront`,
      client,
    );
    await screen.findByRole('heading', { name: 'Draft' });
    queryClient.setQueryData(
      storefrontKeys.preview(BUSINESS, 2, draftView().updated_at),
      previewProjection(),
    );

    // Dirty the form, then save.
    fireEvent.click(screen.getByRole('button', { name: 'Add menu section' }));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Heading'), {
      target: { value: 'Our menu' },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Save draft' }));
    await screen.findByText('Draft saved.');

    expect(
      queryClient.getQueriesData({
        queryKey: storefrontKeys.previewRoot(BUSINESS),
      }),
    ).toHaveLength(0);
  });
});
