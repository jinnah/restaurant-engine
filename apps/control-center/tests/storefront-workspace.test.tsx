import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
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
  versionPage,
  versionSummary,
} from './support/mockClient';

const BUSINESS = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';

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

describe('workspace navigation', () => {
  test('owners and managers see the Storefront section', async () => {
    renderApp(
      `/businesses/${BUSINESS}/menu`,
      authedClient('manager', {
        catalog: { getMenu: vi.fn(async () => ok({ categories: [] })) },
      }),
    );
    expect(
      await screen.findByRole('link', { name: 'Storefront' }),
    ).toBeInTheDocument();
  });

  test('staff see no Storefront navigation at all', async () => {
    renderApp(
      `/businesses/${BUSINESS}/menu`,
      authedClient('staff', {
        catalog: { getMenu: vi.fn(async () => ok({ categories: [] })) },
      }),
    );
    await screen.findAllByRole('link', { name: 'Menu' });
    expect(
      screen.queryByRole('link', { name: 'Storefront' }),
    ).not.toBeInTheDocument();
  });

  test('a staff deep link explains the denial without a doomed request', async () => {
    const client = authedClient('staff');
    renderApp(`/businesses/${BUSINESS}/storefront`, client);
    expect(
      await screen.findByText(
        'Storefront management is available to owners and managers. Your role does not include it.',
      ),
    ).toBeInTheDocument();
    expect(client.storefront.get).not.toHaveBeenCalled();
  });
});

describe('overview status facts', () => {
  test('first use: no draft, never published, honest setup copy', async () => {
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () => ok(storefrontOverview())),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront`, client);
    expect(await screen.findByText('No draft yet')).toBeInTheDocument();
    expect(screen.getByText('Never published')).toBeInTheDocument();
    expect(
      screen.getByText(/has not been set up yet/, { exact: false }),
    ).toBeInTheDocument();
  });

  test('saved draft and published version render server facts only', async () => {
    const published = {
      id: '33333333-3333-4333-8333-333333333331',
      version_number: 4,
      design_variant: 'classic' as const,
      schema_version: 1,
      published_at: '2026-07-30T09:00:00Z',
      published_by_user_id: '2f6b8d4e-1a3c-4f5b-8e9d-0c1a2b3c4d5e',
    };
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({
                lock_version: 7,
                source_version_id: published.id,
              }),
              published,
            }),
          ),
        ),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront`, client);
    expect(await screen.findByText(/Last saved/)).toBeInTheDocument();
    expect(screen.getByText(/Version 4 —/)).toBeInTheDocument();
    expect(
      screen.getByText('This draft started from published version 4.'),
    ).toBeInTheDocument();
    // lock_version lives in a collapsed diagnostics disclosure, not in
    // normal prominence.
    expect(screen.getByText(/Draft lock version 7/)).toBeInTheDocument();
    expect(screen.getByText('Diagnostics')).toBeInTheDocument();
    // No invented claims anywhere (ADR-022 §9).
    expect(screen.queryByText(/edited since/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/unpublished changes/i)).not.toBeInTheDocument();
  });

  test('restore provenance resolves the archived source version number', async () => {
    const sourceId = '44444444-4444-4444-8444-444444444442';
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () =>
          ok(
            storefrontOverview({
              draft: draftView({ source_version_id: sourceId }),
              published: null,
            }),
          ),
        ),
        getVersion: vi.fn(async () =>
          ok(
            versionDetail({
              id: sourceId,
              version_number: 2,
              state: 'archived',
            }),
          ),
        ),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront`, client);
    expect(
      await screen.findByText('This draft was restored from version 2.'),
    ).toBeInTheDocument();
  });

  test('a closed business is readable with the read-only note', async () => {
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
  });
});

describe('history', () => {
  test('lists versions newest first with state badges and detail links', async () => {
    const client = authedClient('manager', {
      storefront: {
        listVersions: vi.fn(async () =>
          ok(
            versionPage([
              versionSummary({ version_number: 3, state: 'published' }),
              versionSummary({
                id: '33333333-3333-4333-8333-333333333332',
                version_number: 2,
                state: 'archived',
              }),
            ]),
          ),
        ),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront/history`, client);
    expect(
      await screen.findByRole('link', { name: 'Version 3' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Published')).toBeInTheDocument();
    expect(screen.getByText('Archived')).toBeInTheDocument();
    expect(screen.getByText('Showing 1–2 of 2')).toBeInTheDocument();
  });

  test('empty history is honest', async () => {
    const client = authedClient('owner', {
      storefront: {
        listVersions: vi.fn(async () => ok(versionPage([]))),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront/history`, client);
    expect(
      await screen.findByText(/Nothing has been published yet/),
    ).toBeInTheDocument();
  });

  test('pagination requests the next offset', async () => {
    const listVersions = vi.fn(async () =>
      ok(
        versionPage([versionSummary({ version_number: 21 })], {
          total: 25,
          offset: 0,
        }),
      ),
    );
    const client = authedClient('owner', { storefront: { listVersions } });
    renderApp(`/businesses/${BUSINESS}/storefront/history`, client);
    const older = await screen.findByRole('button', { name: 'Older' });
    listVersions.mockImplementationOnce(async () =>
      ok(
        versionPage([versionSummary({ version_number: 1 })], {
          total: 25,
          offset: 20,
        }),
      ),
    );
    fireEvent.click(older);
    await waitFor(() => {
      expect(listVersions).toHaveBeenLastCalledWith(BUSINESS, {
        limit: 20,
        offset: 20,
      });
    });
  });
});

describe('version detail', () => {
  test('renders metadata and the section summary, hidden sections badged', async () => {
    const client = authedClient('owner', {
      storefront: {
        getVersion: vi.fn(async () =>
          ok(
            versionDetail({
              version_number: 2,
              state: 'archived',
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
                    props: { heading: 'Welcome', primary_action: 'none' },
                  },
                  {
                    id: 'story',
                    type: 'story',
                    enabled: false,
                    props: { heading: 'Our story', body: 'Body.' },
                  },
                ],
              },
            }),
          ),
        ),
      },
    });
    renderApp(
      `/businesses/${BUSINESS}/storefront/history/33333333-3333-4333-8333-333333333331`,
      client,
    );
    expect(
      await screen.findByRole('heading', { name: /Version 2 \(archived\)/ }),
    ).toBeInTheDocument();
    expect(screen.getByText('Hero')).toBeInTheDocument();
    expect(screen.getByText('Welcome')).toBeInTheDocument();
    expect(screen.getByText('Hidden')).toBeInTheDocument();
  });

  test('an unknown, foreign, or draft id is one neutral not-found', async () => {
    const client = authedClient('owner');
    renderApp(
      `/businesses/${BUSINESS}/storefront/history/99999999-9999-4999-8999-999999999999`,
      client,
    );
    expect(
      await screen.findByText('This version could not be found.'),
    ).toBeInTheDocument();
  });
});

describe('saved-draft preview', () => {
  test('renders the projection through the shared renderer with inert links', async () => {
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () => ok(storefrontOverview({ draft: draftView() }))),
        preview: vi.fn(async () =>
          ok(
            previewProjection({
              sections: [
                {
                  id: 'hero',
                  type: 'hero',
                  props: {
                    heading: 'Neighborhood kitchen',
                    subheading: null,
                    image: null,
                    primary_action: 'view_menu',
                  },
                },
                {
                  id: 'menu',
                  type: 'menu',
                  props: { heading: 'Our menu', intro: null },
                },
              ],
            }),
          ),
        ),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront/preview`, client);

    // The projection renders through the real shared renderer: tenant
    // chrome (business name) plus the sections.
    expect(await screen.findByText('Neighborhood kitchen')).toBeInTheDocument();
    expect(screen.getByText('Our menu')).toBeInTheDocument();

    // Inert link mode: the navigation texts exist but expose no link role
    // and no href — no navigable anchor or activation path exists.
    for (const label of ['View menu', 'View the full menu']) {
      const element = screen.getByText(label);
      expect(element).toBeInTheDocument();
      expect(
        screen.queryByRole('link', { name: label }),
      ).not.toBeInTheDocument();
      expect(element.closest('a')).not.toHaveAttribute('href');
    }

    // Honest captions: saved draft, disabled links, live-menu fidelity.
    expect(screen.getByText(/last/)).toBeInTheDocument();
    expect(
      screen.getByText(/Links are disabled in this preview/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Featured menu items come from your live menu/),
    ).toBeInTheDocument();
  });

  test('without a draft the preview explains instead of requesting', async () => {
    const client = authedClient('owner', {
      storefront: {
        get: vi.fn(async () => ok(storefrontOverview())),
      },
    });
    renderApp(`/businesses/${BUSINESS}/storefront/preview`, client);
    expect(
      await screen.findByText(/There is no draft to preview yet/),
    ).toBeInTheDocument();
    expect(client.storefront.preview).not.toHaveBeenCalled();
  });
});
