/**
 * Shared Hindsight API client instance for the control plane.
 * Configured to connect to the dataplane API server.
 */

import {
  HindsightClient,
  HindsightError,
  createClient,
  createConfig,
  sdk,
} from "@vectorize-io/hindsight-client";

export const DATAPLANE_URL = process.env.HINDSIGHT_CP_DATAPLANE_API_URL || "http://localhost:8888";
const DATAPLANE_API_KEY = process.env.HINDSIGHT_CP_DATAPLANE_API_KEY || "";
const ADMIN_TOKEN = process.env.HINDSIGHT_CP_ADMIN_TOKEN || "";

/**
 * Auth headers for direct fetch calls to the dataplane API.
 */
export function getDataplaneHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  if (DATAPLANE_API_KEY) {
    headers["Authorization"] = `Bearer ${DATAPLANE_API_KEY}`;
  }
  return headers;
}

/**
 * Auth headers for the dataplane admin endpoints (`/admin/*`).
 *
 * The admin surface uses its own independent token (HINDSIGHT_CP_ADMIN_TOKEN ->
 * HINDSIGHT_API_ADMIN_TOKEN), distinct from the tenant API key. When unset, no auth
 * header is sent and the dataplane decides whether the admin API is open.
 */
export function getAdminHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  if (ADMIN_TOKEN) {
    headers["Authorization"] = `Bearer ${ADMIN_TOKEN}`;
  }
  return headers;
}

/**
 * Build a dataplane URL for a bank-scoped endpoint with the bank id properly encoded.
 * Bank ids may contain `:`, `/`, `%`, etc. (e.g. openclaw `agent::channel::user`),
 * which must be percent-encoded before being interpolated into a URL path.
 */
export function dataplaneBankUrl(bankId: string, suffix = ""): string {
  return `${DATAPLANE_URL}/v1/default/banks/${encodeURIComponent(bankId)}${suffix}`;
}

/**
 * High-level client with convenience methods
 */
export const hindsightClient = new HindsightClient({
  baseUrl: DATAPLANE_URL,
  apiKey: DATAPLANE_API_KEY || undefined,
});

/**
 * Low-level client for direct SDK access
 */
export const lowLevelClient = createClient(
  createConfig({
    baseUrl: DATAPLANE_URL,
    headers: DATAPLANE_API_KEY ? { Authorization: `Bearer ${DATAPLANE_API_KEY}` } : undefined,
  })
);

/**
 * Export SDK functions for direct API access
 */
export { sdk };

/**
 * Export HindsightError for error handling
 */
export { HindsightError };
