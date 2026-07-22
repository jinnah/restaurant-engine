import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Link, useNavigate, useParams } from 'react-router';
import type { ItemSummary } from '@restaurant-engine/api-client';
import { asApiFailure } from '../api/failure';
import { classifyFailure, conflictLimit } from '../api/failures';
import { useSession } from '../auth/useSession';
import {
  findMembership,
  useCurrentBusinessId,
} from '../business/useCurrentBusinessId';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { mapFailure, type FormFailure } from '../components/formErrors';
import { useNotify } from '../components/NotificationProvider';
import { ErrorSummary } from '../components/StatusPanels';
import { NotFoundPage } from '../routes/NotFoundPage';
import { AvailabilityToggle } from './components/AvailabilityToggle';
import { ItemFields } from './components/ItemFields';
import { ItemImageSection } from './components/ItemImageSection';
import { ModifierGroupsSection } from './components/ModifierGroupsSection';
import { UnsavedChangesPrompt } from './components/UnsavedChangesPrompt';
import {
  emptyItemValues,
  itemFieldsSchema,
  itemValues,
  toItemUpdate,
  type ItemFormValues,
} from './itemForm';
import {
  useAdminMenu,
  useBusiness,
  useDeleteItem,
  useUpdateItem,
} from './menuData';
import { menuPermissions } from './permissions';
import { FEATURED_LIMIT_DISPLAY, reportLimitDrift } from './policy';
import styles from './menu.module.css';

function findItem(
  categories: { items: ItemSummary[] }[],
  itemId: string,
): ItemSummary | null {
  for (const category of categories) {
    const found = category.items.find((entry) => entry.id === itemId);
    if (found !== undefined) {
      return found;
    }
  }
  return null;
}

/**
 * Edit one menu item.
 *
 * A full page rather than a drawer: the URL is shareable and refreshable,
 * Back means what it says, and on a phone a full screen is the right
 * primitive for a form this size (ADR-018).
 */
export function ItemEditorPage() {
  const businessId = useCurrentBusinessId() ?? '';
  const { itemId = '' } = useParams();
  const navigate = useNavigate();
  const notify = useNotify();
  const session = useSession();
  const menu = useAdminMenu(businessId);
  const business = useBusiness(businessId);
  const updateItem = useUpdateItem(businessId);
  const deleteItem = useDeleteItem(businessId);
  const [failure, setFailure] = useState<FormFailure | null>(null);
  const [featuredLimit, setFeaturedLimit] = useState(FEATURED_LIMIT_DISPLAY);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [leaving, setLeaving] = useState(false);

  const categories = menu.data?.categories ?? [];
  const item = findItem(categories, itemId);
  const currency = business.data?.currency ?? 'USD';

  const membership =
    session.status === 'authenticated'
      ? findMembership(session.session.memberships, businessId)
      : null;
  const permissions = membership === null ? null : menuPermissions(membership);

  const form = useForm<ItemFormValues>({
    resolver: zodResolver(itemFieldsSchema(currency)),
    // Explicit defaults as well as `values`: the tree and the currency both
    // arrive asynchronously, and without them the array fields would be
    // undefined on the render before `values` lands.
    defaultValues: emptyItemValues(''),
    values: item === null ? undefined : itemValues(item, currency),
    mode: 'onBlur',
  });
  const { formState, handleSubmit, register, control, reset } = form;

  useEffect(() => {
    if (item !== null) {
      document.title = `${item.name} — Restaurant Engine`;
    }
  }, [item]);

  useEffect(() => {
    if (leaving) {
      void navigate(`/businesses/${businessId}/menu`, { replace: true });
    }
  }, [leaving, businessId, navigate]);

  if (menu.isPending || business.isPending) {
    return (
      <p role="status" className={styles.loading}>
        Loading…
      </p>
    );
  }

  // The item is genuinely absent on this business's tree: the ordinary
  // not-found experience, with no hint about whether it ever existed.
  if (item === null) {
    return <NotFoundPage />;
  }

  const canWrite = permissions?.canWriteCatalog ?? false;
  const featuredCount = categories.reduce(
    (total, entry) => total + entry.items.filter((i) => i.is_featured).length,
    0,
  );

  function onSubmit(values: ItemFormValues) {
    if (item === null) {
      return;
    }
    const body = toItemUpdate(values, item, currency);
    if (Object.keys(body).length === 0) {
      notify({ message: 'Nothing to save.', tone: 'info' });
      return;
    }
    setFailure(null);
    updateItem.mutate(
      { itemId: item.id, body },
      {
        onSuccess: (updated) => {
          reset(itemValues(updated, currency));
          notify({ message: `“${updated.name}” saved.` });
        },
        onError: (error: unknown) => {
          const apiFailure = asApiFailure(error);
          const kind = classifyFailure(apiFailure);

          if (kind === 'conflict' && body.is_featured === true) {
            // The featured ceiling. The server's number wins, always; if it
            // disagrees with the mirrored constant that is a contract drift
            // worth reporting, not something to absorb silently.
            const serverLimit = conflictLimit(apiFailure);
            if (serverLimit !== null) {
              if (serverLimit !== FEATURED_LIMIT_DISPLAY) {
                reportLimitDrift(
                  'featured items',
                  FEATURED_LIMIT_DISPLAY,
                  serverLimit,
                );
              }
              setFeaturedLimit(serverLimit);
              setFailure({
                summary:
                  serverLimit === FEATURED_LIMIT_DISPLAY
                    ? `You can feature at most ${String(serverLimit)} items. Unfeature one first — hidden items count too.`
                    : `You can feature at most ${String(serverLimit)} items, which differs from what this page expected (${String(FEATURED_LIMIT_DISPLAY)}). Please report this. The server's limit applies.`,
                fields: {},
              });
              reset(itemValues(item, currency));
              void menu.refetch();
              return;
            }
          }

          if (kind === 'gone') {
            setFailure({
              summary:
                'This item was changed or removed. The menu has been refreshed.',
              fields: {},
            });
            void menu.refetch();
            return;
          }

          setFailure(mapFailure(apiFailure, 'The item could not be saved.'));
        },
      },
    );
  }

  return (
    <section aria-labelledby="item-title">
      <h2 id="item-title">{item.name}</h2>
      <p className={styles.crumb}>
        <Link to={`/businesses/${businessId}/menu`}>Back to the menu</Link>
      </p>

      {failure !== null && <ErrorSummary failure={failure} />}

      {permissions?.canSetAvailability === true && (
        <AvailabilityToggle businessId={businessId} item={item} />
      )}

      {canWrite ? (
        <form
          noValidate
          onSubmit={(event) => void handleSubmit(onSubmit)(event)}
        >
          <ItemFields
            register={register}
            control={control}
            errors={formState.errors}
            categories={categories}
            currency={currency}
            mode="edit"
            featuredCount={featuredCount}
            featuredLimit={featuredLimit}
          />
          <div className={styles.actions}>
            <button
              type="button"
              className={styles.secondary}
              disabled={!formState.isDirty || updateItem.isPending}
              onClick={() => {
                reset(itemValues(item, currency));
              }}
            >
              Discard changes
            </button>
            <button
              type="submit"
              className={styles.submit}
              disabled={!formState.isDirty || updateItem.isPending}
            >
              {updateItem.isPending ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        </form>
      ) : (
        <p className={styles.empty}>
          {permissions?.isReadOnly === true
            ? 'This business is closed, so its menu can no longer be edited.'
            : 'You can mark this item sold out, but editing it needs a manager or owner.'}
        </p>
      )}

      <ItemImageSection
        businessId={businessId}
        item={item}
        canWriteCatalog={canWrite}
        canWriteMedia={permissions?.canWriteMedia ?? false}
      />

      <ModifierGroupsSection
        businessId={businessId}
        itemId={item.id}
        currency={currency}
        canWrite={canWrite}
      />

      {canWrite && (
        <div className={styles.dangerZone}>
          <button
            type="button"
            className={styles.danger}
            onClick={() => {
              setConfirmingDelete(true);
            }}
          >
            Delete this item
          </button>
        </div>
      )}

      {confirmingDelete && (
        <ConfirmDialog
          title={`Delete ${item.name}?`}
          confirmLabel="Delete item"
          danger
          pending={deleteItem.isPending}
          onConfirm={() => {
            deleteItem.mutate(item.id, {
              onSuccess: () => {
                setConfirmingDelete(false);
                // The effect below navigates once React has committed
                // `leaving`, so the unsaved-changes blocker is already down.
                setLeaving(true);
                notify({ message: `“${item.name}” deleted.` });
              },
              onError: (error: unknown) => {
                setConfirmingDelete(false);
                setFailure(
                  mapFailure(
                    asApiFailure(error),
                    'This item could not be deleted.',
                  ),
                );
                void menu.refetch();
              },
            });
          }}
          onCancel={() => {
            setConfirmingDelete(false);
          }}
        >
          <p>
            This cannot be undone. Its options are deleted with it. Any photo
            stays in your image library.
          </p>
        </ConfirmDialog>
      )}

      <UnsavedChangesPrompt
        when={formState.isDirty && !leaving}
        message="This item has unsaved changes. Leaving will discard them."
      />
    </section>
  );
}
