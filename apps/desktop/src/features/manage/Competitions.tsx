import { Plus, Trophy } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { EmptyState, ErrorState, LoadingState } from "../../components/states/States";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Modal } from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import {
  ApiError,
  api,
  type Competition,
  type CompetitionDetail,
  type Organisation,
  type Team,
} from "../../lib/api";
import { Detail, Field, NoWorkspace, Unknown, humanise, useManage } from "./_shared";

export function Competitions() {
  const { workspaceId, canManage } = useManage();
  const [items, setItems] = useState<Competition[]>([]);
  const [orgs, setOrgs] = useState<Organisation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    try {
      const [c, o] = await Promise.all([api.listCompetitions(workspaceId), api.listOrganisations(workspaceId)]);
      setItems(c);
      setOrgs(o);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load competitions");
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!workspaceId) {
    return (
      <AppShell title="Competitions" subtitle="Competitions, divisions, grades and seasons">
        <NoWorkspace />
      </AppShell>
    );
  }

  const orgName = (id: string | null) => (id ? orgs.find((o) => o.id === id)?.name ?? "—" : null);
  const filtered = items.filter((c) => c.name.toLowerCase().includes(search.toLowerCase()));

  return (
    <AppShell title="Competitions" subtitle="Competitions, divisions, grades and seasons">
      {msg && (
        <div className="mb-4 rounded-[var(--radius-app)] border border-success/40 bg-success/5 px-4 py-2 text-sm text-success">
          {msg}
        </div>
      )}
      <ClassificationsPanel workspaceId={workspaceId} canManage={canManage} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input placeholder="Search competitions..." value={search} onChange={(e) => setSearch(e.target.value)} className="max-w-xs" />
        <div className="flex-1" />
        {canManage && (
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4" aria-hidden /> New competition
          </Button>
        )}
      </div>
      {loading && <LoadingState label="Loading competitions..." />}
      {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}
      {!loading && !error && filtered.length === 0 && (
        <EmptyState icon={<Trophy className="h-8 w-8" aria-hidden />} title="No competitions" description="Create a competition to begin." />
      )}
      {!loading && !error && filtered.length > 0 && (
        <div className="grid gap-3">
          {filtered.map((c) => (
            <Card key={c.id} className="cursor-pointer hover:border-brand">
              <CardContent className="flex items-center gap-3 py-4" onClick={() => setDetail(c.id)}>
                <Trophy className="h-5 w-5 text-muted-foreground" aria-hidden />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{c.name}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    {c.association_id ? `${orgName(c.association_id)}` : "Independent (no association)"}
                  </div>
                </div>
                <Badge variant={c.status === "active" ? "success" : "muted"}>{c.status}</Badge>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {showCreate && (
        <CreateCompetitionModal
          workspaceId={workspaceId}
          associations={orgs.filter((o) => o.kind === "association")}
          onClose={() => setShowCreate(false)}
          onCreated={(name) => {
            setShowCreate(false);
            setMsg(`Created competition "${name}".`);
            void load();
          }}
        />
      )}
      {detail && (
        <CompetitionDetailModal
          workspaceId={workspaceId}
          competitionId={detail}
          canManage={canManage}
          orgName={orgName}
          onClose={() => setDetail(null)}
          onChanged={(m) => setMsg(m)}
        />
      )}
    </AppShell>
  );
}

function ClassificationsPanel({ workspaceId, canManage }: { workspaceId: string; canManage: boolean }) {
  const [rows, setRows] = useState<{ id: string; key: string | null; label: string | null; is_final: boolean | null; status: string; unresolved_source_value: string | null }[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setRows(await api.listClassifications(workspaceId));
    } catch {
      setRows([]);
    }
  }, [workspaceId]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const seed = async () => {
    setBusy(true);
    try {
      await api.seedDefaultClassifications(workspaceId);
      await load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="mb-4">
      <CardContent className="py-3">
        <button className="flex w-full items-center justify-between text-sm" onClick={() => setOpen((v) => !v)}>
          <span className="font-medium">Match classifications (finals structure)</span>
          <span className="text-muted-foreground">{open ? "Hide" : "Show"}</span>
        </button>
        {open && (
          <div className="mt-3 flex flex-col gap-3">
            <p className="text-xs text-muted-foreground">
              Documented finals/home-and-away types. Undocumented source codes are preserved as
              <b> unresolved</b> for later verification — never guessed.
            </p>
            {canManage && (
              <div>
                <Button size="sm" variant="outline" onClick={() => void seed()} disabled={busy}>
                  Seed default classifications
                </Button>
              </div>
            )}
            {rows.length === 0 ? (
              <p className="text-sm text-muted-foreground">None configured yet.</p>
            ) : (
              <ul className="flex flex-wrap gap-2">
                {rows.map((r) => (
                  <li key={r.id}>
                    {r.status === "unresolved" ? (
                      <Badge variant="warning">unresolved: {r.unresolved_source_value}</Badge>
                    ) : (
                      <Badge variant={r.is_final ? "brand" : "muted"}>{r.label}</Badge>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function CreateCompetitionModal({
  workspaceId,
  associations,
  onClose,
  onCreated,
}: {
  workspaceId: string;
  associations: Organisation[];
  onClose: () => void;
  onCreated: (name: string) => void;
}) {
  const [name, setName] = useState("");
  const [assoc, setAssoc] = useState("");
  const [seasonModel, setSeasonModel] = useState("unknown");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.createCompetition(workspaceId, { name, association_id: assoc || null, season_model: seasonModel });
      onCreated(name.trim());
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Failed to create competition");
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      title="New competition"
      onClose={onClose}
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button size="sm" onClick={() => void submit()} disabled={busy || !name.trim()}>
            {busy ? "Creating..." : "Create"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        {err && <ErrorState message={err} />}
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </Field>
        <Field label="Owning association" hint="Optional — leave as independent if no association owns it.">
          <Select value={assoc} onChange={(e) => setAssoc(e.target.value)}>
            <option value="">Independent (no association)</option>
            {associations.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Season rule" hint="How a match's season is determined from its date. Unknown leaves it for manual entry.">
          <Select value={seasonModel} onChange={(e) => setSeasonModel(e.target.value)}>
            {SEASON_MODELS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </Select>
        </Field>
      </div>
    </Modal>
  );
}

export const SEASON_MODELS = [
  { value: "unknown", label: "Unknown — set the season manually" },
  { value: "au_summer", label: "Australian summer (e.g. 2019/20)" },
  { value: "calendar", label: "Calendar year (e.g. 2020)" },
  { value: "uk_summer", label: "UK / Northern summer (e.g. 2021)" },
  { value: "custom", label: "Custom — use the competition's season dates" },
];

function CompetitionDetailModal({
  workspaceId,
  competitionId,
  canManage,
  orgName,
  onClose,
  onChanged,
}: {
  workspaceId: string;
  competitionId: string;
  canManage: boolean;
  orgName: (id: string | null) => string | null;
  onClose: () => void;
  onChanged: (msg: string) => void;
}) {
  const [comp, setComp] = useState<CompetitionDetail | null>(null);
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [newGrade, setNewGrade] = useState("");
  const [newSeason, setNewSeason] = useState("");
  const [entry, setEntry] = useState({ team_id: "", grade_id: "", season_id: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [c, t] = await Promise.all([api.getCompetition(workspaceId, competitionId), api.listTeams(workspaceId)]);
      setComp(c);
      setTeams(t);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Failed to load competition");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, competitionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const addGrade = async () => {
    if (!newGrade.trim()) return;
    setBusy(true);
    try {
      await api.createGrade(workspaceId, competitionId, { name: newGrade.trim() });
      setNewGrade("");
      onChanged("Grade added.");
      await load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Failed to add grade");
    } finally {
      setBusy(false);
    }
  };

  const addSeason = async () => {
    if (!newSeason.trim()) return;
    setBusy(true);
    try {
      await api.createSeason(workspaceId, competitionId, { label: newSeason.trim() });
      setNewSeason("");
      onChanged("Season added.");
      await load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Failed to add season");
    } finally {
      setBusy(false);
    }
  };

  const assign = async () => {
    if (!entry.team_id || !entry.grade_id || !entry.season_id) return;
    setBusy(true);
    try {
      await api.enterTeam(workspaceId, entry);
      setEntry({ team_id: "", grade_id: "", season_id: "" });
      onChanged("Team assigned to grade for the season.");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Failed to assign team");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open title={comp?.name ?? "Competition"} onClose={onClose}>
      {loading && <LoadingState />}
      {!loading && err && <ErrorState message={err} onRetry={() => void load()} />}
      {!loading && comp && (
        <div className="flex flex-col gap-5">
          <section>
            <Detail label="Association">
              <Unknown value={orgName(comp.association_id) ?? (comp.association_id ? "—" : "Independent")} />
            </Detail>
            <Detail label="Status">{comp.status}</Detail>
            <Detail label="Season rule">
              {canManage ? (
                <Select value={comp.season_model ?? "unknown"} disabled={busy}
                  onChange={async (e) => {
                    setBusy(true);
                    try {
                      const res = await api.updateCompetition(workspaceId, competitionId, { season_model: e.target.value });
                      await load();
                      const n = res?.seasons_reassigned?.assigned ?? 0;
                      onChanged(n > 0
                        ? `Season rule updated — ${n} existing match${n === 1 ? "" : "es"} re-assigned a season (manual choices kept).`
                        : "Season rule updated. Matches with a date are assigned automatically; manual choices are kept.");
                    } finally { setBusy(false); }
                  }}>
                  {SEASON_MODELS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                </Select>
              ) : (
                <Unknown value={SEASON_MODELS.find((m) => m.value === (comp.season_model ?? "unknown"))?.label ?? comp.season_model} />
              )}
            </Detail>
          </section>

          {comp.name_history.length > 1 && (
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Historical names</h3>
              <ul className="space-y-1 text-sm">
                {comp.name_history.map((n) => (
                  <li key={n.id}>{n.name}</li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Grades</h3>
            {comp.grades.length === 0 ? (
              <p className="text-sm text-muted-foreground">No grades yet.</p>
            ) : (
              <ul className="flex flex-wrap gap-2">
                {comp.grades.map((g) => (
                  <li key={g.id}>
                    <Badge variant="outline">
                      {g.name}
                      {g.program ? ` · ${humanise(g.program)}` : ""}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
            {canManage && (
              <div className="mt-2 flex gap-2">
                <Input placeholder="New grade name" value={newGrade} onChange={(e) => setNewGrade(e.target.value)} className="max-w-xs" />
                <Button size="sm" variant="outline" onClick={() => void addGrade()} disabled={busy || !newGrade.trim()}>
                  Add grade
                </Button>
              </div>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Seasons</h3>
            {comp.seasons.length === 0 ? (
              <p className="text-sm text-muted-foreground">No seasons yet.</p>
            ) : (
              <ul className="flex flex-wrap gap-2">
                {comp.seasons.map((s) => (
                  <li key={s.id}>
                    <Badge variant="muted">{s.label}</Badge>
                  </li>
                ))}
              </ul>
            )}
            {canManage && (
              <div className="mt-2 flex gap-2">
                <Input placeholder='New season e.g. "2026/27"' value={newSeason} onChange={(e) => setNewSeason(e.target.value)} className="max-w-xs" />
                <Button size="sm" variant="outline" onClick={() => void addSeason()} disabled={busy || !newSeason.trim()}>
                  Add season
                </Button>
              </div>
            )}
          </section>

          {canManage && comp.grades.length > 0 && comp.seasons.length > 0 && (
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Assign team to grade</h3>
              <div className="grid gap-2 sm:grid-cols-3">
                <Select value={entry.team_id} onChange={(e) => setEntry((v) => ({ ...v, team_id: e.target.value }))}>
                  <option value="">Team…</option>
                  {teams.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </Select>
                <Select value={entry.grade_id} onChange={(e) => setEntry((v) => ({ ...v, grade_id: e.target.value }))}>
                  <option value="">Grade…</option>
                  {comp.grades.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </Select>
                <Select value={entry.season_id} onChange={(e) => setEntry((v) => ({ ...v, season_id: e.target.value }))}>
                  <option value="">Season…</option>
                  {comp.seasons.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="mt-2">
                <Button size="sm" onClick={() => void assign()} disabled={busy || !entry.team_id || !entry.grade_id || !entry.season_id}>
                  Assign
                </Button>
              </div>
            </section>
          )}
        </div>
      )}
    </Modal>
  );
}
