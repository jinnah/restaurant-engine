import { useCurrentBusinessId } from '../business/useCurrentBusinessId';
import { useAdminMenu } from './menuData';
import styles from './menu.module.css';

/**
 * The menu overview: every category and its items, hidden entries included,
 * because this is the management view (M3E).
 *
 * Loading, error, and empty are all rendered honestly rather than as a blank
 * page — an owner who sees nothing must be able to tell "still loading" from
 * "nothing here yet" from "we could not reach the server".
 */
export function MenuOverviewPage() {
  const businessId = useCurrentBusinessId() ?? '';
  const menu = useAdminMenu(businessId);

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

  const categories = menu.data.categories;

  return (
    <section aria-labelledby="menu-title">
      <h2 id="menu-title">Menu</h2>
      {categories.length === 0 ? (
        <p className={styles.empty}>
          Your menu is empty. Start by adding a category — a category is a
          section of your menu, such as Starters or Biryani.
        </p>
      ) : (
        <ol className={styles.categoryList}>
          {categories.map((category) => (
            <li key={category.id} className={styles.categoryCard}>
              <h3 className={styles.categoryName}>{category.name}</h3>
              <p className={styles.count}>
                {category.items.length === 1
                  ? '1 item'
                  : `${String(category.items.length)} items`}
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
