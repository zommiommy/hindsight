import { NextResponse } from "next/server";
import { localizeApiErrorPayload } from "@/lib/i18n/api-errors";
import { DATAPLANE_URL, getAdminHeaders } from "@/lib/hindsight-client";

/**
 * Proxy for the dataplane admin config endpoint (`GET /admin/config`).
 *
 * Forwards the independent admin token (HINDSIGHT_CP_ADMIN_TOKEN) rather than the
 * tenant API key. The dataplane returns 404 when the admin API is disabled and 401
 * when a token is required but missing/wrong — both are surfaced to the caller.
 */
export async function GET(request: Request) {
  try {
    const response = await fetch(`${DATAPLANE_URL}/admin/config`, {
      headers: getAdminHeaders({ Accept: "application/json" }),
      cache: "no-store",
    });

    if (!response.ok) {
      return NextResponse.json(
        localizeApiErrorPayload(request, {
          error: "Failed to get admin config",
          errorKey: "api.errors.admin.config.fetch",
        }),
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error("Error getting admin config:", error);
    return NextResponse.json(
      localizeApiErrorPayload(request, {
        error: "Failed to get admin config",
        errorKey: "api.errors.admin.config.fetch",
      }),
      { status: 500 }
    );
  }
}
