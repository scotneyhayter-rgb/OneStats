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
  score_format?: string;   // Phase 7.7: 'au' (wickets/runs) | 'en' (runs/wickets)
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
export interface MatchFormat {
  id: string;
  code: string;
  label: string;
  enabled: boolean;
  is_default: boolean;
  is_custom: boolean;
  sort_order: number;
}
export interface Competition {
  id: string;
  name: string;
  short_name: string | null;
  association_id: string | null;
  status: string;
  notes: string | null;
  season_model?: string;
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

// --- Phase 5 (people) types ---
export interface Person {
  id: string;
  display_name: string;
  status: string;
  is_junior: boolean;
  privacy_protected: boolean;
  dob: string | null;
  dob_precision: string;
  notes: string | null;
  merged_into_id: string | null;
  protected_fields_hidden?: boolean;
}
export interface PersonDuplicateCandidate {
  person_id: string;
  display_name: string;
  evidence: string[];
  confidence: string;
}
export interface PersonMerge {
  id: string;
  canonical_person_id: string;
  merged_person_id: string;
  reason: string | null;
  evidence: string | null;
  is_undone: boolean;
}
export interface ImportBatch {
  id: string;
  source_system: string;
  source_filename: string | null;
  status: string;
  counts: Record<string, number> | null;
  created_at?: string;
  promoted_at?: string | null;
}
export interface HowoutUnresolved {
  code: string;
  count: number;
  examples: { match_id?: number; innings_id?: number; batsman_id?: number; score?: number }[];
}
export interface CricketStatzImportResult {
  committed: boolean;
  batch_id?: string;
  staged: Record<string, number>;
  preview: { promotable_now: number; unresolved: number; matches_promotable: number; by_entity: Record<string, Record<string, number>> };
  howout_unresolved: HowoutUnresolved[];
  people: { detected?: { matched: number; possible_existing: number; new: number }; promoted?: { created: Record<string, number>; linked: Record<string, number> } };
  promoted?: { created: Record<string, number>; matched: Record<string, number>; status: string };
}
export interface AutoSyncDashboard {
  sources: number;
  pending_review: number;
  new_matches: number;
  possible_duplicates: number;
  updated_scorecards: number;
  jobs_running: number;
  jobs_failed: number;
  coverage: Record<string, number>;
  last_success_at: string | null;
}
export interface ResearchDashboard {
  projects_active: number;
  projects_total: number;
  sources_total: number;
  sources_recent: { id: string; title: string; source_type: string; created_at: string | null }[];
  matches_under_investigation: number;
  draft_scorecards: number;
  awaiting_verification: number;
  disputed: number;
  verified: number;
  conflicting_evidence: number;
  open_tasks: number;
  notes_total: number;
}
export interface ResearchProject {
  id: string;
  title: string;
  description: string | null;
  status: "active" | "paused" | "completed" | "archived";
  scope: Record<string, unknown> | null;
  owner: string | null;
  created_at: string;
  updated_at: string;
}
export interface ResearchSource {
  id: string;
  title: string;
  source_type: string;
  publication: string | null;
  author: string | null;
  publication_date: string | null;
  publication_date_precision: string;
  edition: string | null;
  page_ref: string | null;
  original_url: string | null;
  copyright_status: string | null;
  usage_restrictions: string | null;
  ocr_status: string;
  created_at: string;
}
export interface AutoSyncConnector {
  connector_id: string;
  provider: string;
  status: string;
  access_method: string | null;
  countries: string[];
  formats: string[];
  coverage: string | null;
  auth_required: boolean;
  version: string;
  notes: string | null;
}
export interface SyncSource {
  id: string;
  connector_id: string;
  name: string;
  provider: string | null;
  access_method: string | null;
  reliability: string;
  enabled: boolean;
  last_success_at: string | null;
  auth_required: boolean;
}
export interface SyncJob {
  id: string;
  source_system: string;
  kind: string;
  status: string;
  attempts: number;
  last_error: string | null;
  created_at: string;
}
export interface DiscoveryItem {
  id: string;
  source_system: string;
  source_ref: string;
  kind: string;
  classification: string;
  status: string;
  confidence: number | null;
  match_id: string | null;
  candidate: Record<string, unknown> | null;
  proposed_changes: Record<string, unknown> | null;
}
export interface DiscoveryCoverage {
  id: string;
  scope_key: string;
  status: string;
  matches_found: number;
  searched_at: string | null;
}
export interface MatchSource {
  id: string;
  source_system: string;
  source_ref: string;
  edition: string | null;
  source_filename: string | null;
  source_sha256: string | null;
  recorded_fields: Record<string, unknown> | null;
  created_at: string;
}
export interface MatchSourceConflict {
  field: string;
  values: { source_system: string; source_ref: string; edition: string | null; value: unknown }[];
}
export interface GenericImportResult {
  format_id: string;
  display_name: string;
  batch_id: string;
  counts: Record<string, number>;
  source_system: string;
  committed: boolean;
  created?: Record<string, number>;
  matched?: Record<string, number>;
  status?: string;
}
export interface ImportRecord {
  id: string;
  entity_type: string;
  source_ref: string;
  raw: Record<string, unknown>;
  normalised: Record<string, unknown>;
  status: string;
  resolution: string | null;
  matched_canonical_id: string | null;
  issues: unknown;
}

// --- Phase 6 (matches & scorecards) types ---
export interface MatchTeam {
  id: string;
  team_id: string;
  is_home: boolean;
  captain_person_id: string | null;
  acting_captain_person_id: string | null;
  wicketkeeper_person_id: string | null;
  wicketkeeper2_person_id: string | null;
  bonus_points: number | null;
}
export interface Match {
  id: string;
  competition_id: string | null;
  grade_id: string | null;
  season_id: string | null;
  venue_id: string | null;
  match_date: string | null;
  date_precision: string;
  round: string | null;
  matchtype: string | null;
  format: string | null;
  status: string;
  classification: string;
  finals_stage: string | null;
  classification_verified: boolean;
  result_type: string | null;
  result_raw: string | null;
  result_source?: string | null;
  result_override_reason?: string | null;
  approval_status?: string;            // Phase 7.1: draft | awaiting_approval | approved | rejected
  approval_reason?: string | null;
  approved_at?: string | null;
  revised_since_approval?: boolean;
  won_by_team_id: string | null;
  margin_runs: number | null;
  margin_wickets: number | null;
  toss_winner_team_id: string | null;
  toss_decision: string | null;
  include_in_statistics: boolean;
  notes: string | null;
  source_system: string | null;
  source_ref: string | null;
  // present on list responses (from the match_team relationship); nullable until a side is set
  home_team_id?: string | null;
  away_team_id?: string | null;
}
export interface ComputedResult {
  status: string;  // sufficient | insufficient | requires_review
  result_type?: string | null;
  won_by_team_id?: string | null;
  margin_runs?: number | null;
  margin_wickets?: number | null;
  basis?: string;
  reason?: string;
}
export interface ValidationItem { scope: string; area: string; code: string }
export interface MatchDetail extends Match {
  teams: MatchTeam[];
  computed_result?: ComputedResult;   // Phase 7.3: result derived from the scorecard
  result_warnings?: string[];
  season_warnings?: string[];         // Phase 7.4
  validation?: ValidationItem[];      // Phase 7.1: aggregated advisory warnings
}
export interface Innings {
  id: string;
  match_id: string;
  inns_number: number;
  batting_team_id: string | null;
  bowling_team_id: string | null;
  status: string;
  byes: number | null;
  legbyes: number | null;
  wides: number | null;
  noballs: number | null;
  penalty: number | null;
  official_total: number | null;
  official_wickets: number | null;
  override_reason: string | null;
  iresult_raw: string | null;
  iresult_status: string;
  notes: string | null;
}
export interface InningsTotals {
  innings_id: string;
  extras_total: number | null;
  batting_runs: number | null;
  bowling_conceded: number | null;
  derived_total: number | null;
  derived_wickets: number | null;
  official_total: number | null;
  official_wickets: number | null;
}
export interface BattingEntry {
  id: string;
  innings_id: string;
  person_id: string | null;
  batting_position: number | null;
  runs: number | null;
  balls_faced: number | null;
  fours: number | null;
  sixes: number | null;
  minutes: number | null;
  dismissal_type: string | null;
  dismissal_source_code: string | null;
  bowler_person_id: string | null;
  fielder_person_id: string | null;
  notes: string | null;
  evidence: string | null;
}
export interface BowlingEntry {
  id: string;
  innings_id: string;
  person_id: string | null;
  bowling_order: number | null;
  overs_text: string | null;
  legal_balls: number | null;
  maidens: number | null;
  runs_conceded: number | null;
  wickets: number | null;
  wides: number | null;
  noballs: number | null;
  bowling_type_raw: string | null;
  notes: string | null;
  evidence: string | null;
}
export interface FallOfWicket {
  id: string;
  innings_id: string;
  wicket_number: number | null;
  team_score: number | null;
  dismissed_person_id: string | null;
  not_out_person_id: string | null;
  batting_entry_id: string | null;
  overs_text: string | null;
  legal_balls: number | null;
  notes: string | null;
  evidence: string | null;
}
export interface Partnership {
  id: string;
  innings_id: string;
  wicket_number: number | null;
  runs: number | null;
  balls: number | null;
  player1_person_id: string | null;
  player2_person_id: string | null;
  unbroken: boolean | null;
  end_reason: string | null;
  origin: string; // calculated | manual | verified | unknown
  notes: string | null;
  evidence: string | null;
}
export interface Warnings {
  warnings: string[];
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
  updateWorkspace: (w: string, body: Record<string, unknown>) =>
    request<Workspace>(`/api/v1/workspaces/${w}`, { method: "PATCH", body }),
  // --- Phase 7.8: official-statistics recalculation ---
  recalcStats: (w: string) =>
    request<{ matches: number; contributions: number }>(`/api/v1/workspaces/${w}/stats/recalc`, { method: "POST" }),
  officialPersonStats: (w: string, personId: string) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/stats/people/${personId}`),
  // --- Phase 7.5: workspace-configurable match formats ---
  listMatchFormats: (w: string, opts: { enabled_only?: boolean } = {}) =>
    request<MatchFormat[]>(`/api/v1/workspaces/${w}/match-formats${qs(opts)}`),
  createMatchFormat: (w: string, label: string) =>
    request<MatchFormat>(`/api/v1/workspaces/${w}/match-formats`, { method: "POST", body: { label } }),
  updateMatchFormat: (w: string, id: string, body: { enabled?: boolean; is_default?: boolean }) =>
    request<MatchFormat>(`/api/v1/workspaces/${w}/match-formats/${id}`, { method: "PATCH", body }),

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
    request<Competition & { seasons_reassigned?: { matches: number; assigned: number } }>(
      `/api/v1/workspaces/${w}/competitions/${id}`, { method: "PATCH", body }),
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

  // --- Phase 5: people ---
  listPeople: (w: string, opts: { search?: string; role?: string; include_merged?: boolean; include_protected?: boolean; organisation_id?: string; active_only?: boolean } = {}) =>
    request<Person[]>(`/api/v1/workspaces/${w}/people${qs(opts)}`),
  getPerson: (w: string, id: string, include_protected = false) =>
    request<Person & { names: unknown[]; source_identities: unknown[]; roles: string[] }>(
      `/api/v1/workspaces/${w}/people/${id}${qs({ include_protected })}`),
  createPerson: (w: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people`, { method: "POST", body }),
  addPersonName: (w: string, id: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people/${id}/names`, { method: "POST", body }),
  addPersonRole: (w: string, id: string, role: string) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people/${id}/roles`, { method: "POST", body: { role } }),

  // profiles (career view)
  getProfile: (w: string, id: string) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people/${id}/profile`),
  upsertProfile: (w: string, id: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people/${id}/profile`, { method: "PUT", body }),
  addPersonNumber: (w: string, id: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people/${id}/numbers`, { method: "POST", body }),
  addPersonLeadership: (w: string, id: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people/${id}/leadership`, { method: "POST", body }),
  addPersonRecognition: (w: string, id: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people/${id}/recognition`, { method: "POST", body }),

  // affiliations
  listAffiliations: (w: string, opts: { person_id?: string; organisation_id?: string } = {}) =>
    request<Record<string, unknown>[]>(`/api/v1/workspaces/${w}/affiliations${qs(opts)}`),
  createAffiliation: (w: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/affiliations`, { method: "POST", body }),

  // identity resolution
  identityCandidates: (w: string, person_id: string) =>
    request<PersonDuplicateCandidate[]>(`/api/v1/workspaces/${w}/identity/candidates${qs({ person_id })}`),
  identityCompare: (w: string, a: string, b: string) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/identity/compare${qs({ a, b })}`),
  identityMerge: (w: string, body: { canonical_person_id: string; merged_person_id: string; reason?: string; evidence?: string }) =>
    request<Record<string, string>>(`/api/v1/workspaces/${w}/identity/merge`, { method: "POST", body }),
  identityUndoMerge: (w: string, mergeId: string) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/identity/merges/${mergeId}/undo`, { method: "POST" }),
  identityAssertDistinct: (w: string, body: { person_a_id: string; person_b_id: string; reason?: string }) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/identity/assert-distinct`, { method: "POST", body }),
  listPersonMerges: (w: string, person_id?: string) =>
    request<PersonMerge[]>(`/api/v1/workspaces/${w}/identity/merges${qs({ person_id })}`),

  // Cricket Statz people import
  listPeopleImports: (w: string) =>
    request<ImportBatch[]>(`/api/v1/workspaces/${w}/people-imports`),
  stagePeopleImport: (w: string, data: Record<string, unknown>, filename?: string) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people-imports`, { method: "POST", body: { data, filename } }),
  detectPeopleImport: (w: string, batchId: string) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people-imports/${batchId}/detect`, { method: "POST" }),
  listPeopleImportRecords: (w: string, batchId: string, opts: { entity_type?: string; status_?: string } = {}) =>
    request<ImportRecord[]>(`/api/v1/workspaces/${w}/people-imports/${batchId}/records${qs(opts)}`),
  decidePeopleImportRecord: (w: string, batchId: string, recordId: string, body: { decision: string; existing_person_id?: string }) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people-imports/${batchId}/records/${recordId}/decide`, { method: "POST", body }),
  promotePeopleImport: (w: string, batchId: string) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people-imports/${batchId}/promote`, { method: "POST" }),
  rollbackPeopleImport: (w: string, batchId: string) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people-imports/${batchId}/rollback`, { method: "POST" }),
  reconcilePeopleImport: (w: string, batchId: string) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people-imports/${batchId}/reconcile`),

  // --- Phase 6 Stage 8: CricketStatz import wizard ---
  cricketStatzImport: (
    w: string,
    body: { data: unknown; people?: unknown; commit: boolean; filename?: string },
  ) => request<CricketStatzImportResult>(`/api/v1/workspaces/${w}/imports/cricketstatz`, { method: "POST", body }),
  listImports: (w: string) => request<ImportBatch[]>(`/api/v1/workspaces/${w}/imports`),

  // --- Phase 8: universal import (any format) ---
  importDetect: (w: string, body: { content?: string; content_base64?: string; filename?: string }) =>
    request<{ candidates: { format_id: string; display_name: string; confidence: number }[] }>(
      `/api/v1/workspaces/${w}/imports/detect`, { method: "POST", body }),
  importGeneric: (
    w: string,
    body: { content?: string; content_base64?: string; filename?: string; format_id?: string; commit: boolean },
  ) => request<GenericImportResult>(`/api/v1/workspaces/${w}/imports/generic`, { method: "POST", body }),

  // --- Phase 9: AutoSync ---
  autosyncDashboard: (w: string) => request<AutoSyncDashboard>(`/api/v1/workspaces/${w}/autosync/dashboard`),
  autosyncConnectors: (w: string) => request<AutoSyncConnector[]>(`/api/v1/workspaces/${w}/autosync/connectors`),
  autosyncSources: (w: string) => request<SyncSource[]>(`/api/v1/workspaces/${w}/autosync/sources`),
  autosyncAddSource: (w: string, body: Record<string, unknown>) =>
    request<SyncSource>(`/api/v1/workspaces/${w}/autosync/sources`, { method: "POST", body }),
  autosyncSetSourceEnabled: (w: string, id: string, enabled: boolean) =>
    request<SyncSource>(`/api/v1/workspaces/${w}/autosync/sources/${id}?enabled=${enabled}`, { method: "PATCH" }),
  autosyncSyncNow: (w: string, body: { source_system: string; kind?: string }) =>
    request<{ ran: boolean; job: SyncJob }>(`/api/v1/workspaces/${w}/autosync/sync-now`, { method: "POST", body }),
  autosyncDiscoverHistory: (w: string, body: { source_system: string; scopes: { key: string }[] }) =>
    request<{ job_id: string }>(`/api/v1/workspaces/${w}/autosync/discover-history`, { method: "POST", body }),
  autosyncReview: (w: string) => request<DiscoveryItem[]>(`/api/v1/workspaces/${w}/autosync/review`),
  autosyncAccept: (w: string, id: string) =>
    request<DiscoveryItem>(`/api/v1/workspaces/${w}/autosync/review/${id}/accept`, { method: "POST" }),
  autosyncReject: (w: string, id: string) =>
    request<DiscoveryItem>(`/api/v1/workspaces/${w}/autosync/review/${id}/reject`, { method: "POST" }),
  autosyncBulk: (w: string, body: { item_ids: string[]; action: "accept" | "reject" }) =>
    request<{ action: string; count: number }>(`/api/v1/workspaces/${w}/autosync/review/bulk`, { method: "POST", body }),
  autosyncCoverage: (w: string) => request<DiscoveryCoverage[]>(`/api/v1/workspaces/${w}/autosync/coverage`),

  // --- Phase 10: Research Centre ---
  researchDashboard: (w: string) => request<ResearchDashboard>(`/api/v1/workspaces/${w}/research/dashboard`),
  researchProjects: (w: string, statusFilter?: string) =>
    request<ResearchProject[]>(`/api/v1/workspaces/${w}/research/projects${statusFilter ? `?status_filter=${statusFilter}` : ""}`),
  researchCreateProject: (w: string, body: Record<string, unknown>) =>
    request<ResearchProject>(`/api/v1/workspaces/${w}/research/projects`, { method: "POST", body }),
  researchUpdateProject: (w: string, id: string, body: Record<string, unknown>) =>
    request<ResearchProject>(`/api/v1/workspaces/${w}/research/projects/${id}`, { method: "PATCH", body }),
  researchSources: (w: string, sourceType?: string) =>
    request<ResearchSource[]>(`/api/v1/workspaces/${w}/research/sources${sourceType ? `?source_type=${sourceType}` : ""}`),
  researchCreateSource: (w: string, body: Record<string, unknown>) =>
    request<ResearchSource>(`/api/v1/workspaces/${w}/research/sources`, { method: "POST", body }),
  researchLinkSource: (w: string, id: string, body: { match_id: string; role?: string }) =>
    request<unknown>(`/api/v1/workspaces/${w}/research/sources/${id}/link`, { method: "POST", body }),

  // --- Phase 6: matches ---
  listMatches: (
    w: string,
    opts: { competition_id?: string; grade_id?: string; season_id?: string; venue_id?: string; classification?: string; status_?: string } = {},
  ) => request<Match[]>(`/api/v1/workspaces/${w}/matches${qs(opts)}`),
  getMatch: (w: string, id: string) => request<MatchDetail>(`/api/v1/workspaces/${w}/matches/${id}`),
  matchSources: (w: string, id: string) =>
    request<{ sources: MatchSource[]; conflicts: MatchSourceConflict[] }>(`/api/v1/workspaces/${w}/matches/${id}/sources`),
  createMatch: (w: string, body: Record<string, unknown>) =>
    request<MatchDetail>(`/api/v1/workspaces/${w}/matches`, { method: "POST", body }),
  updateMatch: (w: string, id: string, body: Record<string, unknown>) =>
    request<Match>(`/api/v1/workspaces/${w}/matches/${id}`, { method: "PATCH", body }),
  setMatchClassification: (w: string, id: string, body: Record<string, unknown>) =>
    request<Match>(`/api/v1/workspaces/${w}/matches/${id}/classification`, { method: "POST", body }),
  setMatchResult: (w: string, id: string, body: Record<string, unknown>) =>
    request<Match>(`/api/v1/workspaces/${w}/matches/${id}/result`, { method: "POST", body }),
  // --- Phase 7.1: scorecard approval workflow (separate from match status) ---
  matchApproval: (w: string, id: string, action: "submit" | "approve" | "reject" | "reopen", reason?: string) =>
    request<Match>(`/api/v1/workspaces/${w}/matches/${id}/${action}`, { method: "POST", body: { reason: reason ?? null } }),
  setMatchTeam: (w: string, id: string, body: Record<string, unknown>) =>
    request<MatchTeam>(`/api/v1/workspaces/${w}/matches/${id}/teams`, { method: "POST", body }),
  setMatchToss: (w: string, id: string, body: Record<string, unknown>) =>
    request<Match>(`/api/v1/workspaces/${w}/matches/${id}/toss`, { method: "POST", body }),
  getMatchConditions: (w: string, id: string) =>
    request<ResolvedConditions>(`/api/v1/workspaces/${w}/matches/${id}/conditions`),

  // --- Phase 6: innings ---
  listInnings: (w: string, matchId: string) =>
    request<Innings[]>(`/api/v1/workspaces/${w}/matches/${matchId}/innings`),
  createInnings: (w: string, matchId: string, body: Record<string, unknown>) =>
    request<Innings>(`/api/v1/workspaces/${w}/matches/${matchId}/innings`, { method: "POST", body }),
  updateInnings: (w: string, matchId: string, id: string, body: Record<string, unknown>) =>
    request<Innings>(`/api/v1/workspaces/${w}/matches/${matchId}/innings/${id}`, { method: "PATCH", body }),
  setInningsOfficialTotal: (w: string, matchId: string, id: string, body: Record<string, unknown>) =>
    request<Innings>(`/api/v1/workspaces/${w}/matches/${matchId}/innings/${id}/official-total`, { method: "POST", body }),
  getInningsTotals: (w: string, matchId: string, id: string) =>
    request<InningsTotals>(`/api/v1/workspaces/${w}/matches/${matchId}/innings/${id}/totals`),
  validateInnings: (w: string, matchId: string, id: string) =>
    request<Warnings>(`/api/v1/workspaces/${w}/matches/${matchId}/innings/${id}/validate`),

  // --- Phase 6: batting ---
  listBatting: (w: string, iid: string) =>
    request<BattingEntry[]>(`/api/v1/workspaces/${w}/innings/${iid}/batting`),
  createBatting: (w: string, iid: string, body: Record<string, unknown>) =>
    request<BattingEntry>(`/api/v1/workspaces/${w}/innings/${iid}/batting`, { method: "POST", body }),
  updateBatting: (w: string, iid: string, id: string, body: Record<string, unknown>) =>
    request<BattingEntry>(`/api/v1/workspaces/${w}/innings/${iid}/batting/${id}`, { method: "PATCH", body }),
  deleteBatting: (w: string, iid: string, id: string) =>
    request<void>(`/api/v1/workspaces/${w}/innings/${iid}/batting/${id}`, { method: "DELETE" }),
  reorderBatting: (w: string, iid: string, ordered_ids: string[]) =>
    request<BattingEntry[]>(`/api/v1/workspaces/${w}/innings/${iid}/batting/reorder`, { method: "POST", body: { ordered_ids } }),
  battingCard: (w: string, iid: string) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/innings/${iid}/batting/card`),
  validateBatting: (w: string, iid: string) =>
    request<Warnings>(`/api/v1/workspaces/${w}/innings/${iid}/batting/validate`),

  // --- Phase 6: bowling ---
  listBowling: (w: string, iid: string) =>
    request<BowlingEntry[]>(`/api/v1/workspaces/${w}/innings/${iid}/bowling`),
  createBowling: (w: string, iid: string, body: Record<string, unknown>) =>
    request<BowlingEntry>(`/api/v1/workspaces/${w}/innings/${iid}/bowling`, { method: "POST", body }),
  updateBowling: (w: string, iid: string, id: string, body: Record<string, unknown>) =>
    request<BowlingEntry>(`/api/v1/workspaces/${w}/innings/${iid}/bowling/${id}`, { method: "PATCH", body }),
  deleteBowling: (w: string, iid: string, id: string) =>
    request<void>(`/api/v1/workspaces/${w}/innings/${iid}/bowling/${id}`, { method: "DELETE" }),
  bowlingCard: (w: string, iid: string) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/innings/${iid}/bowling/card`),
  validateBowling: (w: string, iid: string) =>
    request<Warnings>(`/api/v1/workspaces/${w}/innings/${iid}/bowling/validate`),

  // --- Phase 6: fall of wicket & partnerships ---
  listFow: (w: string, iid: string) =>
    request<FallOfWicket[]>(`/api/v1/workspaces/${w}/innings/${iid}/fall-of-wicket`),
  createFow: (w: string, iid: string, body: Record<string, unknown>) =>
    request<FallOfWicket>(`/api/v1/workspaces/${w}/innings/${iid}/fall-of-wicket`, { method: "POST", body }),
  updateFow: (w: string, iid: string, id: string, body: Record<string, unknown>) =>
    request<FallOfWicket>(`/api/v1/workspaces/${w}/innings/${iid}/fall-of-wicket/${id}`, { method: "PATCH", body }),
  deleteFow: (w: string, iid: string, id: string) =>
    request<void>(`/api/v1/workspaces/${w}/innings/${iid}/fall-of-wicket/${id}`, { method: "DELETE" }),
  listPartnerships: (w: string, iid: string) =>
    request<Partnership[]>(`/api/v1/workspaces/${w}/innings/${iid}/partnerships`),
  createPartnership: (w: string, iid: string, body: Record<string, unknown>) =>
    request<Partnership>(`/api/v1/workspaces/${w}/innings/${iid}/partnerships`, { method: "POST", body }),
  updatePartnership: (w: string, iid: string, id: string, body: Record<string, unknown>) =>
    request<Partnership>(`/api/v1/workspaces/${w}/innings/${iid}/partnerships/${id}`, { method: "PATCH", body }),
  deletePartnership: (w: string, iid: string, id: string) =>
    request<void>(`/api/v1/workspaces/${w}/innings/${iid}/partnerships/${id}`, { method: "DELETE" }),
  validatePartnerships: (w: string, iid: string) =>
    request<Warnings>(`/api/v1/workspaces/${w}/innings/${iid}/partnerships-validate`),
  derivePartnerships: (w: string, iid: string) =>
    request<Partnership[]>(`/api/v1/workspaces/${w}/innings/${iid}/partnerships/derive`, { method: "POST" }),
};
