import { z } from 'zod';
import type {
  DietaryTag,
  ItemCreate,
  ItemSummary,
  ItemUpdate,
} from '@restaurant-engine/api-client';
import { DIETARY_TAGS } from './dietary';
import {
  minorToMajorInput,
  moneyErrorMessage,
  parseMajorToMinor,
} from './money';

const MAX_NAME = 120;
const MAX_DESCRIPTION = 1000;
const MAX_TAGS = 3;

/**
 * The item form's shape.
 *
 * Zod validates UI concerns only — required, trimmed, length, decimal
 * precision (ADR-004: API truth stays generated from OpenAPI). Every bound
 * here mirrors one the server enforces; none of them replaces it, and a 422
 * still maps onto the same fields.
 *
 * Price carries **no maximum**. Its ceiling is a domain rule the contract
 * does not publish in any form this app could check, so the field validates
 * only that the text converts to an exact integer number of minor units and
 * lets the server rule on the amount. `serverFieldErrors` below is how that
 * ruling gets back onto this field.
 *
 * The schema is built per currency because price precision depends on it:
 * "12.5" is valid in USD and invalid in JPY.
 */
export function itemFieldsSchema(currency: string) {
  return z.object({
    name: z
      .string()
      .trim()
      .min(1, 'Enter a name for this item.')
      .max(MAX_NAME, `Use at most ${String(MAX_NAME)} characters.`),
    description: z
      .string()
      .max(
        MAX_DESCRIPTION,
        `Use at most ${String(MAX_DESCRIPTION)} characters.`,
      ),
    price: z.string().superRefine((value, ctx) => {
      const parsed = parseMajorToMinor(value, currency);
      if (!parsed.ok) {
        ctx.addIssue({
          code: 'custom',
          message: moneyErrorMessage(parsed.error, currency),
        });
      }
    }),
    categoryId: z.string().min(1, 'Choose a category for this item.'),
    dietaryTags: z
      .array(z.enum(DIETARY_TAGS))
      .max(MAX_TAGS, `Choose at most ${String(MAX_TAGS)}.`),
    isHidden: z.boolean(),
    isFeatured: z.boolean(),
  });
}

export type ItemFormValues = z.infer<ReturnType<typeof itemFieldsSchema>>;

/**
 * Request field name → form field name.
 *
 * The envelope names the field the *API* rejected; the form knows its own
 * inputs. `price_minor` and `price` are the case that matters: the server
 * owns the price ceiling, so its 422 has to land on the price input rather
 * than in a generic summary the user cannot act on.
 */
const FORM_FIELD_BY_REQUEST_FIELD: Record<string, keyof ItemFormValues> = {
  name: 'name',
  description: 'description',
  price_minor: 'price',
  category_id: 'categoryId',
  dietary_tags: 'dietaryTags',
};

/**
 * The subset of a `FormFailure`'s field errors that this form can display,
 * translated to its own field names. Anything unrecognized is left out and
 * stays visible through the failure summary — never silently dropped.
 */
export function serverFieldErrors(
  fields: Record<string, string>,
): { field: keyof ItemFormValues; message: string }[] {
  const mapped: { field: keyof ItemFormValues; message: string }[] = [];
  for (const [requestField, message] of Object.entries(fields)) {
    const field = FORM_FIELD_BY_REQUEST_FIELD[requestField];
    if (field !== undefined) {
      mapped.push({ field, message });
    }
  }
  return mapped;
}

/** Form defaults for a brand-new item, optionally in a preselected category. */
export function emptyItemValues(categoryId: string): ItemFormValues {
  return {
    name: '',
    description: '',
    price: '',
    categoryId,
    // Backend defaults (ItemCreate): a new item starts visible, available,
    // and unfeatured. These two are edit-only and are shown as explanatory
    // text on the create form rather than as controls that do nothing.
    isHidden: false,
    isFeatured: false,
    dietaryTags: [],
  };
}

/** Form values for an existing item. */
export function itemValues(
  item: ItemSummary,
  currency: string,
): ItemFormValues {
  return {
    name: item.name,
    description: item.description ?? '',
    price: minorToMajorInput(item.price_minor, currency),
    categoryId: item.category_id,
    isHidden: item.is_hidden,
    isFeatured: item.is_featured,
    dietaryTags: [...item.dietary_tags],
  };
}

/**
 * The create request body.
 *
 * Exactly the `ItemCreate` fields and nothing else: `category_id` is a path
 * parameter, and `is_hidden`, `is_featured`, and `is_available` are not part
 * of creation at all. The return type is what enforces that — a field that
 * belongs only to an update cannot be added here without a type error.
 */
export function toItemCreate(
  values: ItemFormValues,
  currency: string,
): ItemCreate {
  const parsed = parseMajorToMinor(values.price, currency);
  return {
    name: values.name.trim(),
    description:
      values.description.trim() === '' ? null : values.description.trim(),
    price_minor: parsed.ok ? parsed.minor : 0,
    dietary_tags: values.dietaryTags as DietaryTag[],
  };
}

function sameTags(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && [...a].sort().join() === [...b].sort().join();
}

/**
 * The update request body, carrying only what actually changed.
 *
 * A PATCH leaves absent fields untouched, so sending an unchanged field is
 * not harmless: it would overwrite whatever another administrator committed
 * in the meantime (ruling D5 — concurrent valid edits are last-committed-
 * write). `is_available` is deliberately impossible to send here; it is the
 * separate staff-reachable command.
 */
export function toItemUpdate(
  values: ItemFormValues,
  original: ItemSummary,
  currency: string,
): ItemUpdate {
  const body: ItemUpdate = {};
  const name = values.name.trim();
  if (name !== original.name) {
    body.name = name;
  }
  const description =
    values.description.trim() === '' ? null : values.description.trim();
  if (description !== original.description) {
    body.description = description;
  }
  const parsed = parseMajorToMinor(values.price, currency);
  if (parsed.ok && parsed.minor !== original.price_minor) {
    body.price_minor = parsed.minor;
  }
  if (values.categoryId !== original.category_id) {
    body.category_id = values.categoryId;
  }
  if (values.isHidden !== original.is_hidden) {
    body.is_hidden = values.isHidden;
  }
  if (values.isFeatured !== original.is_featured) {
    body.is_featured = values.isFeatured;
  }
  if (!sameTags(values.dietaryTags, original.dietary_tags)) {
    body.dietary_tags = values.dietaryTags as DietaryTag[];
  }
  return body;
}
