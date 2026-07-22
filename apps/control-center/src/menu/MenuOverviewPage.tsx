import { useState } from 'react';
import type {
  CategorySummary,
  CategoryWithItems,
} from '@restaurant-engine/api-client';
import { useSession } from '../auth/useSession';
import {
  findMembership,
  useCurrentBusinessId,
} from '../business/useCurrentBusinessId';
import { ConfirmDialog } from '../components/ConfirmDialog';
import type { FormFailure } from '../components/formErrors';
import { useNotify } from '../components/NotificationProvider';
import { ErrorSummary } from '../components/StatusPanels';
import {
  CategoryFormDialog,
  categoryFailure,
  type CategoryFormValues,
} from './components/CategoryFormDialog';
import { ItemRow } from './components/ItemRow';
import { useMediaIndex } from './mediaData';
import {
  useAdminMenu,
  useBusiness,
  useCreateCategory,
  useDeleteCategory,
  useUpdateCategory,
} from './menuData';
import { menuPermissions } from './permissions';
import { FEATURED_LIMIT_DISPLAY } from './policy';
import styles from './menu.module.css';

type CategoryDialog =
  | { mode: 'create' }
  | { mode: 'edit'; category: CategorySummary }
  | { mode: 'delete'; category: CategoryWithItems };

function matches(name: string, filter: string): boolean {
  return name.toLocaleLowerCase().includes(filter.toLocaleLowerCase());
}

/** Categories reduced to the items matching the filter; empty filter passes all. */
function applyFilter(
  categories: CategoryWithItems[],
  filter: string,
): CategoryWithItems[] {
  const trimmed = filter.trim();
  if (trimmed === '') {
    return categories;
  }
  return categories.map((category) => ({
    ...category,
    items: category.items.filter((item) => matches(item.name, trimmed)),
  }));
}

/**
 * The menu overview: every category and item, hidden entries included,
 * because this is the management view.
 *
 * The whole tree arrives in one request — the policy ceilings (50
 * categories, 300 items) keep it bounded, and there is no server-side search
 * to reach for — so filtering happens here over loaded data.
 */
export function MenuOverviewPage() {
  const businessId = useCurrentBusinessId() ?? '';
  const session = useSession();
  const menu = useAdminMenu(businessId);
  const business = useBusiness(businessId);
  const notify = useNotify();
  const [filter, setFilter] = useState('');
  const [dialog, setDialog] = useState<CategoryDialog | null>(null);
  const [failure, setFailure] = useState<FormFailure | null>(null);
  const [pageError, setPageError] = useState<FormFailure | null>(null);

  const createCategory = useCreateCategory(businessId);
  const updateCategory = useUpdateCategory(businessId);
  const deleteCategory = useDeleteCategory(businessId);

  const membership =
    session.status === 'authenticated'
      ? findMembership(session.session.memberships, businessId)
      : null;
  const permissions = membership === null ? null : menuPermissions(membership);

  const categories = menu.data?.categories ?? [];
  const hasImages = categories.some((category) =>
    category.items.some((item) => item.image_media_id !== null),
  );
  const mediaIndex = useMediaIndex(businessId, hasImages);

  // Counted from the authoritative tree on every render rather than
  // memoized: the ceilings cap this at 300 items, and a stale featured count
  // after a mutation would be worse than the work saved.
  const featured = categories.flatMap((category) =>
    category.items.filter((item) => item.is_featured),
  );

  if (menu.isPending) {
    return (
      <p role="status" className={styles.loading}>
        Loading menu…
      </p>
    );
  }

  if (menu.isError) {
    return (
      <div role="alert" className={styles.errorPanel}>
        <p>The menu could not be loaded.</p>
        <button
          type="button"
          className={styles.secondary}
          onClick={() => {
            void menu.refetch();
          }}
        >
          Try again
        </button>
      </div>
    );
  }

  // Prices cannot be rendered honestly without the Business's currency, so
  // the tree waits for it rather than guessing a symbol.
  if (business.isPending) {
    return (
      <p role="status" className={styles.loading}>
        Loading menu…
      </p>
    );
  }
  const currency = business.data?.currency ?? 'USD';

  const filtered = applyFilter(categories, filter);
  const filtering = filter.trim() !== '';
  const matchCount = filtered.reduce(
    (total, category) => total + category.items.length,
    0,
  );
  const canWrite = permissions?.canWriteCatalog ?? false;

  /**
   * Every category mutation ends the same way: close the dialog, restore
   * focus, then publish. The order matters — a notification published while
   * the dialog is still open would sit behind a focus trap, visible but
   * unreachable (ADR-018 ruling 6).
   */
  function closeThenNotify(message: string) {
    setDialog(null);
    setFailure(null);
    notify({ message });
  }

  function submitCategory(values: CategoryFormValues) {
    if (dialog === null) {
      return;
    }
    setFailure(null);
    if (dialog.mode === 'create') {
      createCategory.mutate(
        {
          name: values.name,
          description:
            values.description.trim() === '' ? null : values.description,
        },
        {
          onSuccess: (created) => {
            closeThenNotify(`Category “${created.name}” added.`);
          },
          onError: (error: unknown) => {
            setFailure(
              categoryFailure(error, 'The category could not be added.'),
            );
          },
        },
      );
      return;
    }
    if (dialog.mode === 'edit') {
      const original = dialog.category;
      // Only changed fields are sent: PATCH semantics mean an absent field is
      // untouched, so sending everything would overwrite a concurrent edit
      // with values this page happened to be holding.
      const body: Parameters<typeof updateCategory.mutate>[0]['body'] = {};
      if (values.name !== original.name) {
        body.name = values.name;
      }
      const description =
        values.description.trim() === '' ? null : values.description;
      if (description !== original.description) {
        body.description = description;
      }
      if (values.isVisible !== original.is_visible) {
        body.is_visible = values.isVisible;
      }
      if (Object.keys(body).length === 0) {
        setDialog(null);
        return;
      }
      updateCategory.mutate(
        { categoryId: original.id, body },
        {
          onSuccess: (updated) => {
            closeThenNotify(`Category “${updated.name}” saved.`);
          },
          onError: (error: unknown) => {
            setFailure(
              categoryFailure(error, 'The category could not be saved.'),
            );
          },
        },
      );
    }
  }

  function confirmDelete(category: CategoryWithItems) {
    deleteCategory.mutate(category.id, {
      onSuccess: () => {
        closeThenNotify(`Category “${category.name}” deleted.`);
      },
      onError: (error: unknown) => {
        setDialog(null);
        setPageError(
          categoryFailure(
            error,
            'The category could not be deleted. It may have changed — the menu has been refreshed.',
          ),
        );
        void menu.refetch();
      },
    });
  }

  return (
    <section aria-labelledby="menu-title">
      <div className={styles.pageHead}>
        <h2 id="menu-title">Menu</h2>
        {canWrite && (
          <button
            type="button"
            className={styles.submit}
            onClick={() => {
              setFailure(null);
              setDialog({ mode: 'create' });
            }}
          >
            New category
          </button>
        )}
      </div>

      {pageError !== null && <ErrorSummary failure={pageError} />}

      {categories.length === 0 ? (
        <p className={styles.empty}>
          Your menu is empty. Start by adding a category — a category is a
          section of your menu, such as Starters or Biryani.
        </p>
      ) : (
        <>
          <p className={styles.featuredStrip}>
            Featured items: {featured.length} of {FEATURED_LIMIT_DISPLAY}
            {featured.length > 0 && (
              <span className={styles.featuredNames}>
                {' '}
                — {featured.map((item) => item.name).join(', ')}
              </span>
            )}
          </p>

          <div className={styles.filterRow}>
            <label htmlFor="menu-filter">Filter items by name</label>
            <input
              id="menu-filter"
              type="search"
              value={filter}
              autoComplete="off"
              onChange={(event) => {
                setFilter(event.target.value);
              }}
            />
          </div>
          {filtering && (
            <p role="status" className={styles.filterCount}>
              {matchCount === 1
                ? '1 item matches'
                : `${String(matchCount)} items match`}
            </p>
          )}

          <ol className={styles.categoryList}>
            {filtered.map((category) => (
              <li key={category.id} className={styles.categoryCard}>
                <div className={styles.categoryHead}>
                  <h3 className={styles.categoryName}>
                    {category.name}
                    {!category.is_visible && (
                      <span className={styles.chipHidden}>Hidden</span>
                    )}
                  </h3>
                  <p className={styles.count}>
                    {category.items.length === 1
                      ? '1 item'
                      : `${String(category.items.length)} items`}
                  </p>
                </div>
                {canWrite && (
                  <div className={styles.categoryActions}>
                    <button
                      type="button"
                      className={styles.quiet}
                      onClick={() => {
                        setFailure(null);
                        setDialog({ mode: 'edit', category });
                      }}
                    >
                      Edit {category.name}
                    </button>
                    <button
                      type="button"
                      className={styles.quiet}
                      disabled={category.items.length > 0}
                      aria-describedby={
                        category.items.length > 0
                          ? `delete-blocked-${category.id}`
                          : undefined
                      }
                      onClick={() => {
                        setPageError(null);
                        setDialog({ mode: 'delete', category });
                      }}
                    >
                      Delete {category.name}
                    </button>
                    {category.items.length > 0 && (
                      <span
                        id={`delete-blocked-${category.id}`}
                        className={styles.actionNote}
                      >
                        Move or delete its items before deleting the category.
                      </span>
                    )}
                  </div>
                )}
                {category.description !== null && (
                  <p className={styles.categoryDescription}>
                    {category.description}
                  </p>
                )}
                {category.items.length === 0 ? (
                  <p className={styles.empty}>
                    {filtering
                      ? 'No matching items in this category.'
                      : 'No items yet.'}
                  </p>
                ) : (
                  <ol className={styles.itemList}>
                    {category.items.map((item) => (
                      <ItemRow
                        key={item.id}
                        businessId={businessId}
                        item={item}
                        currency={currency}
                        asset={
                          item.image_media_id === null
                            ? undefined
                            : mediaIndex.get(item.image_media_id)
                        }
                      />
                    ))}
                  </ol>
                )}
              </li>
            ))}
          </ol>
        </>
      )}

      {permissions?.isReadOnly === true && (
        <p className={styles.empty}>
          This menu is read-only because the business is closed.
        </p>
      )}

      {(dialog?.mode === 'create' || dialog?.mode === 'edit') && (
        <CategoryFormDialog
          category={dialog.mode === 'edit' ? dialog.category : undefined}
          pending={createCategory.isPending || updateCategory.isPending}
          failure={failure}
          onSubmit={submitCategory}
          onCancel={() => {
            setDialog(null);
            setFailure(null);
          }}
        />
      )}

      {dialog?.mode === 'delete' && (
        <ConfirmDialog
          title={`Delete ${dialog.category.name}?`}
          confirmLabel="Delete category"
          danger
          pending={deleteCategory.isPending}
          onConfirm={() => {
            confirmDelete(dialog.category);
          }}
          onCancel={() => {
            setDialog(null);
          }}
        >
          <p>
            This cannot be undone. Items are never deleted with a category — an
            empty category is all that is removed.
          </p>
        </ConfirmDialog>
      )}
    </section>
  );
}
