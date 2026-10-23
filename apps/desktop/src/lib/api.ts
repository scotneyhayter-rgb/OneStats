/**
 * Typed client for the OneStats backend (the desktop-to-backend interface).
 * Base URL from VITE_ONESTATS_API_URL (default localhost:8000). The session token is held
 * in localStorage and sent as a Bearer header. No secrets beyond the session token.
 */

const BASE_URL: string =
  import.meta.env.VITE_ONESTATS_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "onestats.session";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}
export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage may be unavailable */
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  opts: { method?: string; body?: unknown; auth?: boolean; form?: FormData } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (opts.auth !== false) {
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let resp: Response;
  try {
    resp = await fetch(`${BASE_URL}${path}`, { method: opts.method ?? "GET", headers, body });
  } catch {
    throw new ApiError(`Cannot reach the OneStats backend at ${BASE_URL}. Is it running?`);
  }
  if (resp.status === 204) return undefined as T;
  let data: unknown = null;
  const text = await resp.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!resp.ok) {
    const err = (data as { error?: { code?: string; message?: string } })?.error;
    throw new ApiError(err?.message ?? `Request failed (${resp.status})`, resp.status, err?.code);
  }
  return data as T;
}

// --- types ---
export interface User {
  id: string;
  username: string;
  display_name: string | null;
  is_super_admin: boolean;
}
export interface Workspace {
  id: string;
  name: string;
  short_name: string | null;
  type: string;
  status: string;
  roles?: string[];
}
export interface Draft {
  id: string;
  status: string;
  current_step: number;
  state: Record<string, unknown>;
  workspace_id: string | null;
}
export interface ColourResolved {
  background: string;
  foreground: string;
  contrast_ratio: number;
  meets_aa: boolean;
  meets_aa_large: boolean;
}

export const api = {
  baseUrl: BASE_URL,
  health: () => request<{ status: string; version: string; env: string }>("/api/v1/health", { auth: false }),

  // auth / setup
  setupStatus: () => request<{ setup_required: boolean }>("/api/v1/setup/status", { auth: false }),
  createSuperAdmin: (username: string, password: string, setup_token: string) =>
    request<{ created: boolean }>("/api/v1/setup/super-admin", {
      method: "POST", auth: false, body: { username, password, setup_token },
    }),
  login: (username: string, password: string) =>
    request<{ token: string; expires_at: string; user: User }>("/api/v1/auth/login", {
      method: "POST", auth: false, body: { username, password },
    }),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),
  me: () => request<User>("/api/v1/auth/me"),

  // workspaces
  myWorkspaces: () => request<Workspace[]>("/api/v1/workspaces"),
  createWorkspace: (name: string, short_name: string, type: string) =>
    request<Workspace>("/api/v1/workspaces", { method: "POST", body: { name, short_name, type } }),

  // onboarding
  startDraft: (template?: string) =>
    request<Draft>("/api/v1/onboarding", { method: "POST", body: { template } }),
  getDraft: (id: string) => request<Draft>(`/api/v1/onboarding/${id}`),
  saveDraft: (id: string, state: Record<string, unknown>, current_step?: number) =>
    request<Draft>(`/api/v1/onboarding/${id}`, { method: "PATCH", body: { state, current_step } }),
  activateDraft: (id: string) =>
    request<{ activated: boolean; workspace_id: string }>(`/api/v1/onboarding/${id}/activate`, {
      method: "POST",
    }),

  // branding
  previewColours: (workspaceId: string, colours: Record<string, string>) =>
    request<{ colours: Record<string, ColourResolved>; warnings: string[] }>(
      `/api/v1/workspaces/${workspaceId}/branding/preview`, { method: "POST", body: { colours } },
    ),
  getBranding: (workspaceId: string) =>
    request<{ branding: Record<string, unknown> | null; resolved: unknown; published: unknown }>(
      `/api/v1/workspaces/${workspaceId}/branding`,
    ),
};
