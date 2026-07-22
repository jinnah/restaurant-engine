// The media workflow (M3E, ADR-018 ruling 9/10): uploading, attaching,
// detaching, and deleting are four different operations, and the alt-text
// contract is followed exactly.

import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, test, vi } from 'vitest';
import {
  adminMenu,
  apiError,
  business,
  category,
  envelope,
  item,
  makeClient,
  membership,
  ok,
  sessionView,
} from './support/mockClient';
import { renderApp } from './support/render';
import { isUnsupportedType } from '../src/menu/mediaData';

const SHALIK = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';
const EDITOR = `/businesses/${SHALIK}/menu/items/i1`;

function asset(overrides: Record<string, unknown> = {}) {
  return {
    id: 'a1',
    kind: 'image' as const,
    status: 'active' as const,
    pending_expires_at: null,
    original_filename: 'samosa.jpg',
    source_format: 'jpeg' as const,
    width: 2000,
    height: 1500,
    byte_size: 100000,
    variants: [
      { variant: 'w320' as const, width: 320, height: 240, byte_size: 900 },
    ],
    created_at: '2026-07-21T00:00:00Z',
    updated_at: '2026-07-21T00:00:00Z',
    ...overrides,
  };
}

function client(
  currentItem = item({ id: 'i1', category_id: 'c1', name: 'Samosa' }),
  overrides: Parameters<typeof makeClient>[0] = {},
  role: 'owner' | 'staff' = 'owner',
) {
  return makeClient({
    auth: {
      getSession: vi.fn(async () =>
        ok(
          sessionView({
            memberships: [membership({ business_id: SHALIK, role })],
          }),
        ),
      ),
    },
    businesses: { get: vi.fn(async () => ok(business({ id: SHALIK }))) },
    ...overrides,
    catalog: {
      getMenu: vi.fn(async () =>
        ok(adminMenu([category({ id: 'c1', items: [currentItem] })])),
      ),
      getModifierGroups: vi.fn(async () => ok({ item_id: 'i1', groups: [] })),
      ...overrides.catalog,
    },
    media: {
      listAssets: vi.fn(async () =>
        ok({ items: [asset()], total: 1, limit: 50, offset: 0 }),
      ),
      ...overrides.media,
    },
  });
}

function pngFile(name = 'photo.png', type = 'image/png', size = 1000): File {
  const file = new File(['x'], name, { type });
  Object.defineProperty(file, 'size', { value: size });
  return file;
}

describe('client-side type screening is a courtesy, not the check', () => {
  test('a definitely-wrong stated type is refused', () => {
    expect(isUnsupportedType('application/pdf')).toBe(true);
    expect(isUnsupportedType('image/gif')).toBe(true);
    expect(isUnsupportedType('image/heic')).toBe(true);
  });

  test('accepted types pass, and an unknown type is left to the server', () => {
    expect(isUnsupportedType('image/jpeg')).toBe(false);
    expect(isUnsupportedType('image/png')).toBe(false);
    expect(isUnsupportedType('image/webp')).toBe(false);
    // Android pickers report '' for perfectly valid images; the backend's
    // magic-byte check is the authority.
    expect(isUnsupportedType('')).toBe(false);
  });
});

test('an unsupported file is refused without any request', async () => {
  const uploadAsset = vi.fn(async () => ok(asset()));
  renderApp(EDITOR, client(undefined, { media: { uploadAsset } }));

  fireEvent.click(await screen.findByRole('button', { name: 'Add a photo' }));
  fireEvent.change(screen.getByLabelText('Upload a new image'), {
    target: { files: [pngFile('doc.pdf', 'application/pdf')] },
  });

  expect(
    await screen.findByText(/choose a jpeg, png, or webp/i),
  ).toBeInTheDocument();
  expect(uploadAsset).not.toHaveBeenCalled();
});

test('a file with no stated type is still submitted for the server to judge', async () => {
  const uploadAsset = vi.fn(async () => ok(asset()));
  renderApp(EDITOR, client(undefined, { media: { uploadAsset } }));

  fireEvent.click(await screen.findByRole('button', { name: 'Add a photo' }));
  fireEvent.change(screen.getByLabelText('Upload a new image'), {
    target: { files: [pngFile('mystery', '')] },
  });

  await waitFor(() => {
    expect(uploadAsset).toHaveBeenCalledTimes(1);
  });
});

test('an oversize file warns but is still attempted', async () => {
  const uploadAsset = vi.fn(async () => ok(asset()));
  renderApp(EDITOR, client(undefined, { media: { uploadAsset } }));

  fireEvent.click(await screen.findByRole('button', { name: 'Add a photo' }));
  fireEvent.change(screen.getByLabelText('Upload a new image'), {
    target: { files: [pngFile('big.png', 'image/png', 15 * 1024 * 1024)] },
  });

  // The true cap is a deployment setting the client cannot see, so blocking
  // would reject files a 20 MiB deployment accepts.
  expect(
    await screen.findByText(/may be larger than this server accepts/i),
  ).toBeInTheDocument();
  await waitFor(() => {
    expect(uploadAsset).toHaveBeenCalledTimes(1);
  });
});

test('a 413 is explained in the dialog without losing the selection', async () => {
  const uploadAsset = vi.fn(async () =>
    apiError(413, envelope('payload_too_large', 'Upload is too large.')),
  );
  renderApp(EDITOR, client(undefined, { media: { uploadAsset } }));

  fireEvent.click(await screen.findByRole('button', { name: 'Add a photo' }));
  fireEvent.change(screen.getByLabelText('Upload a new image'), {
    target: { files: [pngFile()] },
  });

  expect(
    await screen.findByText(/larger than this server accepts/i),
  ).toBeInTheDocument();
  expect(screen.getByRole('dialog')).toBeInTheDocument();
});

test('a described image sends its alt text', async () => {
  const setItemImage = vi.fn(async () => ok(item({ id: 'i1' })));
  renderApp(EDITOR, client(undefined, { catalog: { setItemImage } }));

  fireEvent.click(await screen.findByRole('button', { name: 'Add a photo' }));
  fireEvent.click(await screen.findByRole('button', { name: /samosa\.jpg/i }));
  fireEvent.click(screen.getByLabelText('Describe this image'));
  fireEvent.change(screen.getByLabelText('Description'), {
    target: { value: 'Golden samosas on a banana leaf' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Use for this item' }));

  await waitFor(() => {
    expect(setItemImage).toHaveBeenCalledWith(
      SHALIK,
      'i1',
      { media_id: 'a1', alt_text: 'Golden samosas on a banana leaf' },
      'csrf-token-1',
    );
  });
});

test('a decorative image sends an explicit null alt text', async () => {
  const setItemImage = vi.fn(async () => ok(item({ id: 'i1' })));
  renderApp(EDITOR, client(undefined, { catalog: { setItemImage } }));

  fireEvent.click(await screen.findByRole('button', { name: 'Add a photo' }));
  fireEvent.click(await screen.findByRole('button', { name: /samosa\.jpg/i }));
  fireEvent.click(screen.getByLabelText(/this image is decorative/i));
  fireEvent.click(screen.getByRole('button', { name: 'Use for this item' }));

  await waitFor(() => {
    expect(setItemImage).toHaveBeenCalledWith(
      SHALIK,
      'i1',
      // Null is valid: the backend does not require alt text.
      { media_id: 'a1', alt_text: null },
      'csrf-token-1',
    );
  });
});

test('a newly chosen image requires an explicit alt-text decision', async () => {
  renderApp(EDITOR, client());

  fireEvent.click(await screen.findByRole('button', { name: 'Add a photo' }));
  fireEvent.click(await screen.findByRole('button', { name: /samosa\.jpg/i }));

  // Neither branch is preselected, so omission has to be deliberate. This is
  // form-completeness guidance, not a backend rule — both branches are valid.
  expect(
    screen.getByRole('button', { name: 'Use for this item' }),
  ).toBeDisabled();
  fireEvent.click(screen.getByLabelText(/this image is decorative/i));
  expect(
    screen.getByRole('button', { name: 'Use for this item' }),
  ).toBeEnabled();
});

test('an existing image with null alt text reopens as decorative, forcing nothing', async () => {
  renderApp(
    EDITOR,
    client(
      item({
        id: 'i1',
        category_id: 'c1',
        image_media_id: 'a1',
        image_alt_text: null,
      }),
    ),
  );

  fireEvent.click(await screen.findByRole('button', { name: 'Replace photo' }));
  expect(
    await screen.findByLabelText<HTMLInputElement>(/this image is decorative/i),
  ).toBeChecked();
  expect(
    screen.getByRole('button', { name: 'Use for this item' }),
  ).toBeEnabled();
});

test('clearing an image sends media_id null and no alt-text key at all', async () => {
  const setItemImage = vi.fn(async () => ok(item({ id: 'i1' })));
  renderApp(
    EDITOR,
    client(
      item({
        id: 'i1',
        category_id: 'c1',
        image_media_id: 'a1',
        image_alt_text: 'Samosas',
      }),
      { catalog: { setItemImage } },
    ),
  );

  fireEvent.click(
    await screen.findByRole('button', { name: 'Remove from item' }),
  );

  await waitFor(() => {
    // alt_text without an image is invalid by contract, so it must not appear.
    expect(setItemImage).toHaveBeenCalledWith(
      SHALIK,
      'i1',
      { media_id: null },
      'csrf-token-1',
    );
  });
});

test('removing from the item and deleting from the library are different actions', async () => {
  const deleteAsset = vi.fn(async () => ok({ status: 'deleted' as const }));
  const setItemImage = vi.fn(async () => ok(item({ id: 'i1' })));
  renderApp(
    EDITOR,
    client(item({ id: 'i1', category_id: 'c1', image_media_id: 'a1' }), {
      catalog: { setItemImage },
      media: { deleteAsset },
    }),
  );

  await screen.findByRole('button', { name: 'Remove from item' });
  expect(
    screen.getByRole('button', { name: 'Delete from library' }),
  ).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Delete from library' }));
  fireEvent.click(screen.getByRole('button', { name: 'Delete image' }));

  await waitFor(() => {
    expect(deleteAsset).toHaveBeenCalledWith(SHALIK, 'a1', 'csrf-token-1');
  });
  expect(setItemImage).not.toHaveBeenCalled();
});

test('deleting a referenced asset explains the real reason', async () => {
  const deleteAsset = vi.fn(async () =>
    apiError(409, envelope('conflict', 'the asset is referenced')),
  );
  renderApp(
    EDITOR,
    client(item({ id: 'i1', category_id: 'c1', image_media_id: 'a1' }), {
      media: { deleteAsset },
    }),
  );

  fireEvent.click(
    await screen.findByRole('button', { name: 'Delete from library' }),
  );
  fireEvent.click(screen.getByRole('button', { name: 'Delete image' }));

  expect(
    await screen.findByText(/still used by a menu item/i),
  ).toBeInTheDocument();
});

test('attaching an expired pending asset explains that it expired', async () => {
  const setItemImage = vi.fn(async () =>
    apiError(
      409,
      envelope(
        'invalid_state',
        'this media asset has expired and cannot be attached',
      ),
    ),
  );
  renderApp(EDITOR, client(undefined, { catalog: { setItemImage } }));

  fireEvent.click(await screen.findByRole('button', { name: 'Add a photo' }));
  fireEvent.click(await screen.findByRole('button', { name: /samosa\.jpg/i }));
  fireEvent.click(screen.getByLabelText(/this image is decorative/i));
  fireEvent.click(screen.getByRole('button', { name: 'Use for this item' }));

  expect(await screen.findByText(/has expired/i)).toBeInTheDocument();
});

test('a pending library asset shows when it expires rather than hiding it', async () => {
  renderApp(
    EDITOR,
    client(undefined, {
      media: {
        listAssets: vi.fn(async () =>
          ok({
            items: [
              asset({
                status: 'pending',
                pending_expires_at: '2026-07-23T00:00:00Z',
              }),
            ],
            total: 1,
            limit: 50,
            offset: 0,
          }),
        ),
      },
    }),
  );

  fireEvent.click(await screen.findByRole('button', { name: 'Add a photo' }));
  expect(
    await screen.findByText(/not used yet — expires/i),
  ).toBeInTheDocument();
});

test('an empty library says so instead of showing nothing', async () => {
  renderApp(
    EDITOR,
    client(undefined, {
      media: {
        listAssets: vi.fn(async () =>
          ok({ items: [], total: 0, limit: 50, offset: 0 }),
        ),
      },
    }),
  );

  fireEvent.click(await screen.findByRole('button', { name: 'Add a photo' }));
  expect(await screen.findByText(/no images yet/i)).toBeInTheDocument();
});

test('a media list failure keeps the picker usable for uploading', async () => {
  renderApp(
    EDITOR,
    client(undefined, {
      media: {
        listAssets: vi.fn(async () =>
          apiError(404, envelope('not_found', 'Not found.')),
        ),
      },
    }),
  );

  fireEvent.click(await screen.findByRole('button', { name: 'Add a photo' }));
  expect(
    await screen.findByText(/image library could not be loaded/i),
  ).toBeInTheDocument();
  // Uploading still works — the picker is not dead.
  expect(screen.getByLabelText('Upload a new image')).toBeEnabled();
});

type UploadResult = Awaited<ReturnType<typeof ok<ReturnType<typeof asset>>>>;

/** An upload held open, so the in-flight window can be inspected. */
function deferredUpload() {
  let resolve: ((value: UploadResult) => void) | undefined;
  const uploadAsset = vi.fn(
    () =>
      new Promise<UploadResult>((r) => {
        resolve = r;
      }),
  );
  return {
    uploadAsset,
    settle(value: UploadResult) {
      resolve?.(value);
    },
  };
}

/** Open the picker and start an upload that will not finish on its own. */
async function startUpload(overrides: Parameters<typeof client>[1] = {}) {
  const { uploadAsset, settle } = deferredUpload();
  const rendered = renderApp(
    EDITOR,
    client(undefined, { ...overrides, media: { uploadAsset } }),
  );
  fireEvent.click(await screen.findByRole('button', { name: 'Add a photo' }));
  fireEvent.change(screen.getByLabelText('Upload a new image'), {
    target: { files: [pngFile()] },
  });
  return { ...rendered, uploadAsset, settle };
}

test('the upload copy is scoped to what is actually true', async () => {
  const { settle } = await startUpload();

  const notice = await screen.findByText(/^Uploading…/);

  // Closing this dialog is genuinely survivable: the mutation outlives the
  // component, so that is offered plainly.
  expect(notice).toHaveTextContent(/you can close this dialog/i);
  // Continuation is conditioned on the app staying open, because a reload,
  // a tab close, or navigating out of the app kills an in-flight request
  // like any other fetch.
  expect(notice).toHaveTextContent(/while this app remains open/i);
  // And success is conditional, never promised.
  expect(notice).toHaveTextContent(/when it succeeds/i);

  // The two overclaims this copy must never make again.
  expect(notice).not.toHaveTextContent(/will not cancel/i);
  expect(notice).not.toHaveTextContent(/finishes on its own/i);
  settle(ok(asset()));
});

test('the visible control dismisses the picker while an upload is in flight', async () => {
  const { settle } = await startUpload();

  // "Close", not "Cancel": pressing it cancels nothing, so it must not say so.
  const close = await screen.findByRole('button', { name: 'Close' });
  expect(close).toBeEnabled();
  // Focus follows the exit. Disabling the file input drops focus to <body>,
  // which is outside the dialog's key handler and would put Escape out of
  // reach — a keyboard trap for the length of the request (WCAG 2.1.2).
  expect(close).toHaveFocus();

  fireEvent.click(close);
  await waitFor(() => {
    expect(screen.queryByRole('dialog')).toBeNull();
  });
  settle(ok(asset()));
});

test('Escape dismisses the picker while an upload is in flight', async () => {
  const { settle } = await startUpload();

  await screen.findByRole('button', { name: 'Close' });
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });

  await waitFor(() => {
    expect(screen.queryByRole('dialog')).toBeNull();
  });
  settle(ok(asset()));
});

test('an upload finishing after dismissal still refreshes the library', async () => {
  const { queryClient, settle } = await startUpload();

  fireEvent.click(await screen.findByRole('button', { name: 'Close' }));
  await waitFor(() => {
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  settle(ok(asset({ id: 'a2', original_filename: 'later.jpg' })));

  // The invalidation lives on the mutation itself (mediaData), not on the
  // dialog's per-call callbacks, so it survives the dialog unmounting. That
  // is what makes a dismissed-but-finished upload discoverable.
  await waitFor(() => {
    const cached = queryClient
      .getQueryCache()
      .findAll({ queryKey: ['business', SHALIK, 'media'] });
    expect(cached.length).toBeGreaterThan(0);
    expect(cached.some((query) => query.state.isInvalidated)).toBe(true);
  });
});

test('the attach still blocks dismissal, unlike the upload', async () => {
  type ImageResult = Awaited<ReturnType<typeof ok<ReturnType<typeof item>>>>;
  let resolve: ((value: ImageResult) => void) | undefined;
  const setItemImage = vi.fn(
    () =>
      new Promise<ImageResult>((r) => {
        resolve = r;
      }),
  );
  renderApp(EDITOR, client(undefined, { catalog: { setItemImage } }));

  fireEvent.click(await screen.findByRole('button', { name: 'Add a photo' }));
  fireEvent.click(await screen.findByRole('button', { name: /samosa\.jpg/i }));
  fireEvent.click(screen.getByLabelText(/this image is decorative/i));
  fireEvent.click(screen.getByRole('button', { name: 'Use for this item' }));

  // The attach is a short mutation whose result this dialog reports, so the
  // stricter pending behaviour is deliberately kept for it.
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  });
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
  expect(screen.getByRole('dialog')).toBeInTheDocument();

  resolve?.(ok(item({ id: 'i1' })));
});

test('staff are offered no photo actions', async () => {
  renderApp(
    EDITOR,
    client(
      item({ id: 'i1', category_id: 'c1', image_media_id: 'a1' }),
      {},
      'staff',
    ),
  );

  await screen.findByRole('heading', { name: 'Photo' });
  expect(screen.queryByRole('button', { name: 'Replace photo' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Remove from item' })).toBeNull();
  expect(
    screen.queryByRole('button', { name: 'Delete from library' }),
  ).toBeNull();
});
