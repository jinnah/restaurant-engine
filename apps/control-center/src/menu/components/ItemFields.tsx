import type { UseFormRegister, FieldErrors, Control } from 'react-hook-form';
import { Controller } from 'react-hook-form';
import type { CategoryWithItems } from '@restaurant-engine/api-client';
import {
  CheckboxField,
  FormField,
  SelectField,
  TextAreaField,
} from '../../components/FormField';
import { DIETARY_TAGS, dietaryLabel } from '../dietary';
import type { ItemFormValues } from '../itemForm';
import styles from '../menu.module.css';

interface ItemFieldsProps {
  register: UseFormRegister<ItemFormValues>;
  control: Control<ItemFormValues>;
  errors: FieldErrors<ItemFormValues>;
  categories: CategoryWithItems[];
  currency: string;
  /** Editing exposes visibility and featuring; creation does not. */
  mode: 'create' | 'edit';
  /** Shown next to the featured control so the ceiling is never a surprise. */
  featuredCount: number;
  featuredLimit: number;
}

/**
 * The item form's fields, shared by creation and editing.
 *
 * Presentation is shared; the request models are not. Each page builds its
 * own body through `toItemCreate` or `toItemUpdate`, whose distinct return
 * types make it impossible for a create payload to acquire an update-only
 * field.
 *
 * Availability is deliberately absent. "Sold out today" is a separate
 * workflow command with its own capability (which is why staff can reach it),
 * and it is not part of the item PATCH contract at all (ruling D4).
 */
export function ItemFields({
  register,
  control,
  errors,
  categories,
  currency,
  mode,
  featuredCount,
  featuredLimit,
}: ItemFieldsProps) {
  const atFeaturedLimit = featuredCount >= featuredLimit;

  return (
    <>
      <FormField
        id="item-name"
        label="Name"
        autoComplete="off"
        error={errors.name?.message}
        {...register('name')}
      />

      <TextAreaField
        id="item-description"
        label="Description (optional)"
        hint="What a customer sees under the name on your menu."
        error={errors.description?.message}
        {...register('description')}
      />

      <FormField
        id="item-price"
        label={`Price (${currency})`}
        inputMode="decimal"
        autoComplete="off"
        hint="Digits and a dot, for example 12.50."
        error={errors.price?.message}
        {...register('price')}
      />

      <SelectField
        id="item-category"
        label="Category"
        hint={
          mode === 'edit'
            ? 'Moving an item places it at the end of the new category.'
            : undefined
        }
        error={errors.categoryId?.message}
        {...register('categoryId')}
      >
        <option value="">— Choose a category —</option>
        {categories.map((category) => (
          <option key={category.id} value={category.id}>
            {category.name}
          </option>
        ))}
      </SelectField>

      <fieldset className={styles.fieldset}>
        <legend>Dietary attributes</legend>
        <Controller
          control={control}
          name="dietaryTags"
          render={({ field }) => (
            <>
              {DIETARY_TAGS.map((tag) => (
                <CheckboxField
                  key={tag}
                  id={`item-tag-${tag}`}
                  label={dietaryLabel(tag)}
                  checked={field.value.includes(tag)}
                  onChange={(event) => {
                    field.onChange(
                      event.target.checked
                        ? [...field.value, tag]
                        : field.value.filter((value) => value !== tag),
                    );
                  }}
                />
              ))}
            </>
          )}
        />
        {errors.dietaryTags?.message !== undefined && (
          <p className={styles.fieldErrorText}>{errors.dietaryTags.message}</p>
        )}
      </fieldset>

      {mode === 'edit' ? (
        <>
          <CheckboxField
            id="item-visible"
            label="Hide from the storefront"
            hint="Hidden items disappear from your public menu. This is separate from “sold out today”."
            {...register('isHidden')}
          />
          <CheckboxField
            id="item-featured"
            label="Feature this item"
            hint={
              atFeaturedLimit
                ? `You are already featuring ${String(featuredCount)} of ${String(featuredLimit)} items. Unfeature one first — hidden items count too.`
                : `Featured: ${String(featuredCount)} of ${String(featuredLimit)}. Hidden items count toward the limit.`
            }
            {...register('isFeatured')}
          />
        </>
      ) : (
        <p className={styles.fieldHintText}>
          New items start visible and available, and are not featured. You can
          change that, add a photo, and add options after saving.
        </p>
      )}
    </>
  );
}
