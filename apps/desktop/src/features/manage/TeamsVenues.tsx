import { GitMerge, MapPin, Plus, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { EmptyState, ErrorState, LoadingState } from "../../components/states/States";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { ConfirmDialog, Modal } from "../../components/ui/dialog";
import { Input, Textarea } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import {
  ApiError,
  api,
  type DuplicateCandidate,
  type Organisation,
  type Team,
  type Venue,
} from "../../lib/api";
import { Detail, Field, NoWorkspace, Unknown, humanise, useManage } from "./_shared";

const PROGRAMS = ["seniors", "juniors", "womens", "girls", "all_abilities", "veterans", "custom"];

export function TeamsVenues() {
  const { workspaceId, canManage } = useManage();
  const [tab, setTab] = useState<"teams" | "venues">("teams");
  const [msg, setMsg] = useState<string | null>(null);

  if (!workspaceId) {
    return (
      <AppShell title="Teams & Venues" subtitle="Teams, cricket programs and grounds">
        <NoWorkspace />
      </AppShell>
    );
  }

  return (
    <AppShell title="Teams & Venues" subtitle="Teams, cricket programs and grounds">
      {msg && (
        <div className="mb-4 rounded-[var(--radius-app)] border border-success/40 bg-success/5 px-4 py-2 text-sm text-success">
          {msg}
        </div>
      )}
      <div className="mb-4 inline-flex gap-1 rounded-[var(--radius-app)] border border-border p-1">
        <button
          className={tab === "teams" ? "rounded-[var(--radius-app)] bg-muted px-3 py-1 text-sm" : "px-3 py-1 text-sm text-muted-foreground"}
          onClick={() => setTab("teams")}
        >
          Teams
        </button>
        <button
          className={tab === "venues" ? "rounded-[var(--radius-app)] bg-muted px-3 py-1 text-sm" : "px-3 py-1 text-sm text-muted-foreground"}
          onClick={() => setTab("venues")}
        >
          Venues
        </button>
      </div>
      {tab === "teams" ? (
        <TeamsTab workspaceId={workspaceId} canManage={canManage} onMsg={setMsg} />
      ) : (
        <VenuesTab workspaceId={workspaceId} canManage={canManage} onMsg={setMsg} />
      )}
    </AppShell>
  );
}

// ------------------------------------------------------------------ teams

function TeamsTab({ workspaceId, canManage, onMsg }: { workspaceId: string; canManage: boolean; onMsg: (m: string) => void }) {
  const [teams, setTeams] = useState<Team[]>([]);
  const [orgs, setOrgs] = useState<Organisation[]>([]);
  const [program, setProgram] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState<string | null>(null);

  const orgName = useCallback((id: string) => orgs.find((o) => o.id === id)?.name ?? "—", [orgs]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [t, o] = await Promise.all([
        api.listTeams(workspaceId, program ? { program } : {}),
        api.listOrganisations(workspaceId),
      ]);
      setTeams(t);
      setOrgs(o);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load teams");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, program]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select value={program} onChange={(e) => setProgram(e.target.value)} className="max-w-[12rem]">
          <option value="">All programs</option>
          {PROGRAMS.map((p) => (
            <option key={p} value={p}>
              {humanise(p)}
            </option>
          ))}
        </Select>
        <div className="flex-1" />
        {canManage && (
          <Button onClick={() => setShowCreate(true)} disabled={orgs.length === 0}>
            <Plus className="h-4 w-4" aria-hidden /> New team
          </Button>
        )}
      </div>
      {loading && <LoadingState label="Loading teams..." />}
      {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}
      {!loading && !error && teams.length === 0 && (
        <EmptyState
          icon={<Users className="h-8 w-8" aria-hidden />}
          title="No teams"
          description={orgs.length === 0 ? "Create an organisation first, then add its teams." : "Add a team to get started."}
        />
      )}
      {!loading && !error && teams.length > 0 && (
        <div className="grid gap-3">
          {teams.map((t) => (
            <Card key={t.id} className="cursor-pointer hover:border-brand">
              <CardContent className="flex items-center gap-3 py-4" onClick={() => setDetail(t.id)}>
                <Users className="h-5 w-5 text-muted-foreground" aria-hidden />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{t.name}</div>
                  <div className="truncate text-xs text-muted-foreground">{orgName(t.organisation_id)}</div>
                </div>
                <div className="flex shrink-0 gap-1">
                  <Badge variant="brand">{humanise(t.program)}</Badge>
                  {t.is_historical && <Badge variant="outline">historical</Badge>}
                  {t.merged_into_id && <Badge variant="warning">merged</Badge>}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {showCreate && (
        <CreateTeamModal
          workspaceId={workspaceId}
          orgs={orgs}
          onClose={() => setShowCreate(false)}
          onCreated={(name) => {
            setShowCreate(false);
            onMsg(`Created team "${name}".`);
            void load();
          }}
        />
      )}
      {detail && (
        <EntityDetailModal
          kind="team"
          workspaceId={workspaceId}
          entityId={detail}
          canManage={canManage}
          extraOrgName={orgName}
          onClose={() => setDetail(null)}
          onChanged={(m) => {
            onMsg(m);
            void load();
          }}
        />
      )}
    </>
  );
}

function CreateTeamModal({
  workspaceId,
  orgs,
  onClose,
  onCreated,
}: {
  workspaceId: string;
  orgs: Organisation[];
  onClose: () => void;
  onCreated: (name: string) => void;
}) {
  const [name, setName] = useState("");
  const [orgId, setOrgId] = useState(orgs[0]?.id ?? "");
  const [program, setProgram] = useState("seniors");
  const [isHistorical, setIsHistorical] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.createTeam(workspaceId, {
        organisation_id: orgId,
        name,
        program,
        is_historical: isHistorical,
      });
      onCreated(name.trim());
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Failed to create team");
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      title="New team"
      onClose={onClose}
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button size="sm" onClick={() => void submit()} disabled={busy || !name.trim() || !orgId}>
            {busy ? "Creating..." : "Create"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        {err && <ErrorState message={err} />}
        <Field label="Organisation">
          <Select value={orgId} onChange={(e) => setOrgId(e.target.value)}>
            {orgs.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Team name">
          <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </Field>
        <Field label="Program" hint="Cricket program classification.">
          <Select value={program} onChange={(e) => setProgram(e.target.value)}>
            {PROGRAMS.map((p) => (
              <option key={p} value={p}>
                {humanise(p)}
              </option>
            ))}
          </Select>
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={isHistorical} onChange={(e) => setIsHistorical(e.target.checked)} />
          Historical team
        </label>
      </div>
    </Modal>
  );
}

// ------------------------------------------------------------------ venues

function VenuesTab({ workspaceId, canManage, onMsg }: { workspaceId: string; canManage: boolean; onMsg: (m: string) => void }) {
  const [venues, setVenues] = useState<Venue[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setVenues(await api.listVenues(workspaceId, search ? { search } : {}));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load venues");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, search]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input placeholder="Search grounds..." value={search} onChange={(e) => setSearch(e.target.value)} className="max-w-xs" />
        <div className="flex-1" />
        {canManage && (
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4" aria-hidden /> New venue
          </Button>
        )}
      </div>
      {loading && <LoadingState label="Loading venues..." />}
      {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}
      {!loading && !error && venues.length === 0 && (
        <EmptyState icon={<MapPin className="h-8 w-8" aria-hidden />} title="No venues" description="Add a ground to get started." />
      )}
      {!loading && !error && venues.length > 0 && (
        <div className="grid gap-3">
          {venues.map((v) => (
            <Card key={v.id} className="cursor-pointer hover:border-brand">
              <CardContent className="flex items-center gap-3 py-4" onClick={() => setDetail(v.id)}>
                <MapPin className="h-5 w-5 text-muted-foreground" aria-hidden />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{v.name}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    {[v.locality, v.region].filter(Boolean).join(", ") || <span className="italic">location unknown</span>}
                  </div>
                </div>
                {v.merged_into_id && <Badge variant="warning">merged</Badge>}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {showCreate && (
        <CreateVenueModal
          workspaceId={workspaceId}
          onClose={() => setShowCreate(false)}
          onCreated={(name) => {
            setShowCreate(false);
            onMsg(`Created venue "${name}".`);
            void load();
          }}
        />
      )}
      {detail && (
        <EntityDetailModal
          kind="venue"
          workspaceId={workspaceId}
          entityId={detail}
          canManage={canManage}
          onClose={() => setDetail(null)}
          onChanged={(m) => {
            onMsg(m);
            void load();
          }}
        />
      )}
    </>
  );
}

function CreateVenueModal({
  workspaceId,
  onClose,
  onCreated,
}: {
  workspaceId: string;
  onClose: () => void;
  onCreated: (name: string) => void;
}) {
  const [name, setName] = useState("");
  const [locality, setLocality] = useState("");
  const [region, setRegion] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.createVenue(workspaceId, {
        name,
        locality: locality || null,
        region: region || null,
        notes: notes || null,
      });
      onCreated(name.trim());
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Failed to create venue");
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      title="New venue"
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
        <Field label="Locality" hint="Leave blank if unknown — never guess.">
          <Input value={locality} onChange={(e) => setLocality(e.target.value)} />
        </Field>
        <Field label="Region">
          <Input value={region} onChange={(e) => setRegion(e.target.value)} />
        </Field>
        <Field label="Notes">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
      </div>
    </Modal>
  );
}

// ------------------------------------------------- shared team/venue detail

function EntityDetailModal({
  kind,
  workspaceId,
  entityId,
  canManage,
  extraOrgName,
  onClose,
  onChanged,
}: {
  kind: "team" | "venue";
  workspaceId: string;
  entityId: string;
  canManage: boolean;
  extraOrgName?: (id: string) => string;
  onClose: () => void;
  onChanged: (msg: string) => void;
}) {
  const [data, setData] = useState<(Team | Venue) & { name_history: { id: string; name: string; valid_from: string | null; valid_to: string | null }[]; source_identities: { id: string; source_system: string; source_ref: string; source_display_name: string | null }[] } | null>(null);
  const [candidates, setCandidates] = useState<DuplicateCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<{ candidateId: string; candidateName: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [rename, setRename] = useState<string>("");

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const d = kind === "team" ? await api.getTeam(workspaceId, entityId) : await api.getVenue(workspaceId, entityId);
      setData(d);
      try {
        setCandidates(
          kind === "team"
            ? await api.teamDuplicateCandidates(workspaceId, entityId)
            : await api.venueDuplicateCandidates(workspaceId, entityId),
        );
      } catch {
        setCandidates([]);
      }
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [kind, workspaceId, entityId]);

  useEffect(() => {
    void load();
  }, [load]);

  const merge = async () => {
    if (!confirm) return;
    setBusy(true);
    try {
      if (kind === "team") {
        await api.teamMerge(workspaceId, { canonical_team_id: entityId, merged_team_id: confirm.candidateId, reason: "desktop" });
      } else {
        await api.venueMerge(workspaceId, { canonical_venue_id: entityId, merged_venue_id: confirm.candidateId, reason: "desktop" });
      }
      onChanged(`Merged "${confirm.candidateName}".`);
      setConfirm(null);
      await load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Merge failed");
    } finally {
      setBusy(false);
    }
  };

  const saveRename = async () => {
    const next = rename.trim();
    if (!next || !data || next === data.name) return;
    setBusy(true); setErr(null);
    try {
      if (kind === "team") await api.updateTeam(workspaceId, entityId, { name: next, name_change_note: "renamed" });
      else await api.updateVenue(workspaceId, entityId, { name: next });
      onChanged(`Renamed to "${next}". The previous name is kept as an alias; scorecards update automatically.`);
      setRename(""); await load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Rename failed");
    } finally { setBusy(false); }
  };

  const idKey = kind === "team" ? "team_id" : "venue_id";

  return (
    <Modal open title={data?.name ?? (kind === "team" ? "Team" : "Venue")} onClose={onClose}>
      {loading && <LoadingState />}
      {!loading && err && <ErrorState message={err} onRetry={() => void load()} />}
      {!loading && data && (
        <div className="flex flex-col gap-5">
          <section>
            {kind === "team" && extraOrgName && (
              <Detail label="Organisation">{extraOrgName((data as Team).organisation_id)}</Detail>
            )}
            {kind === "team" && <Detail label="Program">{humanise((data as Team).program)}</Detail>}
            {kind === "venue" && (
              <>
                <Detail label="Locality"><Unknown value={(data as Venue).locality} /></Detail>
                <Detail label="Region"><Unknown value={(data as Venue).region} /></Detail>
                <Detail label="Coordinates">
                  <Unknown value={(data as Venue).latitude !== null ? `${(data as Venue).latitude}, ${(data as Venue).longitude}` : null} />
                </Detail>
              </>
            )}
            <Detail label="Status">{data.status}</Detail>
            {canManage && (
              <div className="mt-2 flex flex-wrap items-end gap-2">
                <label className="flex flex-1 flex-col gap-1 text-sm">Rename display name
                  <Input value={rename} placeholder={data.name} onChange={(e) => setRename(e.target.value)} />
                </label>
                <Button size="sm" disabled={busy || !rename.trim() || rename.trim() === data.name} onClick={() => void saveRename()}>Rename</Button>
              </div>
            )}
            {canManage && <p className="mt-1 text-xs text-muted-foreground">The previous name is preserved as an alias and the original source name is never changed; scorecards update automatically.</p>}
          </section>

          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Historical names</h3>
            {data.name_history.length === 0 ? (
              <p className="text-sm text-muted-foreground">No recorded names.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {data.name_history.map((n) => (
                  <li key={n.id} className="flex justify-between gap-3">
                    <span>{n.name}</span>
                    <span className="text-muted-foreground">
                      <Unknown value={n.valid_from} /> {" – "} {n.valid_to ?? "present"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Source references</h3>
            {data.source_identities.length === 0 ? (
              <p className="text-sm text-muted-foreground">No external source references.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {data.source_identities.map((s) => (
                  <li key={s.id} className="flex items-center justify-between gap-3">
                    <span className="text-muted-foreground">{s.source_system}{s.source_display_name ? <> · <span className="text-foreground">original name: “{s.source_display_name}”</span></> : null}</span>
                    <span className="tabular-nums text-muted-foreground">{s.source_ref}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Possible duplicates</h3>
            {candidates.length === 0 ? (
              <p className="text-sm text-muted-foreground">No duplicate suggestions.</p>
            ) : (
              <ul className="space-y-2">
                {candidates.map((c) => {
                  const cid = (c as unknown as Record<string, string>)[idKey];
                  return (
                    <li key={cid} className="flex items-center justify-between gap-2 rounded-[var(--radius-app)] border border-border p-2 text-sm">
                      <div className="min-w-0">
                        <div className="truncate">{c.name}</div>
                        <Badge variant={c.confidence === "strong" ? "warning" : "muted"}>{c.confidence}</Badge>
                      </div>
                      {canManage && (
                        <Button size="sm" variant="outline" onClick={() => setConfirm({ candidateId: cid, candidateName: c.name })}>
                          <GitMerge className="h-4 w-4" aria-hidden /> Merge
                        </Button>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      )}

      {confirm && (
        <ConfirmDialog
          open
          danger
          busy={busy}
          title="Confirm merge"
          confirmLabel="Merge"
          description={
            <>
              Merge <b>{confirm.candidateName}</b> into <b>{data?.name}</b>? Reversible — the merged
              record is preserved, not deleted.
            </>
          }
          onConfirm={() => void merge()}
          onCancel={() => setConfirm(null)}
        />
      )}
    </Modal>
  );
}
