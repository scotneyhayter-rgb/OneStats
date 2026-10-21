/**
 * Typed client for the OneStats backend (the clearly-defined desktop-to-backend
 * interface). The base URL is configurable via VITE_ONESTATS_API_URL; in development the
 * backend runs locally (see docs/DEVELOPMENT.md). No secrets are handled here.
 */

const BASE_URL: string =
  import.meta.env.VITE_ONESTATS_API_URL ?? "http://localhost:8000";

export interface Health {
  status: string;
  service: string;
  version: string;
  env: string;
}

export interface DbHealth {
  database_configured: boolean;
  database_connected: boolean;
  detail: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${BASE_URL}${path}`, { signal });
  } catch (e) {
    throw new ApiError(
      `Cannot reach the OneStats backend at ${BASE_URL}. Is it running?`,
    );
  }
  if (!resp.ok) {
    throw new ApiError(`Request failed (${resp.status})`, resp.status);
  }
  return (await resp.json()) as T;
}

export const api = {
  baseUrl: BASE_URL,
  health: (signal?: AbortSignal) => getJson<Health>("/api/v1/health", signal),
  dbHealth: (signal?: AbortSignal) => getJson<DbHealth>("/api/v1/health/db", signal),
};
