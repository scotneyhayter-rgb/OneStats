/**
 * Player management — full-page detail/edit screen (People → Directory → Manage).
 *
 * Replaces the old cramped detail modal with a roomier page: a header band (photo, name, roles,
 * playing style, current club) over a two-column body that groups the sections into cards. Adds the
 * ability to affiliate a player to a club directly from the clubs card. All editing, photos, merging,
 * numbers/leadership/recognition and the "played for" list carry over unchanged.
 */
import { ArrowLeft, GitMerge } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { compressImage } from "../../lib/utils";
import { AppShell } from "../../components/layout/AppShell";
import { ErrorState, LoadingState } from "../../components/states/States";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { ConfirmDialog } from "../../components/ui/dialog";
import { Input, Textarea } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { ApiError, api, type Person, type PersonDuplicateCandidate } from "../../lib/api";
import { Detail, NoWorkspace, Unknown, humanise, useManage } from "../manage/_shared";
import { AttrAdder } from "./PeopleManagement";

const AFFILIATION_ROLES = ["player", "captain", "coach", "umpire", "scorer", "administrator", "selector", "official", "member", "other"];

export function PlayerManage() {
  const { workspaceId, canManage } = useManage();
  const { personId = "" } = useParams();
  const navigate = useNavigate();

  const [view, setView] = useState<Record<string, any> | null>(null);
  const [candidates, setCandidates] = useState<PersonDuplicateCandidate[]>([]);
  const [orgs, setOrgs] = useState<{ id: string; name: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [bio, setBio] = useState("");
  const [batStyle, setBatStyle] = useState("");
  const [bowlStyle, setBowlStyle] = useState("");
  const [yearFor, setYearFor] = useState<{ kind: "number" | "leadership" | "recognition"; id: string; body: Record<string, unknown> } | null>(null);
  const [yearSeason, setYearSeason] = useState("");
  const [photoUrls, setPhotoUrls] = useState<Record<string, string>>({});
  const [confirm, setConfirm] = useState<{ candidateId: string; name: string; kind: "merge" | "distinct" } | null>(null);
  const [busy, setBusy] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [edName, setEdName] = useState("");
  const [edStatus, setEdStatus] = useState("active");
  const [edDob, setEdDob] = useState("");
  const [edDobPrec, setEdDobPrec] = useState("unknown");
  const [mergeSearch, setMergeSearch] = useState("");
  const [mergeResults, setMergeResults] = useState<Person[]>([]);
  const [searching, setSearching] = useState(false);
  // add-affiliation form
  const [affOrg, setAffOrg] = useState("");
  const [affRole, setAffRole] = useState("player");
  const [affFrom, setAffFrom] = useState("");
  const [affTo, setAffTo] = useState("");

  const onChanged = (m: string) => setMsg(m);

  const load = useCallback(async () => {
    if (!workspaceId || !personId) return;
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
    if (!workspaceId) return;
    (view?.photos ?? []).forEach((p: any) => {
      if (photoUrls[p.id]) return;
      api.personPhotoUrl(workspaceId, p.id).then((u) => setPhotoUrls((m) => ({ ...m, [p.id]: u }))).catch(() => {});
    });
  }, [view, workspaceId, photoUrls]);
  useEffect(() => {
    if (!workspaceId) { setMergeResults([]); return; }
    const q = mergeSearch.trim();
    if (q.length < 2) { setMergeResults([]); return; }
    let active = true; setSearching(true);
    api.listPeople(workspaceId, { search: q })
      .then((ppl) => { if (active) setMergeResults(ppl.filter((p) => p.id !== personId && !p.merged_into_id).slice(0, 8)); })
      .catch(() => { if (active) setMergeResults([]); })
      .finally(() => { if (active) setSearching(false); });
    return () => { active = false; };
  }, [mergeSearch, workspaceId, personId]);

  if (!workspaceId) return <AppShell title="Player" subtitle="Player management"><NoWorkspace /></AppShell>;

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
    } finally { setBusy(false); }
  };
  const removePhoto = async (photoId: string) => {
    try { await api.deletePersonPhoto(workspaceId, photoId); onChanged("Photo removed."); await load(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not remove photo."); }
  };

  const saveBio = async () => {
    setBusy(true);
    try {
      await api.upsertProfile(workspaceId, personId, { biography: bio, batting_style: batStyle || null, bowling_style: bowlStyle || null });
      onChanged("Profile saved."); await load();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Save failed"); }
    finally { setBusy(false); }
  };

  const protectedDob = Boolean((view?.person as any)?.protected_fields_hidden);
  const saveDetails = async () => {
    if (!edName.trim()) { setErr("Name cannot be empty."); return; }
    setBusy(true); setErr(null);
    try {
      const body: Record<string, unknown> = { display_name: edName.trim(), status: edStatus };
      if (!protectedDob) { body.set_dob = true; body.dob = edDob || null; body.dob_precision = edDob ? edDobPrec : "unknown"; }
      await api.updatePerson(workspaceId, personId, body);
      setEditOpen(false); onChanged("Details saved."); await load();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not save details."); }
    finally { setBusy(false); }
  };

  const addAffiliation = async () => {
    if (!affOrg) { setErr("Choose a club to affiliate the player to."); return; }
    setBusy(true); setErr(null);
    try {
      await api.createAffiliation(workspaceId, {
        person_id: personId, organisation_id: affOrg, role: affRole || "player",
        valid_from: affFrom || undefined, valid_to: affTo || undefined,
      });
      setAffOrg(""); setAffRole("player"); setAffFrom(""); setAffTo("");
      onChanged("Affiliation added."); await load();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not add the affiliation."); }
    finally { setBusy(false); }
  };

  const removeAttr = async (kind: "number" | "leadership" | "recognition", attrId: string) => {
    try {
      if (kind === "number") await api.deletePersonNumber(workspaceId, personId, attrId);
      else if (kind === "leadership") await api.deletePersonLeadership(workspaceId, personId, attrId);
      else await api.deletePersonRecognition(workspaceId, personId, attrId);
      onChanged("Removed."); await load();
    } catch (e) { setErr(e instanceof ApiError ? e.message : "Could not remove."); }
  };

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
  const clubName = (id: string) => orgs.find((o) => o.id === id)?.name ?? "Unknown club";
  const primaryClub = (view?.affiliations ?? [])[0];
  const sectionH = "mb-2 text-xs font-semibold uppercase text-muted-foreground";

  return (
    <AppShell title={person?.display_name ?? "Player"} subtitle="Player management">
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        <div className="flex items-center justify-between gap-2">
          <Button size="sm" variant="ghost" onClick={() => navigate("/people")}>
            <ArrowLeft className="h-4 w-4" aria-hidden /> Back to people
          </Button>
          <a href={`#/people/${personId}`} className="rounded-[var(--radius-app)] border border-brand bg-brand/10 px-3 py-1.5 text-sm font-medium text-brand">
            View full career profile →
          </a>
        </div>
        {msg && <div className="rounded-[var(--radius-app)] border border-success/40 bg-success/5 px-4 py-2 text-sm text-success">{msg}</div>}
        {err && <div className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-4 py-2 text-sm text-danger">{err}</div>}

        {loading && <LoadingState />}
        {!loading && err && !view && <ErrorState message={err} onRetry={() => void load()} />}
        {!loading && person && (
          <>
            {/* Header band */}
            <div className="flex flex-wrap items-center gap-4 rounded-[12px] border border-border bg-card p-4">
              <div className="relative">
                {(view?.photos ?? [])[0] && photoUrls[(view?.photos ?? [])[0].id]
                  ? <img src={photoUrls[(view?.photos ?? [])[0].id]} alt="" className="h-20 w-20 rounded-full object-cover" />
                  : <div className="flex h-20 w-20 items-center justify-center rounded-full bg-brand/10 text-xl font-medium text-brand">
                      {(person.display_name ?? "?").split(" ").map((s: string) => s[0]).slice(0, 2).join("")}
                    </div>}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-xl font-semibold">{person.display_name}</div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
                  <Badge variant={person.status === "active" ? "success" : "muted"}>{person.status}</Badge>
                  {(view?.person?.roles ?? []).map((r: string) => <Badge key={r} variant="brand">{humanise(r)}</Badge>)}
                  {primaryClub && <span className="text-muted-foreground">{clubName(primaryClub.organisation_id)}</span>}
                  {(batStyle || bowlStyle) && <span className="text-muted-foreground">· {[batStyle, bowlStyle].filter(Boolean).join(" / ")}</span>}
                </div>
                {person.protected_fields_hidden && <p className="mt-1 text-xs text-muted-foreground">Some personal fields are hidden by privacy protection.</p>}
              </div>
              {canManage && (
                <Button size="sm" variant="outline" onClick={() => { setEditOpen((o) => !o); setErr(null); }}>
                  {editOpen ? "Cancel" : "Edit details"}
                </Button>
              )}
            </div>

            {editOpen && canManage && (
              <div className="flex flex-col gap-2 rounded-[12px] border border-border p-4">
                <h3 className={sectionH}>Edit details</h3>
                <div className="grid gap-2 sm:grid-cols-2">
                  <label className="flex flex-col gap-1 text-xs">Name
                    <Input value={edName} onChange={(e) => setEdName(e.target.value)} placeholder="Display name" />
                  </label>
                  <label className="flex flex-col gap-1 text-xs">Status
                    <Select value={edStatus} onChange={(e) => setEdStatus(e.target.value)}>
                      <option value="active">active</option>
                      <option value="inactive">inactive</option>
                    </Select>
                  </label>
                  {!protectedDob && (
                    <>
                      <label className="flex flex-col gap-1 text-xs">Date of birth
                        <Input type="date" value={edDob} onChange={(e) => setEdDob(e.target.value)} />
                      </label>
                      <label className="flex flex-col gap-1 text-xs">Precision
                        <Select value={edDobPrec} onChange={(e) => setEdDobPrec(e.target.value)} disabled={!edDob}>
                          {["exact", "year", "month", "approx", "unknown"].map((p) => <option key={p} value={p}>{p}</option>)}
                        </Select>
                      </label>
                    </>
                  )}
                </div>
                {protectedDob && <p className="text-xs text-muted-foreground">Date of birth is privacy-protected and can't be edited here.</p>}
                <div className="mt-1 flex gap-2">
                  <Button size="sm" onClick={() => void saveDetails()} disabled={busy || !edName.trim()}>Save details</Button>
                  <Button size="sm" variant="ghost" onClick={() => { setEditOpen(false); setErr(null); void load(); }}>Cancel</Button>
                </div>
              </div>
            )}

            {/* Two-column body */}
            <div className="grid gap-4 lg:grid-cols-2">
              {/* Left: clubs + attributes */}
              <div className="flex flex-col gap-4">
                <section className="rounded-[12px] border border-border p-4">
                  <h3 className={sectionH}>Club &amp; team affiliations</h3>
                  {(view?.affiliations ?? []).length === 0 ? (
                    <p className="text-sm text-muted-foreground">No recorded affiliations.</p>
                  ) : (
                    <ul className="space-y-1 text-sm">
                      {(view?.affiliations ?? []).map((a: any) => (
                        <li key={a.id} className="flex justify-between gap-3">
                          <span>
                            <span className="font-medium">{clubName(a.organisation_id)}</span>
                            {a.role ? <span className="text-muted-foreground"> · {humanise(a.role)}</span> : null}
                          </span>
                          <span className="text-muted-foreground"><Unknown value={a.valid_from} /> – {a.valid_to ?? "present"}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {(view?.played_for_clubs ?? []).length > 0 && (
                    <div className="mt-2">
                      <p className="text-xs text-muted-foreground">Played for (from match appearances, no recorded affiliation):</p>
                      <ul className="mt-1 flex flex-wrap gap-1.5">
                        {(view?.played_for_clubs ?? []).map((c: any) => (
                          <li key={c.org_id} className="rounded-full border border-border bg-muted/40 px-2 py-0.5 text-xs">{c.club}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {canManage && (
                    <div className="mt-3 rounded-[var(--radius-app)] border border-brand/40 bg-brand/5 p-3">
                      <p className="mb-2 text-xs font-medium">Affiliate this player to a club</p>
                      <div className="flex flex-col gap-2">
                        <Select value={affOrg} onChange={(e) => setAffOrg(e.target.value)} className="h-8 text-sm">
                          <option value="">— choose club —</option>
                          {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                        </Select>
                        <div className="flex flex-wrap gap-2">
                          <label className="flex flex-1 flex-col gap-1 text-xs">Role
                            <Select value={affRole} onChange={(e) => setAffRole(e.target.value)} className="h-8 text-sm">
                              {AFFILIATION_ROLES.map((r) => <option key={r} value={r}>{humanise(r)}</option>)}
                            </Select>
                          </label>
                          <label className="flex flex-col gap-1 text-xs">From
                            <Input type="date" value={affFrom} onChange={(e) => setAffFrom(e.target.value)} className="h-8 text-sm" />
                          </label>
                          <label className="flex flex-col gap-1 text-xs">To
                            <Input type="date" value={affTo} onChange={(e) => setAffTo(e.target.value)} className="h-8 text-sm" />
                          </label>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button size="sm" disabled={busy || !affOrg} onClick={() => void addAffiliation()}>Add affiliation</Button>
                          <span className="text-xs text-muted-foreground">Dates are optional — leave blank if unknown.</span>
                        </div>
                      </div>
                    </div>
                  )}
                </section>

                <section className="rounded-[12px] border border-border p-4">
                  <div className="grid gap-3 sm:grid-cols-3">
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
                  </div>
                </section>

                {canManage && (
                  <section className="rounded-[12px] border border-border p-4">
                    <h3 className={sectionH}>Profile &amp; playing style</h3>
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
              </div>

              {/* Right: identity + photos + admin */}
              <div className="flex flex-col gap-4">
                <section className="rounded-[12px] border border-border p-4">
                  <h3 className={sectionH}>Photo</h3>
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

                <section className="rounded-[12px] border border-border p-4">
                  <h3 className={sectionH}>Details</h3>
                  <Detail label="Roles">{(view?.person?.roles ?? []).map((r: string) => humanise(r)).join(", ") || "—"}</Detail>
                  <Detail label="Date of birth"><Unknown value={person.dob} /></Detail>
                  {person.is_junior && <Detail label="Junior"><Badge variant="warning">personal data protected</Badge></Detail>}
                </section>

                <section className="rounded-[12px] border border-border p-4">
                  <h3 className={sectionH}>Historical names</h3>
                  {(view?.person?.names ?? []).length === 0 ? <p className="text-sm text-muted-foreground">—</p> : (
                    <ul className="space-y-1 text-sm">
                      {(view?.person?.names ?? []).map((n: any) => (
                        <li key={n.id} className="flex justify-between gap-3"><span>{n.name}</span><span className="text-muted-foreground">{humanise(n.name_type)}</span></li>
                      ))}
                    </ul>
                  )}
                </section>

                <section className="rounded-[12px] border border-border p-4">
                  <h3 className={sectionH}>Source identities</h3>
                  {(view?.person?.source_identities ?? []).length === 0 ? <p className="text-sm text-muted-foreground">—</p> : (
                    <ul className="space-y-1 text-sm">
                      {(view?.person?.source_identities ?? []).map((s: any) => (
                        <li key={s.id} className="flex justify-between gap-3"><span className="text-muted-foreground">{s.source_system}</span><span>{s.source_ref}</span></li>
                      ))}
                    </ul>
                  )}
                </section>

                <section className="rounded-[12px] border border-border p-4">
                  <h3 className={sectionH}>Duplicates &amp; merging</h3>
                  {canManage && (
                    <div className="mb-3 rounded-[var(--radius-app)] border border-border p-2">
                      <p className="mb-1 text-xs text-muted-foreground">Entered more than once? Search for the other record and merge it into this one. Reversible.</p>
                      <Input value={mergeSearch} onChange={(e) => setMergeSearch(e.target.value)} placeholder="Search a player to merge (name)…" className="h-8 text-sm" />
                      {mergeSearch.trim().length >= 2 && (
                        <div className="mt-2">
                          {searching && <p className="text-xs text-muted-foreground">Searching…</p>}
                          {!searching && mergeResults.length === 0 && <p className="text-xs text-muted-foreground">No other records match.</p>}
                          <ul className="space-y-1">
                            {mergeResults.map((p) => (
                              <li key={p.id} className="flex items-center justify-between gap-2 rounded-[var(--radius-app)] border border-border p-2 text-sm">
                                <span className="min-w-0 truncate">{p.display_name}</span>
                                <Button size="sm" variant="outline" className="shrink-0" onClick={() => setConfirm({ candidateId: p.id, name: p.display_name, kind: "merge" })}>
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
                              <Button size="sm" variant="ghost" onClick={() => setConfirm({ candidateId: c.person_id, name: c.display_name, kind: "distinct" })}>Distinct</Button>
                            </div>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </div>
            </div>
          </>
        )}
      </div>

      {confirm && (
        <ConfirmDialog open danger={confirm.kind === "merge"} busy={busy}
          title={confirm.kind === "merge" ? "Confirm merge" : "Mark as distinct"}
          confirmLabel={confirm.kind === "merge" ? "Merge" : "Mark distinct"}
          description={confirm.kind === "merge"
            ? <>Merge <b>{confirm.name}</b> into <b>{person?.display_name}</b>? Reversible — the merged record is preserved.</>
            : <>Record that <b>{confirm.name}</b> and <b>{person?.display_name}</b> are definitely different people?</>}
          onConfirm={() => void runConfirm()} onCancel={() => setConfirm(null)} />
      )}
    </AppShell>
  );
}
