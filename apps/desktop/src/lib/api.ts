/**
 * Typed client for the OneStats backend (the desktop-to-backend interface).
 * Base URL from VITE_ONESTATS_API_URL (default localhost:8000). The session token is held
 * in localStorage and sent as a Bearer header. No secrets beyond the session token.
 */

// The backend base URL is runtime-configurable (Phase 17): a saved override (standalone-local, or a
// shared server a client connects to) takes precedence over the build-time default. This lets one build
// serve the standalone, server and additional-client install paths without rebuilding.
const DEFAULT_BASE: string =
  import.meta.env.VITE_ONESTATS_API_URL ?? "http://localhost:8000";
const API_URL_KEY = "onestats.apiUrl";

export function getApiBase(): string {
  try {
    return (localStorage.getItem(API_URL_KEY) || "").trim() || DEFAULT_BASE;
  } catch {
    return DEFAULT_BASE;
  }
}
export function setApiBase(url: string | null): void {
  try {
    if (url && url.trim()) localStorage.setItem(API_URL_KEY, url.trim().replace(/\/+$/, ""));
    else localStorage.removeItem(API_URL_KEY);
  } catch {
    /* storage may be unavailable */
  }
}

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
    resp = await fetch(`${getApiBase()}${path}`, { method: opts.method ?? "GET", headers, body });
  } catch {
    throw new ApiError(`Cannot reach the OneStats backend at ${getApiBase()}. Is it running?`);
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
  must_change_password?: boolean;
}
export interface ManagedUser {
  id: string;
  username: string;
  display_name: string | null;
  status: string;
  is_super_admin: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string | null;
}
export interface UserInvitation {
  id: string;
  user_id: string;
  username: string;
  status: string;
  expires_at: string | null;
}
export interface BattingSplit {
  label: string; matches: number; innings: number; runs: number; not_outs: number;
  average: number | null; high_score: string | null; fifties: number; hundreds: number;
}
export interface BowlingSplit {
  label: string; matches: number; overs: string; maidens: number; runs: number; wickets: number;
  average: number | null; economy: number | null; best: string | null;
}
export interface PlayerAnalysis {
  splits: Record<"opposition" | "ground" | "grade" | "format", { batting: BattingSplit[]; bowling: BowlingSplit[] }>;
  best_batting: { score: string; runs: number; opposition: string | null; ground: string | null; date: string | null; position: number | null }[];
  best_bowling: { figures: string; wickets: number; runs: number | null; opposition: string | null; ground: string | null; date: string | null }[];
  partnerships: { runs: number; unbroken: boolean; wicket: number | null; partner: string; opposition: string | null; ground: string | null; date: string | null }[];
  partnership_totals: { partner: string; runs: number; stands: number; matches: number; best: number; average: number | null }[];
  dismissals: { how_out: { type: string; count: number }[]; dismissed_by: { player: string; count: number }[] };
  scores: { innings: { date: string | null; runs: number; not_out: boolean }[]; frequency: { range: string; count: number }[] };
}
export interface PlayerFullProfile {
  person_id: string;
  detail: { batting_style: string | null; bowling_style: string | null; biography: string | null; is_wicketkeeper: boolean;
    numbers: string[]; leadership: { label: string; seasons: string[] }[]; recognition: { label: string; seasons: string[] }[] };
  span: {
    first: { date: string | null; opposition: string | null } | null;
    last: { date: string | null; opposition: string | null } | null;
  };
  career: {
    matches: number;
    batting: Record<string, number | null>;
    bowling: Record<string, number | null>;
    fielding: Record<string, number>;
    captaincy: Record<string, number>;
    derived_role: string | null;
    has_batting: boolean;
    has_bowling: boolean;
    has_captaincy: boolean;
    has_keeping: boolean;
  };
  seasons: Record<string, unknown>[];
  clubs: { team_id: string; team: string; org_id: string; club: string }[];
  records: { title: string; value: number | null; tied: boolean; known_minimum: boolean }[];
  grand_finals: {
    appearances: number;
    premierships: number;
    batting: Record<string, number | null>;
    bowling: Record<string, number | null>;
    fielding: Record<string, number>;
    captaincy: Record<string, number>;
    matches: Record<string, unknown>[];
    has_batting: boolean;
    has_bowling: boolean;
    has_captaincy: boolean;
  };
  milestones: { metrics: Record<string, { label: string; total: number; known_minimum: boolean;
    milestones: { threshold: number; state: string }[]; next: { threshold: number; to_go: number } | null }> };
  badges: { calculated: { label: string; source: string; state: string }[];
    awarded: { label: string; source: string; status?: string }[] };
  honours: Record<string, unknown>[];
}
export interface RecordHolder {
  player: string;
  subject_id: string;
  value: number;
  tied: boolean;
  known_minimum: boolean;
  club?: string | null;
}
export interface RecordCategory {
  title: string;
  metric: string;
  value: number | null;
  holder: RecordHolder | null;
  ties: { player: string; subject_id: string; club?: string | null }[];
  ranking: { rank: number; player: string; value: number; club?: string | null }[];
}
export interface StatColumn {
  key: string;
  label: string;
  align: "left" | "right" | "center";
  decimals: number | null;
}
export interface StatReport {
  report: string;
  title: string;
  columns: StatColumn[];
  rows: Record<string, unknown>[];
}
export interface CatalogueReport {
  id: string;
  name: string;
  category: string;
  description: string;
  filters: string[];
  qualification: string | null;
  limitations: string | null;
  split_default: string | null;
  csv: boolean;
  pdf: boolean;
}
export interface ReportCatalogue {
  categories: { category: string; reports: CatalogueReport[] }[];
  count: number;
}
export interface Publication {
  id: string;
  kind: string;
  report_id: string | null;
  person_id: string | null;
  title: string;
  filters?: Record<string, unknown>;
  slug: string;
  status: string;
  stale?: boolean;
  checksum?: string | null;
  snapshot_at?: string | null;
  public_path?: string;
  public_url?: string | null;
  json_path?: string;
}
export interface AskAnswer {
  question: string;
  matched: boolean;
  message?: string;
  confidence?: string;
  report_id?: string;
  report_name?: string;
  category?: string;
  interpretation?: string;
  scope?: string[];
  columns?: StatColumn[];
  rows?: Record<string, unknown>[];
  qualifications?: string[];
  answer_summary?: string | null;
  suggestions?: { id: string; name: string; category: string }[];
}
export interface CaptaincyCompareRow {
  subject_id: string;
  player: string;
  captained: number;
  wins: number;
  losses: number;
  draws: number;
  ties: number;
  no_results: number;
  win_pct: number | null;
  gf_captained: number;
  gf_wins: number;
  consecutive_wins: number;
}
export interface StatLadderRow {
  position: number;
  team_id: string;
  played: number;
  wins: number;
  losses: number;
  draws: number;
  ties: number;
  no_results: number;
  bonus: number;
  points: number;
}
export interface StatLadder {
  competition_id: string;
  scheme: Record<string, number>;
  standings: StatLadderRow[];
  note: string;
}
export interface WorkspaceDashboard {
  totals: {
    matches: number; players: number; approved_scorecards: number; seasons: number;
    competitions: number; organisations: number; media_assets: number;
  };
  attention: {
    scorecards_awaiting_approval: number; possible_duplicate_matches: number;
    research_conflicts: number; failed_autosync_jobs: number;
  };
  research: { projects_active: number; incomplete_scorecards: number; open_research_tasks: number; sources: number };
  recent_activity: { action: string; category: string; entity: string | null; at: string | null; actor: string | null }[];
  is_empty: boolean;
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
export interface ResearchTask {
  id: string;
  title: string;
  description: string | null;
  status: "open" | "in_progress" | "resolved" | "dismissed";
  gap_kind: string | null;
  priority: number;
  assigned_to: string | null;
  project_id: string | null;
}
export interface ResearchMatchRow {
  match_id: string;
  match_date: string | null;
  date_precision: string;
  approval_status: string;
  round: string | null;
  result_type: string | null;
  sources: number;
}
export interface ResearchExtraction {
  id: string;
  source_id: string;
  page: number;
  method: string;
  ocr_text: string | null;
  corrected_text: string | null;
  confidence: number | null;
  status: string;
}
export interface TimelineSeason {
  season_id: string;
  label: string;
  total_matches: number;
  verified_matches: number;
  disputed_matches: number;
  matches_without_result: number;
  coverage_class: string;
  computed_class: string;
  assessment_basis: string | null;
}
export interface ResearchTimeline {
  seasons: TimelineSeason[];
  methodology: { note: string };
}
export interface GapCategory {
  count: number;
  sample?: { match_id: string; match_date: string | null; round: string | null }[];
}
export type ResearchGaps = Record<string, GapCategory>;
export interface MediaProviderInfo {
  name: string;
  available: boolean;
  default: boolean;
  note: string | null;
}
export interface MediaAsset {
  id: string;
  storage_provider: "internal" | "onevault" | "external";
  storage_locator: string | null;
  original_filename: string | null;
  content_type: string | null;
  file_bytes: number | null;
  sha256: string | null;
  kind: string;
  title: string | null;
  description: string | null;
  copyright_status: string | null;
  licence: string | null;
  attribution: string | null;
  visibility: "private" | "workspace" | "publishable";
  publication_eligible: boolean;
  sensitive: boolean;
  junior_protected: boolean;
  thumbnail_ref: string | null;
  created_at: string;
}
export interface MediaVerifyReport {
  total: number;
  verified_ok: number;
  missing: string[];
  mismatch: string[];
  unverifiable: string[];
  ok: boolean;
}
export interface HeritageCollection {
  id: string;
  name: string;
  description: string | null;
  items: number;
}
export interface HeritageItem {
  id: string;
  media_asset_id: string | null;
  title: string | null;
  significance: string | null;
  description: string | null;
  display_order: number;
  publication_eligible: boolean;
}
export interface ResearchAlias {
  id: string;
  entity_type: string;
  entity_id: string | null;
  alias: string;
  alias_kind: string | null;
  language: string | null;
}
export interface ProvenanceClaim {
  id: string;
  match_id: string;
  field_path: string;
  source_id: string | null;
  claimed_value: string | null;
  normalised_value: string | null;
  status: "claimed" | "accepted" | "rejected" | "superseded";
  confidence: number | null;
  decision_note: string | null;
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
export interface IntegrationField {
  key: string;
  label: string;
  default?: string | null;
  required: boolean;
}
export interface IntegrationProvider {
  id: string;
  name: string;
  testable: boolean;
  custom_url: boolean;
  notes: string | null;
  secret_fields: IntegrationField[];
  config_fields: IntegrationField[];
}
export interface IntegrationCredential {
  id: string;
  provider: string;
  label: string;
  enabled: boolean;
  status: string;
  config: Record<string, unknown>;
  has_secret: boolean;
  last_test_ok: boolean | null;
  last_test_at: string | null;
  last_test_message: string | null;
  last_success_at: string | null;
  created_at: string | null;
  // present only on a Test response
  test_ok?: boolean;
  test_message?: string;
}
export interface IntegrationAuditEntry {
  action: string;
  actor: string | null;
  provider: string | null;
  at: string | null;
}
export interface MemberPortalItem {
  title: string;
  kind: string;
  slug: string;
  status: string;
  public: boolean;
  stale: boolean;
  path: string | null;
  snapshot_at: string | null;
}
export interface MemberPortal {
  club: string;
  primary: string;
  items: MemberPortalItem[];
  public_count: number;
  member_only_count: number;
  workspace_id: string;
  ask: { enabled: boolean; endpoint: string | null };
}
export interface UploadSession {
  id: string;
  status: string;
  scope: Record<string, unknown>;
  upload_count: number;
  expires_at: string | null;
  created_at: string | null;
  last_used_at: string | null;
  active: boolean;
  // present only on create (returned once)
  token?: string;
  upload_path?: string;
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
export interface DismissalFielder {
  id: string;
  person_id: string;
  role: string;
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
  baseUrl: getApiBase(),
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
  changePassword: (current_password: string, new_password: string) =>
    request<void>("/api/v1/auth/change-password", { method: "POST", body: { current_password, new_password } }),
  acceptInvitation: (token: string, new_password: string) =>
    request<{ user_id: string; username: string }>("/api/v1/invitations/accept", { method: "POST", auth: false, body: { token, new_password } }),
  // --- System Administration: user management (Super Admin) ---
  usersList: () => request<ManagedUser[]>("/api/v1/users"),
  userCreate: (body: { username: string; display_name?: string; is_super_admin?: boolean }) =>
    request<{ user_id: string; username: string; temp_password: string; temp_password_expires_at: string }>("/api/v1/users", { method: "POST", body }),
  userUpdate: (id: string, body: { display_name?: string; status?: string; is_super_admin?: boolean }) =>
    request<{ updated: boolean }>(`/api/v1/users/${id}`, { method: "PATCH", body }),
  userResetPassword: (id: string) =>
    request<{ user_id: string; temp_password: string; temp_password_expires_at: string }>(`/api/v1/users/${id}/reset-password`, { method: "POST" }),
  userAudit: (id: string) =>
    request<{ logins: { success: boolean; ip: string | null; at: string | null }[]; admin_events: { action: string; actor: string | null; at: string | null }[] }>(`/api/v1/users/${id}/audit`),
  userAssignWorkspaceRole: (id: string, workspace_id: string, role: string) =>
    request<{ granted: boolean }>(`/api/v1/users/${id}/workspace-roles`, { method: "POST", body: { workspace_id, role } }),
  invitationsList: () => request<UserInvitation[]>("/api/v1/invitations"),
  invitationCreate: (body: { username: string; display_name?: string; is_super_admin?: boolean }) =>
    request<{ invitation_id: string; user_id: string; username: string; token: string; expires_at: string }>("/api/v1/invitations", { method: "POST", body }),
  invitationRevoke: (id: string) =>
    request<{ revoked: boolean }>(`/api/v1/invitations/${id}/revoke`, { method: "POST" }),

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
  brandingLogoObjectUrl: async (workspaceId: string): Promise<string | null> => {
    const headers: Record<string, string> = {};
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
    const resp = await fetch(`${getApiBase()}/api/v1/workspaces/${workspaceId}/branding/logo`, { headers });
    if (!resp.ok) return null;
    return URL.createObjectURL(await resp.blob());
  },

  // --- Workspace dashboard (home command centre) ---
  workspaceDashboard: (w: string) => request<WorkspaceDashboard>(`/api/v1/workspaces/${w}/dashboard`),

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
  // Phase 13 player profile (stats composed from the one engine)
  profileFull: (w: string, id: string) =>
    request<PlayerFullProfile>(`/api/v1/workspaces/${w}/people/${id}/full-profile`),
  profileSeasons: (w: string, id: string) =>
    request<Record<string, unknown>[]>(`/api/v1/workspaces/${w}/people/${id}/seasons`),
  profileMatches: (w: string, id: string) =>
    request<Record<string, unknown>[]>(`/api/v1/workspaces/${w}/people/${id}/matches`),
  profileAnalysis: (w: string, id: string) =>
    request<PlayerAnalysis>(`/api/v1/workspaces/${w}/people/${id}/analysis`),
  profilePdfUrl: async (w: string, id: string): Promise<string> => {
    const headers: Record<string, string> = {};
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
    const resp = await fetch(`${getApiBase()}/api/v1/workspaces/${w}/people/${id}/profile.pdf`, { headers });
    if (!resp.ok) throw new ApiError(`Profile PDF failed (${resp.status})`, resp.status);
    return URL.createObjectURL(await resp.blob());
  },
  upsertProfile: (w: string, id: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people/${id}/profile`, { method: "PUT", body }),
  personPhotos: (w: string, id: string) =>
    request<{ id: string; caption: string | null; public_visible: boolean }[]>(`/api/v1/workspaces/${w}/people/${id}/photos`),
  personPhotoUrl: async (w: string, photoId: string): Promise<string> => {
    const headers: Record<string, string> = {};
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
    const resp = await fetch(`${getApiBase()}/api/v1/workspaces/${w}/people/photos/${photoId}/file`, { headers });
    if (!resp.ok) throw new ApiError(`photo ${resp.status}`, resp.status);
    return URL.createObjectURL(await resp.blob());
  },
  addPersonNumber: (w: string, id: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people/${id}/numbers`, { method: "POST", body }),
  addPersonLeadership: (w: string, id: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people/${id}/leadership`, { method: "POST", body }),
  addPersonRecognition: (w: string, id: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/api/v1/workspaces/${w}/people/${id}/recognition`, { method: "POST", body }),
  deletePersonNumber: (w: string, id: string, attrId: string) =>
    request<void>(`/api/v1/workspaces/${w}/people/${id}/numbers/${attrId}`, { method: "DELETE" }),
  deletePersonLeadership: (w: string, id: string, attrId: string) =>
    request<void>(`/api/v1/workspaces/${w}/people/${id}/leadership/${attrId}`, { method: "DELETE" }),
  deletePersonRecognition: (w: string, id: string, attrId: string) =>
    request<void>(`/api/v1/workspaces/${w}/people/${id}/recognition/${attrId}`, { method: "DELETE" }),

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

  // --- API & Integrations management (workspace-scoped; admin-gated) ---
  integrationProviders: (w: string) =>
    request<IntegrationProvider[]>(`/api/v1/workspaces/${w}/integrations/providers`),
  integrationCredentials: (w: string) =>
    request<IntegrationCredential[]>(`/api/v1/workspaces/${w}/integrations/credentials`),
  integrationCreate: (w: string, body: { provider: string; label?: string; secrets: Record<string, string>; config: Record<string, unknown> }) =>
    request<IntegrationCredential>(`/api/v1/workspaces/${w}/integrations/credentials`, { method: "POST", body }),
  integrationRotate: (w: string, id: string, secrets: Record<string, string>) =>
    request<IntegrationCredential>(`/api/v1/workspaces/${w}/integrations/credentials/${id}/rotate`, { method: "POST", body: { secrets } }),
  integrationSetEnabled: (w: string, id: string, enabled: boolean) =>
    request<IntegrationCredential>(`/api/v1/workspaces/${w}/integrations/credentials/${id}`, { method: "PATCH", body: { enabled } }),
  integrationRevoke: (w: string, id: string) =>
    request<IntegrationCredential>(`/api/v1/workspaces/${w}/integrations/credentials/${id}/revoke`, { method: "POST" }),
  integrationTest: (w: string, id: string) =>
    request<IntegrationCredential>(`/api/v1/workspaces/${w}/integrations/credentials/${id}/test`, { method: "POST" }),
  integrationAudit: (w: string) =>
    request<IntegrationAuditEntry[]>(`/api/v1/workspaces/${w}/integrations/audit`),

  // --- Authenticated member portal (read-only) ---
  memberPortal: (w: string) => request<MemberPortal>(`/api/v1/workspaces/${w}/portal`),

  // --- Mobile upload pairing (deliverable 20a) ---
  mobileUploadSessions: (w: string) =>
    request<UploadSession[]>(`/api/v1/workspaces/${w}/mobile-upload/sessions`),
  mobileUploadCreate: (w: string, body: { ttl_minutes?: number; scope?: Record<string, unknown> }) =>
    request<UploadSession>(`/api/v1/workspaces/${w}/mobile-upload/sessions`, { method: "POST", body }),
  mobileUploadRevoke: (w: string, id: string) =>
    request<UploadSession>(`/api/v1/workspaces/${w}/mobile-upload/sessions/${id}/revoke`, { method: "POST" }),

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
  researchUploadSourceFile: (w: string, id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<ResearchSource & { duplicate_of: string | null }>(
      `/api/v1/workspaces/${w}/research/sources/${id}/file`, { method: "POST", form });
  },
  researchEditions: (w: string, publication: string) =>
    request<ResearchSource[]>(`/api/v1/workspaces/${w}/research/publications/${encodeURIComponent(publication)}/editions`),
  researchLinkSource: (w: string, id: string, body: { match_id: string; role?: string }) =>
    request<unknown>(`/api/v1/workspaces/${w}/research/sources/${id}/link`, { method: "POST", body }),
  researchExtractions: (w: string, id: string) =>
    request<ResearchExtraction[]>(`/api/v1/workspaces/${w}/research/sources/${id}/extractions`),
  researchExtract: (w: string, id: string) =>
    request<ResearchExtraction>(`/api/v1/workspaces/${w}/research/sources/${id}/extract`, { method: "POST", body: {} }),
  researchCorrect: (w: string, extractionId: string, corrected_text: string) =>
    request<ResearchExtraction>(`/api/v1/workspaces/${w}/research/extractions/${extractionId}/correct`,
      { method: "POST", body: { corrected_text } }),
  researchTimeline: (w: string) => request<ResearchTimeline>(`/api/v1/workspaces/${w}/research/timeline`),
  researchGaps: (w: string) => request<ResearchGaps>(`/api/v1/workspaces/${w}/research/gaps`),
  researchTasks: (w: string, statusFilter?: string) =>
    request<ResearchTask[]>(`/api/v1/workspaces/${w}/research/tasks${statusFilter ? `?status_filter=${statusFilter}` : ""}`),
  researchCreateTask: (w: string, body: Record<string, unknown>) =>
    request<ResearchTask>(`/api/v1/workspaces/${w}/research/tasks`, { method: "POST", body }),
  researchUpdateTask: (w: string, id: string, body: Record<string, unknown>) =>
    request<ResearchTask>(`/api/v1/workspaces/${w}/research/tasks/${id}`, { method: "PATCH", body }),
  researchMatches: (w: string, approvalStatus?: string) =>
    request<ResearchMatchRow[]>(`/api/v1/workspaces/${w}/research/matches${approvalStatus ? `?approval_status=${approvalStatus}` : ""}`),
  researchStartReconstruction: (w: string, body: Record<string, unknown>) =>
    request<{ id: string }>(`/api/v1/workspaces/${w}/research/reconstructions`, { method: "POST", body }),
  researchVerify: (w: string, matchId: string, decision: string, reason?: string) =>
    request<unknown>(`/api/v1/workspaces/${w}/research/matches/${matchId}/verify`,
      { method: "POST", body: { decision, reason: reason ?? null } }),
  researchSubmitForReview: (w: string, matchId: string) =>
    request<unknown>(`/api/v1/workspaces/${w}/research/matches/${matchId}/submit-for-review`, { method: "POST", body: {} }),
  researchAttachSource: (w: string, matchId: string, body: { source_id: string; role?: string }) =>
    request<unknown>(`/api/v1/workspaces/${w}/research/matches/${matchId}/attach-source`, { method: "POST", body }),
  researchMatchSources: (w: string, matchId: string) =>
    request<ResearchSource[]>(`/api/v1/workspaces/${w}/research/matches/${matchId}/sources`),
  researchMatchProvenance: (w: string, matchId: string) =>
    request<ProvenanceClaim[]>(`/api/v1/workspaces/${w}/research/matches/${matchId}/provenance`),
  researchRecordClaim: (w: string, matchId: string, body: Record<string, unknown>) =>
    request<ProvenanceClaim>(`/api/v1/workspaces/${w}/research/matches/${matchId}/provenance`, { method: "POST", body }),
  researchConflicts: (w: string, matchId: string) =>
    request<{ field_path: string; claims: ProvenanceClaim[] }[]>(`/api/v1/workspaces/${w}/research/matches/${matchId}/conflicts`),
  researchAcceptClaim: (w: string, claimId: string, note?: string) =>
    request<ProvenanceClaim>(`/api/v1/workspaces/${w}/research/provenance/${claimId}/accept`, { method: "POST", body: { note: note ?? null } }),
  researchRejectClaim: (w: string, claimId: string, note?: string) =>
    request<ProvenanceClaim>(`/api/v1/workspaces/${w}/research/provenance/${claimId}/reject`, { method: "POST", body: { note: note ?? null } }),
  researchAliases: (w: string) => request<ResearchAlias[]>(`/api/v1/workspaces/${w}/research/aliases`),
  researchCreateAlias: (w: string, body: Record<string, unknown>) =>
    request<ResearchAlias>(`/api/v1/workspaces/${w}/research/aliases`, { method: "POST", body }),
  researchExpandAliases: (w: string, term: string) =>
    request<{ term: string; expanded: string[] }>(`/api/v1/workspaces/${w}/research/aliases/expand?term=${encodeURIComponent(term)}`),
  researchSourceFileObjectUrl: async (w: string, id: string): Promise<string> => {
    const headers: Record<string, string> = {};
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
    const resp = await fetch(`${getApiBase()}/api/v1/workspaces/${w}/research/sources/${id}/file`, { headers });
    if (!resp.ok) throw new ApiError(`Could not load document (${resp.status})`, resp.status);
    return URL.createObjectURL(await resp.blob());
  },

  // --- Phase 11: Media Archive ---
  mediaProviders: (w: string) => request<MediaProviderInfo[]>(`/api/v1/workspaces/${w}/media/providers`),
  mediaAssets: (w: string, kind?: string) =>
    request<MediaAsset[]>(`/api/v1/workspaces/${w}/media/assets${kind ? `?kind=${kind}` : ""}`),
  mediaPublishable: (w: string) => request<MediaAsset[]>(`/api/v1/workspaces/${w}/media/assets/publishable`),
  mediaUpload: (w: string, file: File, kind: string, title?: string) => {
    const form = new FormData();
    form.append("file", file);
    const q = `?kind=${encodeURIComponent(kind)}${title ? `&title=${encodeURIComponent(title)}` : ""}`;
    return request<MediaAsset & { duplicate_of: string | null }>(`/api/v1/workspaces/${w}/media/assets${q}`,
      { method: "POST", form });
  },
  mediaAddExternal: (w: string, body: Record<string, unknown>) =>
    request<MediaAsset>(`/api/v1/workspaces/${w}/media/assets/external`, { method: "POST", body }),
  mediaUpdateAsset: (w: string, id: string, body: Record<string, unknown>) =>
    request<MediaAsset>(`/api/v1/workspaces/${w}/media/assets/${id}`, { method: "PATCH", body }),
  mediaVerify: (w: string) => request<MediaVerifyReport>(`/api/v1/workspaces/${w}/media/backup/verify`),
  mediaHeritageCollections: (w: string) =>
    request<HeritageCollection[]>(`/api/v1/workspaces/${w}/media/heritage/collections`),
  mediaCreateCollection: (w: string, body: Record<string, unknown>) =>
    request<HeritageCollection>(`/api/v1/workspaces/${w}/media/heritage/collections`, { method: "POST", body }),
  mediaCollectionItems: (w: string, id: string) =>
    request<HeritageItem[]>(`/api/v1/workspaces/${w}/media/heritage/collections/${id}/items`),
  mediaAddHeritageItem: (w: string, id: string, body: Record<string, unknown>) =>
    request<HeritageItem>(`/api/v1/workspaces/${w}/media/heritage/collections/${id}/items`, { method: "POST", body }),
  mediaThumbnailObjectUrl: async (w: string, id: string): Promise<string> => {
    const headers: Record<string, string> = {};
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
    const resp = await fetch(`${getApiBase()}/api/v1/workspaces/${w}/media/assets/${id}/thumbnail`, { headers });
    if (!resp.ok) throw new ApiError(`thumbnail ${resp.status}`, resp.status);
    return URL.createObjectURL(await resp.blob());
  },

  // --- Phase 12: statistics reports ---
  statsReportCatalogue: (w: string) =>
    request<{ report: string; title: string }[]>(`/api/v1/workspaces/${w}/stats/reports`),
  statsReport: (w: string, report: string, q: Record<string, string | number | undefined> = {}) => {
    const qs2 = Object.entries(q).filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
    return request<StatReport>(`/api/v1/workspaces/${w}/stats/reports/${report}${qs2 ? `?${qs2}` : ""}`);
  },
  statsUsedFormats: (w: string) =>
    request<string[]>(`/api/v1/workspaces/${w}/stats/formats`),
  statsSavedList: (w: string) =>
    request<{ id: string; name: string; report: string; config: Record<string, unknown> | null; shared: boolean; created_by: string | null }[]>(`/api/v1/workspaces/${w}/stats/saved-reports`),
  statsSaveReport: (w: string, body: { name: string; report: string; config?: Record<string, unknown>; shared?: boolean }) =>
    request<{ id: string }>(`/api/v1/workspaces/${w}/stats/saved-reports`, { method: "POST", body }),
  statsUpdateSaved: (w: string, id: string, body: Record<string, unknown>) =>
    request<unknown>(`/api/v1/workspaces/${w}/stats/saved-reports/${id}`, { method: "PATCH", body }),
  statsDeleteSaved: (w: string, id: string) =>
    request<{ deleted: boolean }>(`/api/v1/workspaces/${w}/stats/saved-reports/${id}`, { method: "DELETE" }),
  statsLadder: (w: string, competitionId: string, season_id?: string) =>
    request<StatLadder>(`/api/v1/workspaces/${w}/stats/ladder?competition_id=${competitionId}${season_id ? `&season_id=${season_id}` : ""}`),
  statsReportPdfUrl: async (w: string, report: string, q: Record<string, string | number | undefined> = {}): Promise<string> => {
    const qs2 = Object.entries(q).filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
    const headers: Record<string, string> = {};
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
    const resp = await fetch(`${getApiBase()}/api/v1/workspaces/${w}/stats/reports/${report}/pdf${qs2 ? `?${qs2}` : ""}`, { headers });
    if (!resp.ok) throw new ApiError(`PDF export failed (${resp.status})`, resp.status);
    return URL.createObjectURL(await resp.blob());
  },
  // --- Report Catalogue (the full categorised library over the one engine) ---
  statsCatalogue: (w: string) =>
    request<ReportCatalogue>(`/api/v1/workspaces/${w}/stats/catalogue`),
  statsReportCsvUrl: async (w: string, report: string, q: Record<string, string | number | undefined> = {}): Promise<string> => {
    const qs2 = Object.entries(q).filter(([, v]) => v !== undefined && v !== "")
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
    const headers: Record<string, string> = {};
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
    const resp = await fetch(`${getApiBase()}/api/v1/workspaces/${w}/stats/reports/${report}/csv${qs2 ? `?${qs2}` : ""}`, { headers });
    if (!resp.ok) throw new ApiError(`CSV export failed (${resp.status})`, resp.status);
    return URL.createObjectURL(await resp.blob());
  },
  askOneStats: (w: string, question: string, top = 10) =>
    request<AskAnswer>(`/api/v1/workspaces/${w}/ask`, { method: "POST", body: { question, top } }),
  // --- Phase 15: website publishing ---
  publicationsList: (w: string) =>
    request<Publication[]>(`/api/v1/workspaces/${w}/publications`),
  publicationCreate: (w: string, body: { kind: string; title: string; report_id?: string; person_id?: string; filters?: Record<string, unknown> }) =>
    request<Publication>(`/api/v1/workspaces/${w}/publications`, { method: "POST", body }),
  publicationSetStatus: (w: string, id: string, status: string) =>
    request<{ id: string; status: string }>(`/api/v1/workspaces/${w}/publications/${id}/status`, { method: "POST", body: { status } }),
  publicationRefresh: (w: string, id: string) =>
    request<{ id: string; status: string }>(`/api/v1/workspaces/${w}/publications/${id}/refresh`, { method: "POST" }),
  publicationRefreshAll: (w: string) =>
    request<{ refreshed: number }>(`/api/v1/workspaces/${w}/publications/refresh`, { method: "POST" }),
  publicationExport: (w: string, id: string) =>
    request<{ files: Record<string, string> }>(`/api/v1/workspaces/${w}/publications/${id}/export`),
  publicPreviewUrl: (path: string) => `${getApiBase()}${path}`,
  statsCaptaincyCompare: (w: string, personIds: string[]) =>
    request<{ captains: CaptaincyCompareRow[] }>(`/api/v1/workspaces/${w}/stats/captaincy/compare?person_ids=${personIds.join(",")}`),
  statsCatalogueIndexUrl: async (w: string): Promise<string> => {
    const headers: Record<string, string> = {};
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
    const resp = await fetch(`${getApiBase()}/api/v1/workspaces/${w}/stats/catalogue/index.pdf`, { headers });
    if (!resp.ok) throw new ApiError(`Catalogue index failed (${resp.status})`, resp.status);
    return URL.createObjectURL(await resp.blob());
  },

  // --- Phase 13: records & achievements ---
  recordsAllTime: (w: string, q: Record<string, string | undefined> = {}) => {
    const qs2 = Object.entries(q).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
    return request<Record<string, RecordCategory>>(`/api/v1/workspaces/${w}/records${qs2 ? `?${qs2}` : ""}`);
  },
  recordsSeasonal: (w: string) =>
    request<{ season_id: string; label: string; leading_run_scorer: { player: string; value: number } | null;
              leading_wicket_taker: { player: string; value: number } | null }[]>(`/api/v1/workspaces/${w}/records/seasonal`),
  recordsUpcoming: (w: string, window = 10) =>
    request<{ person_id: string; metric: string; threshold: number; current: number; to_go: number }[]>(`/api/v1/workspaces/${w}/records/upcoming?window=${window}`),
  recordsHonours: (w: string) => request<Record<string, unknown>[]>(`/api/v1/workspaces/${w}/records/honours`),
  recordsBadges: (w: string, personId: string) =>
    request<{ calculated: { label: string; source: string; state: string }[];
              awarded: { label: string; source: string }[] }>(`/api/v1/workspaces/${w}/records/badges/${personId}`),
  recordBookPdfUrl: async (w: string): Promise<string> => {
    const headers: Record<string, string> = {};
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
    const resp = await fetch(`${getApiBase()}/api/v1/workspaces/${w}/records/book/pdf`, { headers });
    if (!resp.ok) throw new ApiError(`Record book export failed (${resp.status})`, resp.status);
    return URL.createObjectURL(await resp.blob());
  },

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
  // multi-fielder run-outs (R-3): additional involved fielders beyond the primary
  getRunOutFielders: (w: string, iid: string, id: string) =>
    request<DismissalFielder[]>(`/api/v1/workspaces/${w}/innings/${iid}/batting/${id}/run-out-fielders`),
  setRunOutFielders: (w: string, iid: string, id: string, fielders: { person_id: string; role?: string }[]) =>
    request<DismissalFielder[]>(`/api/v1/workspaces/${w}/innings/${iid}/batting/${id}/run-out-fielders`,
      { method: "PUT", body: { fielders } }),

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
