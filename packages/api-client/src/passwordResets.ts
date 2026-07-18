// Public password-reset redemption facade (M2D, ADR-014).
//
// The token travels ONLY in the POST body. Issuance is a platform
// operation (`client.platform.issuePasswordReset`); this public surface
// only redeems. A successful redemption revokes every session server-side;
// the caller signs in again through auth.login.

import type { Client } from 'openapi-fetch';

import type { components, paths } from './generated/schema';
import { toResult, type ApiResult } from './result';

export type PasswordResetRedeemRequest =
  components['schemas']['PasswordResetRedeemRequest'];
export type PasswordResetRedeemResponse =
  components['schemas']['PasswordResetRedeemResponse'];

export interface PasswordResetsApi {
  /** Redeem a reset token and set a new password. */
  redeem(
    body: PasswordResetRedeemRequest,
  ): Promise<ApiResult<PasswordResetRedeemResponse>>;
}

export function createPasswordResetsApi(
  client: Client<paths>,
): PasswordResetsApi {
  return {
    async redeem(body) {
      try {
        const { data, error, response } = await client.POST(
          '/api/v1/password-resets/redeem',
          { body },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },
  };
}
