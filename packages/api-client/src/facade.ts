// The public client factory: one internal openapi-fetch client, domain
// facades composed on top (ADR-009). Health methods stay flat (M1C
// surface); every domain from M2A onward mounts as a group
// (`client.auth.login(...)`, `client.platform.listBusinesses(...)`).

import { createInternalClient, type ApiClientOptions } from './client';
import { createAuthApi, type AuthApi } from './auth';
import { createBusinessesApi, type BusinessesApi } from './businesses';
import { createCatalogApi, type CatalogApi } from './catalog';
import { createHealthMethods, type HealthMethods } from './health';
import { createHoursApi, type HoursApi } from './hours';
import { createInvitationsApi, type InvitationsApi } from './invitations';
import { createMediaApi, type MediaApi } from './media';
import { createOrdersApi, type OrdersApi } from './orders';
import {
  createPasswordResetsApi,
  type PasswordResetsApi,
} from './passwordResets';
import { createPlatformApi, type PlatformApi } from './platform';
import { createPublicApi, type PublicApi } from './public';
import { createStorefrontApi, type StorefrontApi } from './storefront';

export interface ApiClient extends HealthMethods {
  auth: AuthApi;
  platform: PlatformApi;
  businesses: BusinessesApi;
  catalog: CatalogApi;
  media: MediaApi;
  storefront: StorefrontApi;
  hours: HoursApi;
  orders: OrdersApi;
  public: PublicApi;
  invitations: InvitationsApi;
  passwordResets: PasswordResetsApi;
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  const client = createInternalClient(options);
  return {
    ...createHealthMethods(client),
    auth: createAuthApi(client),
    platform: createPlatformApi(client),
    businesses: createBusinessesApi(client),
    catalog: createCatalogApi(client),
    media: createMediaApi(client, options),
    storefront: createStorefrontApi(client),
    hours: createHoursApi(client),
    orders: createOrdersApi(client),
    public: createPublicApi(client),
    invitations: createInvitationsApi(client),
    passwordResets: createPasswordResetsApi(client),
  };
}
