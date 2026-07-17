// The public client factory: one internal openapi-fetch client, domain
// facades composed on top (ADR-009). Health methods stay flat (M1C
// surface); every domain from M2A onward mounts as a group
// (`client.auth.login(...)`).

import { createInternalClient, type ApiClientOptions } from './client';
import { createAuthApi, type AuthApi } from './auth';
import { createHealthMethods, type HealthMethods } from './health';

export interface ApiClient extends HealthMethods {
  auth: AuthApi;
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  const client = createInternalClient(options);
  return {
    ...createHealthMethods(client),
    auth: createAuthApi(client),
  };
}
