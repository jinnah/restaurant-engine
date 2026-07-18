// The public client factory: one internal openapi-fetch client, domain
// facades composed on top (ADR-009). Health methods stay flat (M1C
// surface); every domain from M2A onward mounts as a group
// (`client.auth.login(...)`, `client.platform.listBusinesses(...)`).

import { createInternalClient, type ApiClientOptions } from './client';
import { createAuthApi, type AuthApi } from './auth';
import { createBusinessesApi, type BusinessesApi } from './businesses';
import { createHealthMethods, type HealthMethods } from './health';
import { createPlatformApi, type PlatformApi } from './platform';
import { createPublicApi, type PublicApi } from './public';

export interface ApiClient extends HealthMethods {
  auth: AuthApi;
  platform: PlatformApi;
  businesses: BusinessesApi;
  public: PublicApi;
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  const client = createInternalClient(options);
  return {
    ...createHealthMethods(client),
    auth: createAuthApi(client),
    platform: createPlatformApi(client),
    businesses: createBusinessesApi(client),
    public: createPublicApi(client),
  };
}
