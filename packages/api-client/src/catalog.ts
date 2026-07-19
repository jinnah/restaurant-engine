// Catalog administration facade (M3A, ADR-017).
//
// Business-scoped menu management: the caller acts on their own business
// and the server authorizes via membership capabilities (nonmembers get
// 404, existence non-disclosure). General writes need
// business.catalog.write; the availability command is the one
// staff-reachable mutation (business.catalog.availability). Every unsafe
// call carries the synchronizer CSRF token.

import type { Client } from 'openapi-fetch';

import type { components, paths } from './generated/schema';
import { toResult, type ApiResult } from './result';

export type AdminMenu = components['schemas']['AdminMenu'];
export type CategoryWithItems = components['schemas']['CategoryWithItems'];
export type CategorySummary = components['schemas']['CategorySummary'];
export type CategoryCreate = components['schemas']['CategoryCreate'];
export type CategoryUpdate = components['schemas']['CategoryUpdate'];
export type CategoryReorder = components['schemas']['CategoryReorder'];
export type ItemSummary = components['schemas']['ItemSummary'];
export type ItemCreate = components['schemas']['ItemCreate'];
export type ItemUpdate = components['schemas']['ItemUpdate'];
export type ItemReorder = components['schemas']['ItemReorder'];
export type ItemAvailabilitySet = components['schemas']['ItemAvailabilitySet'];
export type CatalogDeletedResponse = components['schemas']['DeletedResponse'];

const CSRF_HEADER = 'X-CSRF-Token';

export interface CatalogApi {
  /** The complete administrative menu tree (hidden entries included). */
  getMenu(businessId: string): Promise<ApiResult<AdminMenu>>;
  createCategory(
    businessId: string,
    body: CategoryCreate,
    csrfToken: string,
  ): Promise<ApiResult<CategorySummary>>;
  updateCategory(
    businessId: string,
    categoryId: string,
    body: CategoryUpdate,
    csrfToken: string,
  ): Promise<ApiResult<CategorySummary>>;
  /** Empty categories only (non-empty → 409). */
  deleteCategory(
    businessId: string,
    categoryId: string,
    csrfToken: string,
  ): Promise<ApiResult<CatalogDeletedResponse>>;
  /** Full-set reorder: every category id in the new order. */
  reorderCategories(
    businessId: string,
    body: CategoryReorder,
    csrfToken: string,
  ): Promise<ApiResult<AdminMenu>>;
  createItem(
    businessId: string,
    categoryId: string,
    body: ItemCreate,
    csrfToken: string,
  ): Promise<ApiResult<ItemSummary>>;
  getItem(businessId: string, itemId: string): Promise<ApiResult<ItemSummary>>;
  updateItem(
    businessId: string,
    itemId: string,
    body: ItemUpdate,
    csrfToken: string,
  ): Promise<ApiResult<ItemSummary>>;
  deleteItem(
    businessId: string,
    itemId: string,
    csrfToken: string,
  ): Promise<ApiResult<CatalogDeletedResponse>>;
  /** Full-set reorder within one category. */
  reorderItems(
    businessId: string,
    body: ItemReorder,
    csrfToken: string,
  ): Promise<ApiResult<AdminMenu>>;
  /** The "sold out today" toggle — staff-reachable. */
  setItemAvailability(
    businessId: string,
    itemId: string,
    body: ItemAvailabilitySet,
    csrfToken: string,
  ): Promise<ApiResult<ItemSummary>>;
}

export function createCatalogApi(client: Client<paths>): CatalogApi {
  const csrf = (csrfToken: string) => ({ [CSRF_HEADER]: csrfToken });

  return {
    async getMenu(businessId) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}/catalog/menu',
          { params: { path: { business_id: businessId } } },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async createCategory(businessId, body, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/businesses/{business_id}/catalog/categories',
          {
            params: { path: { business_id: businessId } },
            body,
            headers: csrf(csrfToken),
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async updateCategory(businessId, categoryId, body, csrfToken) {
      try {
        const { data, error, response } = await client.PATCH(
          '/api/v1/businesses/{business_id}/catalog/categories/{category_id}',
          {
            params: {
              path: { business_id: businessId, category_id: categoryId },
            },
            body,
            headers: csrf(csrfToken),
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async deleteCategory(businessId, categoryId, csrfToken) {
      try {
        const { data, error, response } = await client.DELETE(
          '/api/v1/businesses/{business_id}/catalog/categories/{category_id}',
          {
            params: {
              path: { business_id: businessId, category_id: categoryId },
            },
            headers: csrf(csrfToken),
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async reorderCategories(businessId, body, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/businesses/{business_id}/catalog/categories/reorder',
          {
            params: { path: { business_id: businessId } },
            body,
            headers: csrf(csrfToken),
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async createItem(businessId, categoryId, body, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/businesses/{business_id}/catalog/categories/{category_id}/items',
          {
            params: {
              path: { business_id: businessId, category_id: categoryId },
            },
            body,
            headers: csrf(csrfToken),
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async getItem(businessId, itemId) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}/catalog/items/{item_id}',
          { params: { path: { business_id: businessId, item_id: itemId } } },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async updateItem(businessId, itemId, body, csrfToken) {
      try {
        const { data, error, response } = await client.PATCH(
          '/api/v1/businesses/{business_id}/catalog/items/{item_id}',
          {
            params: { path: { business_id: businessId, item_id: itemId } },
            body,
            headers: csrf(csrfToken),
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async deleteItem(businessId, itemId, csrfToken) {
      try {
        const { data, error, response } = await client.DELETE(
          '/api/v1/businesses/{business_id}/catalog/items/{item_id}',
          {
            params: { path: { business_id: businessId, item_id: itemId } },
            headers: csrf(csrfToken),
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async reorderItems(businessId, body, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/businesses/{business_id}/catalog/items/reorder',
          {
            params: { path: { business_id: businessId } },
            body,
            headers: csrf(csrfToken),
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async setItemAvailability(businessId, itemId, body, csrfToken) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/businesses/{business_id}/catalog/items/{item_id}/availability',
          {
            params: { path: { business_id: businessId, item_id: itemId } },
            body,
            headers: csrf(csrfToken),
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },
  };
}
