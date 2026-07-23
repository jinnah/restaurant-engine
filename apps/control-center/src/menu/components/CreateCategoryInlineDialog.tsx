import { useState } from 'react';
import type { CategorySummary } from '@restaurant-engine/api-client';
import type { FormFailure } from '../../components/formErrors';
import { useNotify } from '../../components/NotificationProvider';
import { useCreateCategory } from '../menuData';
import { CategoryFormDialog, categoryFailure } from './CategoryFormDialog';

/**
 * Create a category from within the item workflow (item 5).
 *
 * The same create behaviour and validation as the menu page — it reuses
 * `useCreateCategory` and `CategoryFormDialog` — so there is one category
 * contract, not a second. On success it hands the new category back to the
 * caller, which selects it in the item form without disturbing anything
 * already typed. Rendered by the page *outside* the item `<form>` so no form
 * is ever nested inside another; a repeated submit is prevented by the
 * dialog's pending guard and the single-flight mutation.
 */
export function CreateCategoryInlineDialog({
  businessId,
  onCreated,
  onCancel,
}: {
  businessId: string;
  onCreated: (category: CategorySummary) => void;
  onCancel: () => void;
}) {
  const create = useCreateCategory(businessId);
  const notify = useNotify();
  const [failure, setFailure] = useState<FormFailure | null>(null);

  return (
    <CategoryFormDialog
      pending={create.isPending}
      failure={failure}
      onCancel={onCancel}
      onSubmit={(values) => {
        setFailure(null);
        create.mutate(
          {
            name: values.name,
            description:
              values.description.trim() === '' ? null : values.description,
          },
          {
            onSuccess: (created) => {
              onCreated(created);
              notify({ message: `Category “${created.name}” added.` });
            },
            onError: (error: unknown) => {
              setFailure(
                categoryFailure(error, 'The category could not be added.'),
              );
            },
          },
        );
      }}
    />
  );
}
