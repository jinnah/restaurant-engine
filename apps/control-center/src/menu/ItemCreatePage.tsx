import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { asApiFailure } from '../api/failure';
import { useCurrentBusinessId } from '../business/useCurrentBusinessId';
import { mapFailure, type FormFailure } from '../components/formErrors';
import { useNotify } from '../components/NotificationProvider';
import { ErrorSummary } from '../components/StatusPanels';
import { CreateCategoryInlineDialog } from './components/CreateCategoryInlineDialog';
import { ItemFields } from './components/ItemFields';
import { UnsavedChangesPrompt } from './components/UnsavedChangesPrompt';
import {
  emptyItemValues,
  itemFieldsSchema,
  serverFieldErrors,
  toItemCreate,
  type ItemFormValues,
} from './itemForm';
import { useAdminMenu, useBusiness, useCreateItem } from './menuData';
import styles from './menu.module.css';

/**
 * Create a menu item at `/menu/items/new?categoryId=…`.
 *
 * The category arrives as a query parameter so "Add item" on a category can
 * preselect it, but a missing, malformed, or stale value is never a dead
 * end: the category select simply starts empty with an explanation, and the
 * page stays usable. That matters because this URL is bookmarkable and a
 * category can be deleted between one visit and the next.
 */
export function ItemCreatePage() {
  const businessId = useCurrentBusinessId() ?? '';
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const notify = useNotify();
  const menu = useAdminMenu(businessId);
  const business = useBusiness(businessId);
  const createItem = useCreateItem(businessId);
  const [failure, setFailure] = useState<FormFailure | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [creatingCategory, setCreatingCategory] = useState(false);

  const categories = menu.data?.categories ?? [];
  const currency = business.data?.currency ?? 'USD';
  const requested = params.get('categoryId');
  // A requested category counts only if it is really one of this business's:
  // a stale or invented id must not be sent to the server as a path segment.
  const preselected =
    requested !== null && categories.some((entry) => entry.id === requested)
      ? requested
      : '';

  const form = useForm<ItemFormValues>({
    resolver: zodResolver(itemFieldsSchema(currency)),
    defaultValues: emptyItemValues(preselected),
    mode: 'onBlur',
  });
  const {
    formState,
    handleSubmit,
    register,
    control,
    reset,
    setError,
    setValue,
  } = form;

  useEffect(() => {
    document.title = 'New item — Restaurant Engine';
  }, []);

  // Navigate from an effect, not from the success handler. The
  // unsaved-changes blocker reads state that React has not committed yet
  // while the handler is still running, so navigating there would have the
  // application challenge its own success redirect.
  useEffect(() => {
    if (createdId !== null) {
      void navigate(`/businesses/${businessId}/menu/items/${createdId}`, {
        replace: true,
      });
    }
  }, [createdId, businessId, navigate]);

  // The tree and currency arrive after first render; adopt the resolved
  // category once, without disturbing anything the user has typed.
  useEffect(() => {
    if (preselected !== '' && formState.defaultValues?.categoryId === '') {
      reset(emptyItemValues(preselected), { keepDirtyValues: true });
    }
  }, [preselected, formState.defaultValues, reset]);

  if (menu.isPending || business.isPending) {
    return (
      <p role="status" className={styles.loading}>
        Loading…
      </p>
    );
  }

  const featuredCount = categories.reduce(
    (total, entry) => total + entry.items.filter((i) => i.is_featured).length,
    0,
  );

  function onSubmit(values: ItemFormValues) {
    setFailure(null);
    createItem.mutate(
      { categoryId: values.categoryId, body: toItemCreate(values, currency) },
      {
        onSuccess: (created) => {
          // Clear dirtiness first, then record the id; the effect above does
          // the navigating once React has committed both.
          reset(emptyItemValues(values.categoryId));
          setCreatedId(created.id);
          notify({ message: `Item “${created.name}” added.` });
        },
        onError: (error: unknown) => {
          const mapped = mapFailure(
            asApiFailure(error),
            'The item could not be added.',
          );
          setFailure(mapped);
          // The server's own words, on the input it rejected. The price
          // ceiling reaches the user this way and no other, because this app
          // deliberately does not know what it is.
          for (const { field, message } of serverFieldErrors(mapped.fields)) {
            setError(field, { type: 'server', message });
          }
        },
      },
    );
  }

  return (
    <section aria-labelledby="new-item-title">
      <h2 id="new-item-title">New item</h2>
      <p className={styles.crumb}>
        <Link to={`/businesses/${businessId}/menu`}>Back to the menu</Link>
      </p>

      {preselected === '' && requested !== null && (
        <p role="status" className={styles.noticeText}>
          That category is no longer available. Choose a category for this item.
        </p>
      )}
      {failure !== null && <ErrorSummary failure={failure} />}

      <form noValidate onSubmit={(event) => void handleSubmit(onSubmit)(event)}>
        <ItemFields
          register={register}
          control={control}
          errors={formState.errors}
          categories={categories}
          currency={currency}
          mode="create"
          onCreateCategory={() => {
            setCreatingCategory(true);
          }}
          featuredCount={featuredCount}
          // Creation cannot feature an item — ItemCreate carries no
          // `is_featured` — so no ceiling is ever relevant here.
          featuredLimit={null}
        />
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.secondary}
            onClick={() => {
              void navigate(`/businesses/${businessId}/menu`);
            }}
          >
            Cancel
          </button>
          <button
            type="submit"
            className={styles.submit}
            disabled={createItem.isPending}
          >
            {createItem.isPending ? 'Adding…' : 'Add item'}
          </button>
        </div>
      </form>

      {/* Rendered outside the item form so no <form> nests inside another;
          creating a category selects it here without disturbing what has
          already been typed (item 5). */}
      {creatingCategory && (
        <CreateCategoryInlineDialog
          businessId={businessId}
          onCancel={() => {
            setCreatingCategory(false);
          }}
          onCreated={(cat) => {
            setCreatingCategory(false);
            setValue('categoryId', cat.id, {
              shouldDirty: true,
              shouldValidate: true,
            });
          }}
        />
      )}

      <UnsavedChangesPrompt
        when={formState.isDirty && createdId === null}
        message="This item has not been created yet. Leaving will discard it."
      />
    </section>
  );
}
