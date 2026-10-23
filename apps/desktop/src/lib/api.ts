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

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
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

// --- Phase 4 domain types ---
export interface NameHistory {
  id: string;
  name: string;
  valid_from: string | null;
  valid_to: string | null;
  note: string | null;
}
export interface SourceIdentity {
  id: string;
  source_system: string;
  source_ref: string;
  source_display_name: string | null;
}
export interface Organisation {
  id: string;
  name: string;
  short_name: string | null;
  kind: string;
  is_historical: boolean;
  status: string;
  notes: string | null;
  merged_into_id: string | null;
  source_system: string | null;
  source_ref: string | null;
}
export interface OrganisationDetail extends Organisation {
  name_history: NameHistory[];
  source_identities: SourceIdentity[];
}
export interface DuplicateCandidate {
  organisation_id?: string;
  venue_id?: string;
  team_id?: string;
  competition_id?: string;
  name: string;
  evidence: string[];
  confidence: string;
}
export interface Venue {
  id: string;
  name: string;
  short_name: string | null;
  status: string;
  address: string | null;
  locality: string | null;
  region: string | null;
  country: string | null;
  postcode: string | null;
  latitude: number | null;
  longitude: number | null;
  notes: string | null;
  merged_into_id: string | null;
}
export interface Team {
  id: string;
  organisation_id: string;
  name: string;
  short_name: string | null;
  program: string;
  is_historical: boolean;
  status: string;
  merged_into_id: string | null;
}
export interface Competition {
  id: string;
  name: string;
  short_name: string | null;
  association_id: string | null;
  status: string;
  notes: string | null;
}
export interface Division {
  id: string;
  name: string;
  status: string;
}
export interface Grade {
  id: string;
  competition_id: string;
  division_id: string | null;
  name: string;
  program: string | null;
  status: string;
}
export interface Season {
  id: string;
  label: string;
  start_date: string | null;
  end_date: string | null;
  status: string;
}
export interface CompetitionDetail extends Competition {
  name_history: NameHistory[];
  divisions: Division[];
  grades: Grade[];
  seasons: Season[];
}
export interface TeamGradeEntry {
  id: string;
  team_id: string;
  grade_id: string;
  season_id: string;
  notes: string | null;
}
export interface MatchClassification {
  id: string;
  key: string | null;
  label: string | null;
  is_final: boolean | null;
  status: string;
  unresolved_source_value: string | null;
}
export interface PlayingCondition {
  id: string;
  scope: string;
  competition_id: string | null;
  season_id: string | null;
  grade_id: string | null;
  match_id: string | null;
  overs_limit: number | null;
  max_players: number | null;
  balls_per_over: number | null;
  innings_per_side: number | null;
  format: string | null;
  points: Record<string, unknown> | null;
  extra: Record<string, unknown> | null;
  notes: string | null;
}
export interface ResolvedConditions {
  conditions: Record<string, unknown>;
  sources: Record<string, string | null>;
}
export interface OrgRelationship {
  id: string;
  from_org_id: string;
  to_org_id: string;
  rel_type: string;
  valid_from: string | null;
  valid_to: string | null;
  notes: string | null;
  evidence: string | null;
  is_void: boolean;
}
export interface TimelineEvent {
  kind: string;
  name?: string;
  rel_type?: string;
  from_org_id?: string;
  to_org_id?: string;
  valid_from: string | null;
  valid_to: string | null;
  note: string | null;
  evidence?: string | null;
  uncertain: boolean;
}
export interface OrgTimeline {
  organisation: Organisation;
  events: TimelineEvent[];
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

  // --- Phase 4: organisations ---
  listOrganisations: (w: string, opts: { include_merged?: boolean; kind?: string } = {}) =>
    request<Organisation[]>(`/api/v1/workspaces/${w}/organisations${qs(opts)}`),
  getOrganisation: (w: string, id: string) =>
    request<OrganisationDetail>(`/api/v1/workspaces/${w}/organisations/${id}`),
  createOrganisation: (w: string, body: Record<string, unknown>) =>
    request<Organisation>(`/api/v1/workspaces/${w}/organisations`, { method: "POST", body }),
  updateOrganisation: (w: string, id: string, body: Record<string, unknown>) =>
    request<Organisation>(`/api/v1/workspaces/${w}/organisations/${id}`, { method: "PATCH", body }),
  orgDuplicateCandidates: (w: string, id: string) =>
    request<DuplicateCandidate[]>(`/api/v1/workspaces/${w}/organisations/${id}/duplicate-candidates`),
  orgAssertDistinct: (w: string, body: { organisation_a_id: string; organisation_b_id: string; reason?: string }) =>
    request<{ assertion_id: string }>(`/api/v1/workspaces/${w}/organisations/assert-distinct`, { method: "POST", body }),
  orgMerge: (w: string, body: { canonical_organisation_id: string; merged_organisation_id: string; reason?: string }) =>
    request<Record<string, string>>(`/api/v1/workspaces/${w}/organisations/merge`, { method: "POST", body }),
  orgUndoMerge: (w: string, mergeId: string) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/organisations/merges/${mergeId}/undo`, { method: "POST" }),
  addOrgName: (w: string, id: string, body: Record<string, unknown>) =>
    request<{ name_history_id: string }>(`/api/v1/workspaces/${w}/organisations/${id}/names`, { method: "POST", body }),
  addOrgSource: (w: string, id: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/organisations/${id}/sources`, { method: "POST", body }),

  // --- Phase 4: venues ---
  listVenues: (w: string, opts: { include_merged?: boolean; search?: string } = {}) =>
    request<Venue[]>(`/api/v1/workspaces/${w}/venues${qs(opts)}`),
  getVenue: (w: string, id: string) =>
    request<Venue & { name_history: NameHistory[]; source_identities: SourceIdentity[] }>(
      `/api/v1/workspaces/${w}/venues/${id}`,
    ),
  createVenue: (w: string, body: Record<string, unknown>) =>
    request<Venue>(`/api/v1/workspaces/${w}/venues`, { method: "POST", body }),
  updateVenue: (w: string, id: string, body: Record<string, unknown>) =>
    request<Venue>(`/api/v1/workspaces/${w}/venues/${id}`, { method: "PATCH", body }),
  venueDuplicateCandidates: (w: string, id: string) =>
    request<DuplicateCandidate[]>(`/api/v1/workspaces/${w}/venues/${id}/duplicate-candidates`),
  venueMerge: (w: string, body: { canonical_venue_id: string; merged_venue_id: string; reason?: string }) =>
    request<Record<string, string>>(`/api/v1/workspaces/${w}/venues/merge`, { method: "POST", body }),
  venueAssertDistinct: (w: string, body: { venue_a_id: string; venue_b_id: string; reason?: string }) =>
    request<{ assertion_id: string }>(`/api/v1/workspaces/${w}/venues/assert-distinct`, { method: "POST", body }),

  // --- Phase 4: teams ---
  listTeams: (w: string, opts: { organisation_id?: string; program?: string; include_merged?: boolean; search?: string } = {}) =>
    request<Team[]>(`/api/v1/workspaces/${w}/teams${qs(opts)}`),
  getTeam: (w: string, id: string) =>
    request<Team & { name_history: NameHistory[]; source_identities: SourceIdentity[] }>(
      `/api/v1/workspaces/${w}/teams/${id}`,
    ),
  createTeam: (w: string, body: Record<string, unknown>) =>
    request<Team>(`/api/v1/workspaces/${w}/teams`, { method: "POST", body }),
  updateTeam: (w: string, id: string, body: Record<string, unknown>) =>
    request<Team>(`/api/v1/workspaces/${w}/teams/${id}`, { method: "PATCH", body }),
  teamDuplicateCandidates: (w: string, id: string) =>
    request<DuplicateCandidate[]>(`/api/v1/workspaces/${w}/teams/${id}/duplicate-candidates`),
  teamMerge: (w: string, body: { canonical_team_id: string; merged_team_id: string; reason?: string }) =>
    request<Record<string, string>>(`/api/v1/workspaces/${w}/teams/merge`, { method: "POST", body }),

  // --- Phase 4: competitions / divisions / grades / seasons / entries ---
  listCompetitions: (w: string, opts: { association_id?: string; search?: string } = {}) =>
    request<Competition[]>(`/api/v1/workspaces/${w}/competitions${qs(opts)}`),
  getCompetition: (w: string, id: string) =>
    request<CompetitionDetail>(`/api/v1/workspaces/${w}/competitions/${id}`),
  createCompetition: (w: string, body: Record<string, unknown>) =>
    request<Competition>(`/api/v1/workspaces/${w}/competitions`, { method: "POST", body }),
  updateCompetition: (w: string, id: string, body: Record<string, unknown>) =>
    request<Competition>(`/api/v1/workspaces/${w}/competitions/${id}`, { method: "PATCH", body }),
  createDivision: (w: string, cid: string, body: Record<string, unknown>) =>
    request<{ division_id: string }>(`/api/v1/workspaces/${w}/competitions/${cid}/divisions`, { method: "POST", body }),
  createGrade: (w: string, cid: string, body: Record<string, unknown>) =>
    request<{ grade_id: string }>(`/api/v1/workspaces/${w}/competitions/${cid}/grades`, { method: "POST", body }),
  renameGrade: (w: string, gid: string, body: { name: string; name_change_note?: string }) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/competitions/grades/${gid}`, { method: "PATCH", body }),
  createSeason: (w: string, cid: string, body: Record<string, unknown>) =>
    request<{ season_id: string }>(`/api/v1/workspaces/${w}/competitions/${cid}/seasons`, { method: "POST", body }),
  enterTeam: (w: string, body: { team_id: string; grade_id: string; season_id: string; notes?: string }) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/competitions/entries`, { method: "POST", body }),
  listEntries: (w: string, opts: { team_id?: string; grade_id?: string; season_id?: string } = {}) =>
    request<TeamGradeEntry[]>(`/api/v1/workspaces/${w}/competitions/entries${qs(opts)}`),
  listClassifications: (w: string, status?: string) =>
    request<MatchClassification[]>(`/api/v1/workspaces/${w}/competitions/classifications${qs({ status_: status })}`),
  seedDefaultClassifications: (w: string) =>
    request<MatchClassification[]>(`/api/v1/workspaces/${w}/competitions/classifications/defaults`, { method: "POST" }),
  recordUnresolvedClassification: (w: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/competitions/classifications/unresolved`, { method: "POST", body }),

  // --- Phase 4: playing conditions ---
  setConditions: (w: string, body: Record<string, unknown>) =>
    request<PlayingCondition>(`/api/v1/workspaces/${w}/playing-conditions`, { method: "PUT", body }),
  resolveConditions: (w: string, opts: { competition_id?: string; season_id?: string; grade_id?: string; match_id?: string }) =>
    request<ResolvedConditions>(`/api/v1/workspaces/${w}/playing-conditions/resolve${qs(opts)}`),
  getConditions: (w: string, scope: string, targetId: string) =>
    request<PlayingCondition>(`/api/v1/workspaces/${w}/playing-conditions/${scope}/${targetId}`),
  clearConditions: (w: string, scope: string, targetId: string) =>
    request<{ removed: boolean }>(`/api/v1/workspaces/${w}/playing-conditions/${scope}/${targetId}`, { method: "DELETE" }),

  // --- Phase 4: organisation relationships + timeline ---
  createRelationship: (w: string, body: Record<string, unknown>) =>
    request<OrgRelationship>(`/api/v1/workspaces/${w}/organisation-relationships`, { method: "POST", body }),
  listRelationships: (w: string, organisation_id: string, opts: { include_void?: boolean; direction?: string } = {}) =>
    request<OrgRelationship[]>(`/api/v1/workspaces/${w}/organisation-relationships${qs({ organisation_id, ...opts })}`),
  orgTimeline: (w: string, organisation_id: string) =>
    request<OrgTimeline>(`/api/v1/workspaces/${w}/organisation-relationships/timeline${qs({ organisation_id })}`),
  resolveAffiliation: (w: string, organisation_id: string, on_date: string) =>
    request<{ affiliation: Record<string, unknown> | null; known: boolean }>(
      `/api/v1/workspaces/${w}/organisation-relationships/affiliation${qs({ organisation_id, on_date })}`,
    ),
  correctRelationship: (w: string, id: string, body: Record<string, unknown>) =>
    request<OrgRelationship>(`/api/v1/workspaces/${w}/organisation-relationships/${id}`, { method: "PATCH", body }),
  voidRelationship: (w: string, id: string) =>
    request<OrgRelationship>(`/api/v1/workspaces/${w}/organisation-relationships/${id}/void`, { method: "POST" }),
  restoreRelationship: (w: string, id: string) =>
    request<OrgRelationship>(`/api/v1/workspaces/${w}/organisation-relationships/${id}/restore`, { method: "POST" }),
};
