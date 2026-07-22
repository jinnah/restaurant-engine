import { useState } from 'react';
import type { CategoryWithItems } from '@restaurant-engine/api-client';
import { useSession } from '../auth/useSession';
import {
  findMembership,
  useCurrentBusinessId,
} from '../business/useCurrentBusinessId';
import { ItemRow } from './components/ItemRow';
import { useMediaIndex } from './mediaData';
import { useAdminMenu, useBusiness } from './menuData';
import { menuPermissions } from './permissions';
import { FEATURED_LIMIT_DISPLAY } from './policy';
import styles from './menu.module.css';

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
  const [filter, setFilter] = useState('');

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

  return (
    <section aria-labelledby="menu-title">
      <h2 id="menu-title">Menu</h2>

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
    </section>
  );
}
