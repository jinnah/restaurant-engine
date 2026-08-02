/**
 * Query keys for the hours workspace (M5C). One settings document per
 * business — every write returns the complete updated `HoursSettings`,
 * so the cache holds exactly one shape under exactly one key.
 */
export const hoursKeys = {
  root: (businessId: string) => ['hours', businessId] as const,
  settings: (businessId: string) => ['hours', businessId, 'settings'] as const,
};
