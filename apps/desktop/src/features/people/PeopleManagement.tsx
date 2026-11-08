import { GitMerge, Plus, Undo2, Upload, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { compressImage } from "../../lib/utils";
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
  type DuplicatePair,
  type ImportBatch,
  type ImportRecord,
  type Person,
  type PersonDuplicateCandidate,
  type PersonMerge,
} from "../../lib/api";
import { Detail, Field, NoWorkspace, Unknown, humanise, useManage } from "../manage/_shared";

const ROLES = ["player", "umpire", "scorer", "coach", "administrator", "selector", "captain", "official", "other"];

export function PeopleManagement() {
  const { workspaceId, canManage } = useManage();
  const [tab, setTab] = useState<"directory" | "identity" | "import">("directory");
  const [msg, setMsg] = useState<string | null>(null);

  if (!workspaceId) {
    return (
      <AppShell title="People" subtitle="Players, officials and identity management">
        <NoWorkspace />
      </AppShell>
    );
  }

  const tabBtn = (key: typeof tab, label: string) => (
    <button
      className={tab === key ? "rounded-[var(--radius-app)] bg-muted px-3 py-1 text-sm" : "px-3 py-1 text-sm text-muted-foreground"}
      onClick={() => setTab(key)}
    >
      {label}
    </button>
  );

  return (
    <AppShell title="People" subtitle="Players, officials and identity management">
      {msg && (
        <div className="mb-4 rounded-[var(--radius-app)] border border-success/40 bg-success/5 px-4 py-2 text-sm text-success">
          {msg}
        </div>
      )}
      <div className="mb-4 inline-flex gap-1 rounded-[var(--radius-app)] border border-border p-1">
        {tabBtn("directory", "Directory")}
        {tabBtn("identity", "Identity Resolution")}
        {tabBtn("import", "Cricket Statz Import")}
      </div>
      {tab === "directory" && <Directory workspaceId={workspaceId} canManage={canManage} onMsg={setMsg} />}
      {tab === "identity" && <IdentityCentre workspaceId={workspaceId} canManage={canManage} onMsg={setMsg} />}
      {tab === "import" && <ImportReview workspaceId={workspaceId} canManage={canManage} onMsg={setMsg} />}
    </AppShell>
  );
}

// ------------------------------------------------------------------ directory

function Directory({ workspaceId, canManage, onMsg }: { workspaceId: string; canManage: boolean; onMsg: (m: string) => void }) {
  const [people, setPeople] = useState<Person[]>([]);
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const PAGE = 25;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const opts: { role?: string } = {};
      if (role) opts.role = role;
      setPeople(await api.listPeople(workspaceId, opts));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load people");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, role]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = people.filter((p) => p.display_name.toLowerCase().includes(search.toLowerCase()));
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE));
  const shown = filtered.slice(page * PAGE, page * PAGE + PAGE);

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input placeholder="Search name / alias / initials..." value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(0); }} className="max-w-xs" />
        <Select value={role} onChange={(e) => setRole(e.target.value)} className="max-w-[12rem]">
          <option value="">All roles</option>
          {ROLES.map((r) => <option key={r} value={r}>{humanise(r)}</option>)}
        </Select>
        <div className="flex-1" />
        {canManage && <Button onClick={() => setShowCreate(true)}><Plus className="h-4 w-4" aria-hidden /> New person</Button>}
      </div>

      {loading && <LoadingState label="Loading people..." />}
      {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}
      {!loading && !error && filtered.length === 0 && (
        <EmptyState icon={<Users className="h-8 w-8" aria-hidden />} title="No people"
          description={canManage ? "Add a person or import from Cricket Statz." : "Nothing to show yet."} />
      )}
      {!loading && !error && shown.length > 0 && (
        <>
          <div className="grid gap-2">
            {shown.map((p) => (
              <Card key={p.id} className="hover:border-brand">
                <CardContent className="flex items-center gap-3 py-3">
                  <button type="button" className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 text-left"
                    onClick={() => { window.location.hash = `#/people/${p.id}`; }}
                    aria-label={`Open ${p.display_name}'s career profile`}>
                    <Users className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{p.display_name}</div>
                      <div className="truncate text-xs text-muted-foreground">{p.status}</div>
                    </div>
                  </button>
                  {p.is_junior && <Badge variant="warning">junior</Badge>}
                  {p.merged_into_id && <Badge variant="muted">merged</Badge>}
                  <Button size="sm" variant="outline" onClick={() => setSelected(p.id)}>Details</Button>
                </CardContent>
              </Card>
            ))}
          </div>
          {pages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-3 text-sm">
              <Button size="sm" variant="outline" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Prev</Button>
              <span className="text-muted-foreground">Page {page + 1} of {pages}</span>
              <Button size="sm" variant="outline" disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          )}
        </>
      )}

      {selected && (
        <ProfileModal workspaceId={workspaceId} personId={selected} canManage={canManage}
          onClose={() => setSelected(null)} onChanged={(m) => { onMsg(m); void load(); }} />
      )}
      {showCreate && (
        <CreatePersonModal workspaceId={workspaceId} onClose={() => setShowCreate(false)}
          onCreated={(n) => { setShowCreate(false); onMsg(`Created "${n}".`); void load(); }} />
      )}
    </>
  );
}

function CreatePersonModal({ workspaceId, onClose, onCreated }: { workspaceId: string; onClose: () => void; onCreated: (n: string) => void }) {
  const [name, setName] = useState("");
  const [isJunior, setIsJunior] = useState(false);
  const [role, setRole] = useState("player");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      await api.createPerson(workspaceId, { display_name: name, is_junior: isJunior, roles: [role] });
      onCreated(name.trim());
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Failed to create"); setBusy(false); }
  };
  return (
    <Modal open title="New person" onClose={onClose} footer={
      <>
        <Button variant="outline" size="sm" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button size="sm" onClick={() => void submit()} disabled={busy || !name.trim()}>{busy ? "Creating..." : "Create"}</Button>
      </>
    }>
      <div className="flex flex-col gap-3">
        {err && <ErrorState message={err} />}
        <Field label="Display name"><Input value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
        <Field label="Primary role">
          <Select value={role} onChange={(e) => setRole(e.target.value)}>
            {ROLES.map((r) => <option key={r} value={r}>{humanise(r)}</option>)}
          </Select>
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={isJunior} onChange={(e) => setIsJunior(e.target.checked)} /> Junior (personal data protected)
        </label>
      </div>
    </Modal>
  );
}

function ProfileModal({ workspaceId, personId, canManage, onClose, onChanged }: {
  workspaceId: string; personId: string; canManage: boolean; onClose: () => void; onChanged: (m: string) => void;
}) {
  const [view, setView] = useState<Record<string, any> | null>(null);
  const [candidates, setCandidates] = useState<PersonDuplicateCandidate[]>([]);
  const [orgs, setOrgs] = useState<{ id: string; name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [bio, setBio] = useState("");
  const [batStyle, setBatStyle] = useState("");
  const [bowlStyle, setBowlStyle] = useState("");
  const [yearFor, setYearFor] = useState<{ kind: "number" | "leadership" | "recognition"; id: string; body: Record<string, unknown> } | null>(null);
  const [yearSeason, setYearSeason] = useState("");
  const [photoUrls, setPhotoUrls] = useState<Record<string, string>>({});
  const [confirm, setConfirm] = useState<{ candidateId: string; name: string; kind: "merge" | "distinct" } | null>(null);
  const [busy, setBusy] = useState(false);
  // core-detail editing (name / status / date of birth)
  const [editOpen, setEditOpen] = useState(false);
  const [edName, setEdName] = useState("");
  const [edStatus, setEdStatus] = useState("active");
  const [edDob, setEdDob] = useState("");
  const [edDobPrec, setEdDobPrec] = useState("unknown");
  // manual merge: search for any other record to merge into this one (beyond auto-suggestions)
  const [mergeSearch, setMergeSearch] = useState("");
  const [mergeResults, setMergeResults] = useState<Person[]>([]);
  const [searching, setSearching] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setErr(null);
    try {
      const v = await api.getProfile(workspaceId, personId);
      setView(v);
      const pp = v.person as any;
      setEdName((pp?.display_name as string) ?? "");
      setEdStatus((pp?.status as string) || "active");
      setEdDob((pp?.dob as string) ?? "");
      setEdDobPrec((pp?.dob_precision as string) || "unknown");
      setBio(((v.profile as any)?.biography as string) ?? "");
      setBatStyle(((v.profile as any)?.batting_style as string) ?? "");
      setBowlStyle(((v.profile as any)?.bowling_style as string) ?? "");
      try { setOrgs(await api.listOrganisations(workspaceId)); } catch { setOrgs([]); }
      try { setCandidates(await api.identityCandidates(workspaceId, personId)); } catch { setCandidates([]); }
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Failed to load profile"); }
    finally { setLoading(false); }
  }, [workspaceId, personId]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    (view?.photos ?? []).forEach((p: any) => {
      if (photoUrls[p.id]) return;
      api.personPhotoUrl(workspaceId, p.id).then((u) => setPhotoUrls((m) => ({ ...m, [p.id]: u }))).catch(() => {});
    });
  }, [view, workspaceId, photoUrls]);

  const uploadPhoto = async (file: File) => {
    setBusy(true);
    try {
      const compressed = await compressImage(file);
      await api.uploadPersonPhoto(workspaceId, personId, compressed, { isPrimary: (view?.photos ?? []).length === 0 });
      onChanged("Photo uploaded."); await load();
    } catch (e) {
      const m = e instanceof ApiError ? e.message : "";
      setErr(m === "file_too_large" ? "That image is too large (max 15 MB). Please choose a smaller photo."
        : m === "dimensions_too_large" ? "That image's resolution is too high. Please choose a smaller photo."
        : (/unsupported|invalid_image|type_mismatch/.test(m) ? "Please use a JPEG, PNG or WebP image." : (m || "Photo upload failed.")));
    }
    finally { setBusy(false); }
  };
  const removePhoto = async (photoId: string) => {
    try { await api.deletePersonPhoto(workspaceId, photoId); onChanged("Photo removed."); await load(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not remove photo."); }
  };

  const saveBio = async () => {
    setBusy(true);
    try {
      await api.upsertProfile(workspaceId, personId,
        { biography: bio, batting_style: batStyle || null, bowling_style: bowlStyle || null });
      onChanged("Profile saved."); await load();
    }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Save failed"); }
    finally { setBusy(false); }
  };

  const protectedDob = Boolean((view?.person as any)?.protected_fields_hidden);
  const saveDetails = async () => {
    if (!edName.trim()) { setErr("Name cannot be empty."); return; }
    setBusy(true); setErr(null);
    try {
      const body: Record<string, unknown> = { display_name: edName.trim(), status: edStatus };
      // only touch the date of birth when it isn't privacy-protected (never overwrite a hidden value)
      if (!protectedDob) { body.set_dob = true; body.dob = edDob || null; body.dob_precision = edDob ? edDobPrec : "unknown"; }
      await api.updatePerson(workspaceId, personId, body);
      setEditOpen(false); onChanged("Details saved."); await load();
    }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not save details."); }
    finally { setBusy(false); }
  };

  // live search for any other record to merge into this one (the auto-suggestions below are name-based only)
  useEffect(() => {
    const q = mergeSearch.trim();
    if (q.length < 2) { setMergeResults([]); return; }
    let active = true; setSearching(true);
    api.listPeople(workspaceId, { search: q })
      .then((ppl) => { if (active) setMergeResults(ppl.filter((p) => p.id !== personId && !p.merged_into_id).slice(0, 8)); })
      .catch(() => { if (active) setMergeResults([]); })
      .finally(() => { if (active) setSearching(false); });
    return () => { active = false; };
  }, [mergeSearch, workspaceId, personId]);

  const removeAttr = async (kind: "number" | "leadership" | "recognition", attrId: string) => {
    try {
      if (kind === "number") await api.deletePersonNumber(workspaceId, personId, attrId);
      else if (kind === "leadership") await api.deletePersonLeadership(workspaceId, personId, attrId);
      else await api.deletePersonRecognition(workspaceId, personId, attrId);
      onChanged("Removed."); await load();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not remove."); }
  };

  // "+yr": add another season to an existing role/recognition without retyping (creates a new entry with
  // the same role/number + club, just a new season). Entries group by label on the career profile.
  const addYear = async () => {
    if (!yearFor || !yearSeason.trim()) return;
    const body = { ...yearFor.body, season_label: yearSeason.trim() };
    try {
      if (yearFor.kind === "number") await api.addPersonNumber(workspaceId, personId, body);
      else if (yearFor.kind === "leadership") await api.addPersonLeadership(workspaceId, personId, body);
      else await api.addPersonRecognition(workspaceId, personId, body);
      setYearFor(null); setYearSeason(""); onChanged("Season added."); await load();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not add season."); }
  };

  const attrChips = (kind: "number" | "leadership" | "recognition", items: any[],
                     label: (x: any) => string, bodyOf: (x: any) => Record<string, unknown>) => (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap gap-1 text-sm">
        {(items ?? []).length === 0 ? <span className="text-muted-foreground">—</span> :
          (items ?? []).map((it: any) => (
            <span key={it.id} className="inline-flex items-center gap-1 rounded-[var(--radius-app)] border border-border px-1.5 py-0.5 text-xs">
              {label(it)}{it.season_label ? ` (${it.season_label})` : ""}
              {canManage && <>
                <button type="button" aria-label="Add another season" title="Add another season"
                  className="text-muted-foreground hover:text-brand"
                  onClick={() => { setYearFor({ kind, id: it.id, body: bodyOf(it) }); setYearSeason(""); }}>+yr</button>
                <button type="button" aria-label="Remove" className="text-muted-foreground hover:text-danger"
                  onClick={() => void removeAttr(kind, it.id)}>×</button>
              </>}
            </span>
          ))}
      </div>
      {canManage && yearFor && (items ?? []).some((it: any) => it.id === yearFor.id) && (
        <div className="flex flex-col gap-1">
          <Input value={yearSeason} placeholder="Add season (e.g. 2024/25)" className="h-8 w-full text-sm"
            autoFocus onChange={(e) => setYearSeason(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void addYear(); }} />
          <div className="flex gap-1">
            <Button size="sm" variant="outline" disabled={!yearSeason.trim()} onClick={() => void addYear()}>Add</Button>
            <Button size="sm" variant="ghost" onClick={() => setYearFor(null)}>Cancel</Button>
          </div>
        </div>
      )}
    </div>
  );

  const runConfirm = async () => {
    if (!confirm) return;
    setBusy(true);
    try {
      if (confirm.kind === "merge") {
        await api.identityMerge(workspaceId, { canonical_person_id: personId, merged_person_id: confirm.candidateId, reason: "confirmed (desktop)" });
        onChanged(`Merged "${confirm.name}" into this person.`);
      } else {
        await api.identityAssertDistinct(workspaceId, { person_a_id: personId, person_b_id: confirm.candidateId, reason: "distinct (desktop)" });
        onChanged(`Marked "${confirm.name}" as distinct.`);
      }
      setConfirm(null); setMergeSearch(""); setMergeResults([]); await load();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Action failed"); setBusy(false); }
  };

  const person = view?.person as Record<string, any> | undefined;

  return (
    <Modal open title={person?.display_name ?? "Person"} onClose={onClose}>
      {loading && <LoadingState />}
      {!loading && err && <ErrorState message={err} onRetry={() => void load()} />}
      {!loading && person && (
        <div className="flex flex-col gap-5">
          <a href={`#/people/${personId}`} onClick={(e) => { e.preventDefault(); window.location.hash = `#/people/${personId}`; onClose(); }}
            className="inline-flex w-fit items-center gap-1 rounded-[var(--radius-app)] border border-brand bg-brand/10 px-3 py-1.5 text-sm font-medium text-brand">
            View full career profile →
          </a>
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Photo</h3>
            <div className="flex flex-wrap items-center gap-3">
              {(view?.photos ?? []).map((p: any) => (
                <div key={p.id} className="relative">
                  {photoUrls[p.id]
                    ? <img src={photoUrls[p.id]} alt="" className="h-20 w-20 rounded-full object-cover" />
                    : <div className="h-20 w-20 rounded-full bg-muted" />}
                  {canManage && <button type="button" aria-label="Remove photo"
                    className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full border border-border bg-card text-xs text-muted-foreground hover:text-danger"
                    onClick={() => void removePhoto(p.id)}>×</button>}
                </div>
              ))}
              {canManage && (
                <label className="flex h-20 w-20 cursor-pointer flex-col items-center justify-center rounded-full border-2 border-dashed border-border text-center text-[11px] text-muted-foreground hover:border-brand hover:text-brand">
                  {busy ? "…" : "+ Add photo"}
                  <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" disabled={busy}
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) void uploadPhoto(f); e.target.value = ""; }} />
                </label>
              )}
            </div>
          </section>
          <section>
            <div className="mb-1 flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase text-muted-foreground">Details</h3>
              {canManage && (
                <Button size="sm" variant="ghost" onClick={() => { setEditOpen((o) => !o); setErr(null); }}>
                  {editOpen ? "Cancel" : "Edit details"}
                </Button>
              )}
            </div>
            {!editOpen ? (
              <>
                <Detail label="Name">{person.display_name}</Detail>
                <Detail label="Status">{person.status}</Detail>
                <Detail label="Roles">{(view?.person?.roles ?? []).map((r: string) => humanise(r)).join(", ") || "—"}</Detail>
                <Detail label="Date of birth"><Unknown value={person.dob} /></Detail>
                {person.is_junior && <Detail label="Junior"><Badge variant="warning">personal data protected</Badge></Detail>}
                {person.protected_fields_hidden && (
                  <p className="text-xs text-muted-foreground">Some personal fields are hidden by privacy protection.</p>
                )}
              </>
            ) : (
              <div className="flex flex-col gap-2 rounded-[var(--radius-app)] border border-border p-3">
                <label className="flex flex-col gap-1 text-xs">Name
                  <Input value={edName} onChange={(e) => setEdName(e.target.value)} placeholder="Display name" />
                </label>
                <label className="flex flex-col gap-1 text-xs">Status
                  <Select value={edStatus} onChange={(e) => setEdStatus(e.target.value)}>
                    <option value="active">active</option>
                    <option value="inactive">inactive</option>
                  </Select>
                </label>
                {protectedDob ? (
                  <p className="text-xs text-muted-foreground">Date of birth is privacy-protected and can't be edited here.</p>
                ) : (
                  <div className="grid gap-2 sm:grid-cols-2">
                    <label className="flex flex-col gap-1 text-xs">Date of birth
                      <Input type="date" value={edDob} onChange={(e) => setEdDob(e.target.value)} />
                    </label>
                    <label className="flex flex-col gap-1 text-xs">Precision
                      <Select value={edDobPrec} onChange={(e) => setEdDobPrec(e.target.value)} disabled={!edDob}>
                        {["exact", "year", "month", "approx", "unknown"].map((p) => <option key={p} value={p}>{p}</option>)}
                      </Select>
                    </label>
                  </div>
                )}
                <div className="mt-1 flex gap-2">
                  <Button size="sm" onClick={() => void saveDetails()} disabled={busy || !edName.trim()}>Save details</Button>
                  <Button size="sm" variant="ghost" onClick={() => { setEditOpen(false); setErr(null); void load(); }}>Cancel</Button>
                </div>
              </div>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Historical names</h3>
            <ul className="space-y-1 text-sm">
              {(view?.person?.names ?? []).map((n: any) => (
                <li key={n.id} className="flex justify-between gap-3">
                  <span>{n.name}</span><span className="text-muted-foreground">{humanise(n.name_type)}</span>
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Club & team affiliations</h3>
            {(view?.affiliations ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">No recorded affiliations.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {(view?.affiliations ?? []).map((a: any) => (
                  <li key={a.id} className="flex justify-between gap-3">
                    <span>
                      <span className="font-medium">{orgs.find((o) => o.id === a.organisation_id)?.name ?? "Unknown club"}</span>
                      {a.role ? <span className="text-muted-foreground"> · {humanise(a.role)}</span> : null}
                    </span>
                    <span className="text-muted-foreground"><Unknown value={a.valid_from} /> – {a.valid_to ?? "present"}</span>
                  </li>
                ))}
              </ul>
            )}
            {(view?.played_for_clubs ?? []).length > 0 && (
              <div className="mt-2">
                <p className="text-xs text-muted-foreground">
                  Played for (from match appearances, no recorded affiliation):
                </p>
                <ul className="mt-1 flex flex-wrap gap-1.5">
                  {(view?.played_for_clubs ?? []).map((c: any) => (
                    <li key={c.org_id} className="rounded-full border border-border bg-muted/40 px-2 py-0.5 text-xs">
                      {c.club}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          <section className="grid gap-3 sm:grid-cols-3">
            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase text-muted-foreground">Numbers</h3>
              {attrChips("number", view?.numbers ?? [], (n) => String(n.number ?? "?"),
                (n) => ({ organisation_id: n.organisation_id, number: n.number }))}
              {canManage && <AttrAdder kind="number" workspaceId={workspaceId} personId={personId} orgs={orgs}
                onDone={(m) => { onChanged(m); void load(); }} />}
            </div>
            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase text-muted-foreground">Leadership</h3>
              {attrChips("leadership", view?.leadership ?? [], (l) => humanise(l.role),
                (l) => ({ organisation_id: l.organisation_id, role: l.role }))}
              {canManage && <AttrAdder kind="leadership" workspaceId={workspaceId} personId={personId} orgs={orgs}
                onDone={(m) => { onChanged(m); void load(); }} />}
            </div>
            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase text-muted-foreground">Recognition</h3>
              {attrChips("recognition", view?.recognition ?? [], (r) => r.title || humanise(r.recognition_type),
                (r) => ({ recognition_type: r.recognition_type, title: r.title ?? undefined, organisation_id: r.organisation_id ?? undefined }))}
              {canManage && <AttrAdder kind="recognition" workspaceId={workspaceId} personId={personId} orgs={orgs}
                onDone={(m) => { onChanged(m); void load(); }} />}
            </div>
          </section>

          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Source identities</h3>
            <ul className="space-y-1 text-sm">
              {(view?.person?.source_identities ?? []).map((s: any) => (
                <li key={s.id} className="flex justify-between gap-3">
                  <span className="text-muted-foreground">{s.source_system}</span><span>{s.source_ref}</span>
                </li>
              ))}
            </ul>
          </section>

          {canManage && (
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Profile &amp; playing style</h3>
              <div className="mb-2 grid gap-2 sm:grid-cols-2">
                <label className="flex flex-col gap-1 text-xs">Batting
                  <Input value={batStyle} placeholder="e.g. Right Handed" onChange={(e) => setBatStyle(e.target.value)} />
                </label>
                <label className="flex flex-col gap-1 text-xs">Bowling
                  <Input value={bowlStyle} placeholder="e.g. Right Arm Pace" onChange={(e) => setBowlStyle(e.target.value)} />
                </label>
              </div>
              <label className="flex flex-col gap-1 text-xs">Biography
                <Textarea value={bio} onChange={(e) => setBio(e.target.value)} />
              </label>
              <div className="mt-2"><Button size="sm" onClick={() => void saveBio()} disabled={busy}>Save profile</Button></div>
            </section>
          )}

          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Duplicates &amp; merging</h3>
            {canManage && (
              <div className="mb-3 rounded-[var(--radius-app)] border border-border p-2">
                <p className="mb-1 text-xs text-muted-foreground">
                  Entered more than once? Search for the other record and merge it into this one. Reversible.
                </p>
                <Input value={mergeSearch} onChange={(e) => setMergeSearch(e.target.value)}
                  placeholder="Search a player to merge (name)…" className="h-8 text-sm" />
                {mergeSearch.trim().length >= 2 && (
                  <div className="mt-2">
                    {searching && <p className="text-xs text-muted-foreground">Searching…</p>}
                    {!searching && mergeResults.length === 0 && <p className="text-xs text-muted-foreground">No other records match.</p>}
                    <ul className="space-y-1">
                      {mergeResults.map((p) => (
                        <li key={p.id} className="flex items-center justify-between gap-2 rounded-[var(--radius-app)] border border-border p-2 text-sm">
                          <span className="min-w-0 truncate">{p.display_name}</span>
                          <Button size="sm" variant="outline" className="shrink-0"
                            onClick={() => setConfirm({ candidateId: p.id, name: p.display_name, kind: "merge" })}>
                            <GitMerge className="h-4 w-4" aria-hidden /> Merge
                          </Button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
            <p className="mb-2 text-xs text-muted-foreground">Suggested matches — a name match is never proof. Merges are reversible.</p>
            {candidates.length === 0 ? (
              <p className="text-sm text-muted-foreground">No duplicate suggestions.</p>
            ) : (
              <ul className="space-y-2">
                {candidates.map((c) => (
                  <li key={c.person_id} className="flex items-center justify-between gap-2 rounded-[var(--radius-app)] border border-border p-2 text-sm">
                    <div className="min-w-0">
                      <div className="truncate">{c.display_name}</div>
                      <div className="flex flex-wrap gap-1">
                        <Badge variant={c.confidence === "strong" ? "warning" : c.confidence === "medium" ? "brand" : "muted"}>{c.confidence}</Badge>
                        {c.evidence.map((ev) => <Badge key={ev} variant="outline">{humanise(ev)}</Badge>)}
                      </div>
                    </div>
                    {canManage && (
                      <div className="flex shrink-0 gap-1">
                        <Button size="sm" variant="outline" onClick={() => setConfirm({ candidateId: c.person_id, name: c.display_name, kind: "merge" })}>
                          <GitMerge className="h-4 w-4" aria-hidden /> Merge
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setConfirm({ candidateId: c.person_id, name: c.display_name, kind: "distinct" })}>
                          Distinct
                        </Button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}

      {confirm && (
        <ConfirmDialog open danger={confirm.kind === "merge"} busy={busy}
          title={confirm.kind === "merge" ? "Confirm merge" : "Mark as distinct"}
          confirmLabel={confirm.kind === "merge" ? "Merge" : "Mark distinct"}
          description={confirm.kind === "merge"
            ? <>Merge <b>{confirm.name}</b> into <b>{person?.display_name}</b>? Reversible — the merged record is preserved.</>
            : <>Record that <b>{confirm.name}</b> and <b>{person?.display_name}</b> are definitely different people?</>}
          onConfirm={() => void runConfirm()} onCancel={() => setConfirm(null)} />
      )}
    </Modal>
  );
}

// ------------------------------------------------------------------ identity centre

function IdentityCentre({ workspaceId, canManage, onMsg }: { workspaceId: string; canManage: boolean; onMsg: (m: string) => void }) {
  const [merges, setMerges] = useState<PersonMerge[]>([]);
  const [pairs, setPairs] = useState<DuplicatePair[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmUndo, setConfirmUndo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pairBusy, setPairBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [m, dup, all] = await Promise.all([
        api.listPersonMerges(workspaceId),
        api.identityScan(workspaceId),
        api.listPeople(workspaceId, { include_merged: true }),
      ]);
      setMerges(m);
      setPairs(dup);
      // resolve display names for involved people (best-effort)
      setNames(Object.fromEntries(all.map((p) => [p.id, p.display_name])));
    } catch (e) { setError(e instanceof ApiError ? e.message : "Failed to load identity data"); }
    finally { setLoading(false); }
  }, [workspaceId]);
  useEffect(() => { void load(); }, [load]);

  const undo = async () => {
    if (!confirmUndo) return;
    setBusy(true);
    try { await api.identityUndoMerge(workspaceId, confirmUndo); onMsg("Merge reversed."); setConfirmUndo(null); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Undo failed"); }
    finally { setBusy(false); }
  };

  const pairKey = (p: DuplicatePair) => `${p.person_a_id}:${p.person_b_id}`;
  const resolvePair = async (p: DuplicatePair, action: "keepA" | "keepB" | "distinct") => {
    setPairBusy(pairKey(p));
    try {
      if (action === "distinct") {
        await api.identityAssertDistinct(workspaceId, { person_a_id: p.person_a_id, person_b_id: p.person_b_id, reason: "reviewed — different people (desktop)" });
        onMsg("Marked as different people.");
      } else {
        const canonical = action === "keepA" ? p.person_a_id : p.person_b_id;
        const merged = action === "keepA" ? p.person_b_id : p.person_a_id;
        await api.identityMerge(workspaceId, { canonical_person_id: canonical, merged_person_id: merged, reason: "confirmed duplicate (desktop)" });
        onMsg(`Merged into "${(action === "keepA" ? p.a_display_name : p.b_display_name) ?? "person"}".`);
      }
      await load();
    } catch (e) { setError(e instanceof ApiError ? e.message : "Could not resolve this pair"); }
    finally { setPairBusy(null); }
  };

  const confBadge = (c: DuplicatePair["confidence"]) =>
    c === "strong" ? <Badge variant="brand">strong</Badge>
      : c === "medium" ? <Badge variant="warning">medium</Badge>
        : <Badge variant="muted">weak</Badge>;

  const nm = (id: string) => names[id] ?? id.slice(0, 8);

  return (
    <>
      <p className="mb-4 text-sm text-muted-foreground">
        Resolve players who appear more than once — e.g. the same person recorded under two clubs. Review the
        suggested pairs below (strongest first), keep one record or mark them as different people. A name match
        is never proof and nothing is auto-merged; every merge is reversible.
      </p>
      {loading && <LoadingState label="Loading identity data..." />}
      {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}

      {!loading && !error && (
        <section className="mb-6">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Possible duplicates {pairs.length > 0 && <span className="text-foreground">({pairs.length})</span>}
          </h3>
          {pairs.length === 0 ? (
            <EmptyState icon={<Users className="h-8 w-8" aria-hidden />} title="No possible duplicates"
              description="Every player resolves to a single person. New suggestions appear here after an import." />
          ) : (
            <div className="grid gap-2">
              {pairs.map((p) => {
                const k = pairKey(p);
                const pending = pairBusy === k;
                return (
                  <Card key={k}>
                    <CardContent className="flex flex-wrap items-center gap-x-3 gap-y-2 py-3 text-sm">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          {confBadge(p.confidence)}
                          <span className="truncate"><b>{p.a_display_name ?? nm(p.person_a_id)}</b> &amp; <b>{p.b_display_name ?? nm(p.person_b_id)}</b></span>
                        </div>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {p.evidence.map((ev) => (
                            <span key={ev} className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">{humanise(ev)}</span>
                          ))}
                        </div>
                      </div>
                      {canManage && (
                        <div className="flex flex-wrap items-center gap-2">
                          <Button size="sm" variant="outline" disabled={pending} onClick={() => void resolvePair(p, "keepA")}>
                            <GitMerge className="h-4 w-4" aria-hidden /> Keep {p.a_display_name ?? "A"}
                          </Button>
                          <Button size="sm" variant="outline" disabled={pending} onClick={() => void resolvePair(p, "keepB")}>
                            <GitMerge className="h-4 w-4" aria-hidden /> Keep {p.b_display_name ?? "B"}
                          </Button>
                          <Button size="sm" variant="ghost" disabled={pending} onClick={() => void resolvePair(p, "distinct")}>
                            Not the same
                          </Button>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </section>
      )}

      {!loading && !error && (
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Merge history</h3>
      )}
      {!loading && !error && merges.length === 0 && (
        <EmptyState icon={<GitMerge className="h-8 w-8" aria-hidden />} title="No merges recorded"
          description="Confirmed merges and reversals appear here with full history." />
      )}
      {!loading && !error && merges.length > 0 && (
        <div className="grid gap-2">
          {merges.map((m) => (
            <Card key={m.id}>
              <CardContent className="flex items-center justify-between gap-3 py-3 text-sm">
                <div className="min-w-0">
                  <div className="truncate"><b>{nm(m.merged_person_id)}</b> → <b>{nm(m.canonical_person_id)}</b></div>
                  <div className="text-xs text-muted-foreground">{m.reason ?? ""}{m.is_undone ? " · reversed" : ""}</div>
                </div>
                {m.is_undone ? <Badge variant="muted">reversed</Badge> : canManage && (
                  <Button size="sm" variant="ghost" onClick={() => setConfirmUndo(m.id)}><Undo2 className="h-4 w-4" aria-hidden /> Reverse</Button>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      {confirmUndo && (
        <ConfirmDialog open busy={busy} title="Reverse merge" confirmLabel="Reverse"
          description="Reverse this merge? The merged person is reinstated as an independent record."
          onConfirm={() => void undo()} onCancel={() => setConfirmUndo(null)} />
      )}
    </>
  );
}

// ------------------------------------------------------------------ import review

function ImportReview({ workspaceId, canManage, onMsg }: { workspaceId: string; canManage: boolean; onMsg: (m: string) => void }) {
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [showStage, setShowStage] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setBatches((await api.listPeopleImports(workspaceId)).filter((b) => Boolean(b.counts?.player || b.counts?.official))); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Failed to load imports"); }
    finally { setLoading(false); }
  }, [workspaceId]);
  useEffect(() => { void load(); }, [load]);

  return (
    <>
      <div className="mb-4 flex items-center gap-2">
        <p className="text-sm text-muted-foreground">Stage → detect → review → promote. Original records are preserved; nothing is promoted without approval.</p>
        <div className="flex-1" />
        {canManage && <Button onClick={() => setShowStage(true)}><Upload className="h-4 w-4" aria-hidden /> New import</Button>}
      </div>
      {loading && <LoadingState label="Loading import batches..." />}
      {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}
      {!loading && !error && batches.length === 0 && (
        <EmptyState icon={<Upload className="h-8 w-8" aria-hidden />} title="No people imports"
          description="Stage a Cricket Statz players/officials export to begin." />
      )}
      {!loading && !error && batches.length > 0 && (
        <div className="grid gap-2">
          {batches.map((b) => (
            <Card key={b.id} className="cursor-pointer hover:border-brand">
              <CardContent className="flex items-center justify-between gap-3 py-3" onClick={() => setSelected(b.id)}>
                <div className="min-w-0">
                  <div className="truncate font-medium">{b.source_filename ?? b.source_system}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    players {b.counts?.player ?? 0} · officials {b.counts?.official ?? 0}
                  </div>
                </div>
                <Badge variant={b.status === "promoted" ? "success" : b.status === "partially_promoted" ? "warning" : "muted"}>{humanise(b.status)}</Badge>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      {selected && (
        <ImportBatchModal workspaceId={workspaceId} batchId={selected} canManage={canManage}
          onClose={() => setSelected(null)} onMsg={(m) => { onMsg(m); void load(); }} />
      )}
      {showStage && (
        <StageImportModal workspaceId={workspaceId} onClose={() => setShowStage(false)}
          onStaged={() => { setShowStage(false); onMsg("Import staged."); void load(); }} />
      )}
    </>
  );
}

function StageImportModal({ workspaceId, onClose, onStaged }: { workspaceId: string; onClose: () => void; onStaged: () => void }) {
  const [json, setJson] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const submit = async () => {
    setBusy(true); setErr(null);
    let data: Record<string, unknown>;
    try { data = JSON.parse(json); } catch { setErr("Invalid JSON"); setBusy(false); return; }
    try { await api.stagePeopleImport(workspaceId, data, "pasted.json"); onStaged(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Stage failed"); setBusy(false); }
  };
  return (
    <Modal open title="Stage Cricket Statz import" onClose={onClose} footer={
      <>
        <Button variant="outline" size="sm" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button size="sm" onClick={() => void submit()} disabled={busy || !json.trim()}>{busy ? "Staging..." : "Stage"}</Button>
      </>
    }>
      <div className="flex flex-col gap-3">
        {err && <ErrorState message={err} />}
        <Field label="Export JSON" hint='Object with "players" and/or "officials" arrays. Staged verbatim; promoted only after review.'>
          <Textarea value={json} onChange={(e) => setJson(e.target.value)} className="min-h-[180px] font-mono text-xs" />
        </Field>
      </div>
    </Modal>
  );
}

function ImportBatchModal({ workspaceId, batchId, canManage, onClose, onMsg }: {
  workspaceId: string; batchId: string; canManage: boolean; onClose: () => void; onMsg: (m: string) => void;
}) {
  const [records, setRecords] = useState<ImportRecord[]>([]);
  const [recon, setRecon] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmAction, setConfirmAction] = useState<"promote" | "rollback" | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setErr(null);
    try {
      setRecords(await api.listPeopleImportRecords(workspaceId, batchId));
      setRecon(await api.reconcilePeopleImport(workspaceId, batchId));
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Failed to load batch"); }
    finally { setLoading(false); }
  }, [workspaceId, batchId]);
  useEffect(() => { void load(); }, [load]);

  const act = async (fn: () => Promise<unknown>, done: string) => {
    setBusy(true);
    try { await fn(); onMsg(done); await load(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Action failed"); }
    finally { setBusy(false); setConfirmAction(null); }
  };

  const decide = (recordId: string, decision: string) =>
    void act(() => api.decidePeopleImportRecord(workspaceId, batchId, recordId, { decision }), `Record ${decision}.`);

  return (
    <Modal open title="Import review" onClose={onClose}>
      {loading && <LoadingState />}
      {!loading && err && <ErrorState message={err} onRetry={() => void load()} />}
      {!loading && !err && (
        <div className="flex flex-col gap-4">
          {recon && (
            <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
              {["total_staged", "new_candidates", "matched_existing", "possible_duplicates", "promoted", "needs_review", "deferred", "rejected"].map((k) => (
                <div key={k} className="rounded-[var(--radius-app)] border border-border p-2">
                  <div className="text-lg font-semibold">{recon[k] ?? 0}</div>
                  <div className="text-[11px] text-muted-foreground">{humanise(k)}</div>
                </div>
              ))}
            </div>
          )}
          {canManage && (
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" disabled={busy} onClick={() => void act(() => api.detectPeopleImport(workspaceId, batchId), "Detection complete.")}>Detect</Button>
              <Button size="sm" disabled={busy} onClick={() => setConfirmAction("promote")}>Promote approved</Button>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => setConfirmAction("rollback")}>Rollback</Button>
            </div>
          )}
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Records</h3>
            <ul className="space-y-2">
              {records.map((r) => {
                const norm = r.normalised as Record<string, any>;
                return (
                  <li key={r.id} className="rounded-[var(--radius-app)] border border-border p-2 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <span className="font-medium">{norm?.display_name ?? "(unknown)"}</span>{" "}
                        <span className="text-xs text-muted-foreground">{humanise(r.entity_type)} · {r.source_ref}</span>
                      </div>
                      <Badge variant={r.status === "promoted" ? "success" : r.status === "unresolved" ? "warning" : "muted"}>
                        {humanise(r.resolution ?? r.status)}
                      </Badge>
                    </div>
                    {canManage && r.status === "unresolved" && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        <Button size="sm" variant="outline" onClick={() => decide(r.id, "new")}>New person</Button>
                        <Button size="sm" variant="ghost" onClick={() => decide(r.id, "distinct")}>Distinct</Button>
                        <Button size="sm" variant="ghost" onClick={() => decide(r.id, "defer")}>Defer</Button>
                        <Button size="sm" variant="ghost" onClick={() => decide(r.id, "reject")}>Reject</Button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        </div>
      )}
      {confirmAction && (
        <ConfirmDialog open busy={busy} danger={confirmAction === "rollback"}
          title={confirmAction === "promote" ? "Promote approved records" : "Rollback import"}
          confirmLabel={confirmAction === "promote" ? "Promote" : "Rollback"}
          description={confirmAction === "promote"
            ? "Promote all approved records into verified identities? Unresolved records are left for review."
            : "Reverse this import, deleting people this batch created? Linked existing people are untouched."}
          onConfirm={() => confirmAction === "promote"
            ? void act(() => api.promotePeopleImport(workspaceId, batchId), "Promotion complete.")
            : void act(() => api.rollbackPeopleImport(workspaceId, batchId), "Import rolled back.")}
          onCancel={() => setConfirmAction(null)} />
      )}
    </Modal>
  );
}

/**
 * Inline add-control for a person's Numbers / Leadership / Recognition (wires the backend POST endpoints).
 * Numbers and Leadership require a club (organisation); Recognition is a free type. Add-only for now
 * (the backend has no delete endpoint for these).
 */
function AttrAdder({ kind, workspaceId, personId, orgs, onDone }: {
  kind: "number" | "leadership" | "recognition";
  workspaceId: string;
  personId: string;
  orgs: { id: string; name: string }[];
  onDone: (message: string) => void;
}) {
  const [orgId, setOrgId] = useState("");
  const [value, setValue] = useState("");
  const [season, setSeason] = useState("");
  const [busy, setBusy] = useState(false);
  const needsOrg = kind !== "recognition";
  const placeholder = kind === "number" ? "Squad number" : kind === "leadership" ? "Role (e.g. Captain)" : "e.g. Life Member";

  const add = async () => {
    if (!value.trim() || (needsOrg && !orgId)) return;
    setBusy(true);
    const sl = season.trim() || undefined;
    try {
      if (kind === "number") await api.addPersonNumber(workspaceId, personId, { organisation_id: orgId, number: value.trim(), season_label: sl });
      else if (kind === "leadership") await api.addPersonLeadership(workspaceId, personId, { organisation_id: orgId, role: value.trim(), season_label: sl });
      else await api.addPersonRecognition(workspaceId, personId, { recognition_type: value.trim(), season_label: sl });
      setValue(""); setOrgId(""); setSeason("");
      onDone(`${kind.charAt(0).toUpperCase()}${kind.slice(1)} added.`);
    } catch (e) {
      onDone(e instanceof ApiError ? e.message : "Could not add.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-2 flex flex-col gap-1">
      {needsOrg && (
        <Select value={orgId} disabled={busy} onChange={(e) => setOrgId(e.target.value)} className="h-7 text-xs">
          <option value="">— choose club —</option>
          {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </Select>
      )}
      <Input value={value} disabled={busy} placeholder={placeholder} className="h-7 text-xs"
        onChange={(e) => setValue(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void add(); }} />
      <div className="flex gap-1">
        <Input value={season} disabled={busy} placeholder="Season (e.g. 2023/24, optional)" className="h-7 text-xs"
          onChange={(e) => setSeason(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void add(); }} />
        <Button size="sm" variant="outline" disabled={busy || !value.trim() || (needsOrg && !orgId)}
          onClick={() => void add()}>Add</Button>
      </div>
    </div>
  );
}
