import { Building2, GitMerge, Plus } from "lucide-react";
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
  type OrganisationDetail,
} from "../../lib/api";
import { Detail, Field, NoWorkspace, Unknown, humanise, useManage } from "./_shared";

const KINDS = ["club", "association", "intl_team", "historical_club"];
// Properly capitalised display labels for the organisation kinds (the stored values stay lower_snake).
const KIND_LABELS: Record<string, string> = {
  club: "Club",
  association: "Association",
  intl_team: "International Team",
  historical_club: "Historical Club",
};
const kindLabel = (k: string): string => KIND_LABELS[k] ?? humanise(k);
// Statuses a user can set here; "merged" is system-managed and shown as a badge, never chosen.
const STATUSES = ["active", "archived"];
const statusLabel = (s: string): string => s.charAt(0).toUpperCase() + s.slice(1);

export function Organisations() {
  const { workspaceId, canManage } = useManage();
  const [items, setItems] = useState<Organisation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("");
  const [includeMerged, setIncludeMerged] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    try {
      const opts: { include_merged?: boolean; kind?: string } = {};
      if (includeMerged) opts.include_merged = true;
      if (kind) opts.kind = kind;
      setItems(await api.listOrganisations(workspaceId, opts));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load organisations");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, kind, includeMerged]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!workspaceId) {
    return (
      <AppShell title="Organisations" subtitle="Clubs, associations and historical organisations">
        <NoWorkspace />
      </AppShell>
    );
  }

  const filtered = items.filter((o) => o.name.toLowerCase().includes(search.toLowerCase()));

  return (
    <AppShell title="Organisations" subtitle="Clubs, associations and historical organisations">
      {msg && (
        <div className="mb-4 rounded-[var(--radius-app)] border border-success/40 bg-success/5 px-4 py-2 text-sm text-success">
          {msg}
        </div>
      )}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search by name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <Select value={kind} onChange={(e) => setKind(e.target.value)} className="max-w-[12rem]">
          <option value="">All kinds</option>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {kindLabel(k)}
            </option>
          ))}
        </Select>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <input type="checkbox" checked={includeMerged} onChange={(e) => setIncludeMerged(e.target.checked)} />
          Show merged
        </label>
        <div className="flex-1" />
        {canManage && (
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4" aria-hidden /> New organisation
          </Button>
        )}
      </div>

      {loading && <LoadingState label="Loading organisations..." />}
      {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}
      {!loading && !error && filtered.length === 0 && (
        <EmptyState
          icon={<Building2 className="h-8 w-8" aria-hidden />}
          title="No organisations"
          description={canManage ? "Create your first club or association." : "Nothing to show yet."}
        />
      )}
      {!loading && !error && filtered.length > 0 && (
        <div className="grid gap-3">
          {filtered.map((o) => (
            <Card key={o.id} className="cursor-pointer hover:border-brand" >
              <CardContent className="flex items-center gap-3 py-4" onClick={() => setSelected(o.id)}>
                <Building2 className="h-5 w-5 text-muted-foreground" aria-hidden />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{o.name}</div>
                  <div className="truncate text-xs text-muted-foreground">
                    {o.short_name ? `${o.short_name} · ` : ""}
                    {kindLabel(o.kind)}
                  </div>
                </div>
                <div className="flex shrink-0 gap-1">
                  {o.is_historical && <Badge variant="outline">historical</Badge>}
                  {o.merged_into_id && <Badge variant="warning">merged</Badge>}
                  <Badge variant={o.status === "active" ? "success" : "muted"}>{o.status}</Badge>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {selected && (
        <OrganisationDetailModal
          workspaceId={workspaceId}
          orgId={selected}
          canManage={canManage}
          onClose={() => setSelected(null)}
          onChanged={(m) => {
            setMsg(m);
            void load();
          }}
        />
      )}
      {showCreate && (
        <CreateOrganisationModal
          workspaceId={workspaceId}
          onClose={() => setShowCreate(false)}
          onCreated={(name) => {
            setShowCreate(false);
            setMsg(`Created "${name}".`);
            void load();
          }}
        />
      )}
    </AppShell>
  );
}

function CreateOrganisationModal({
  workspaceId,
  onClose,
  onCreated,
}: {
  workspaceId: string;
  onClose: () => void;
  onCreated: (name: string) => void;
}) {
  const [name, setName] = useState("");
  const [shortName, setShortName] = useState("");
  const [kind, setKind] = useState("club");
  const [isHistorical, setIsHistorical] = useState(false);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.createOrganisation(workspaceId, {
        name,
        short_name: shortName || null,
        kind,
        is_historical: isHistorical,
        notes: notes || null,
      });
      onCreated(name.trim());
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Failed to create organisation");
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      title="New organisation"
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
        <Field label="Short name" hint="Optional display abbreviation.">
          <Input value={shortName} onChange={(e) => setShortName(e.target.value)} />
        </Field>
        <Field label="Kind">
          <Select value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {kindLabel(k)}
              </option>
            ))}
          </Select>
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={isHistorical} onChange={(e) => setIsHistorical(e.target.checked)} />
          Historical organisation
        </label>
        <Field label="Notes">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
      </div>
    </Modal>
  );
}

function OrganisationDetailModal({
  workspaceId,
  orgId,
  canManage,
  onClose,
  onChanged,
}: {
  workspaceId: string;
  orgId: string;
  canManage: boolean;
  onClose: () => void;
  onChanged: (msg: string) => void;
}) {
  const [org, setOrg] = useState<OrganisationDetail | null>(null);
  const [candidates, setCandidates] = useState<DuplicateCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<
    | { kind: "merge" | "distinct"; candidateId: string; candidateName: string }
    | { kind: "undo" }
    | null
  >(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    name: "", short_name: "", kind: "club", status: "active", is_historical: false, notes: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const detail = await api.getOrganisation(workspaceId, orgId);
      setOrg(detail);
      try {
        setCandidates(await api.orgDuplicateCandidates(workspaceId, orgId));
      } catch {
        setCandidates([]);
      }
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Failed to load organisation");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, orgId]);

  useEffect(() => {
    void load();
  }, [load]);

  const runConfirm = async () => {
    if (!confirm) return;
    setBusy(true);
    try {
      if (confirm.kind === "merge") {
        await api.orgMerge(workspaceId, {
          canonical_organisation_id: orgId,
          merged_organisation_id: confirm.candidateId,
          reason: "confirmed duplicate (desktop)",
        });
        onChanged(`Merged "${confirm.candidateName}" into this organisation.`);
      } else if (confirm.kind === "distinct") {
        await api.orgAssertDistinct(workspaceId, {
          organisation_a_id: orgId,
          organisation_b_id: confirm.candidateId,
          reason: "marked distinct (desktop)",
        });
        onChanged(`Marked "${confirm.candidateName}" as distinct.`);
      }
      setConfirm(null);
      await load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  const beginEdit = () => {
    if (!org) return;
    setForm({
      name: org.name,
      short_name: org.short_name ?? "",
      kind: org.kind,
      status: org.status,
      is_historical: org.is_historical,
      notes: org.notes ?? "",
    });
    setErr(null);
    setEditing(true);
  };

  const saveEdit = async () => {
    if (!org) return;
    const name = form.name.trim();
    if (!name) {
      setErr("Name is required.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api.updateOrganisation(workspaceId, orgId, {
        name,
        short_name: form.short_name.trim() || null,
        kind: form.kind,
        status: form.status,
        is_historical: form.is_historical,
        notes: form.notes.trim() || null,
        name_change_note: name !== org.name ? "renamed" : undefined,
      });
      setEditing(false);
      onChanged(
        name !== org.name
          ? `Renamed to "${name}". The previous name is kept as an alias; scorecards update automatically.`
          : `Updated "${name}".`,
      );
      await load();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open title={org?.name ?? "Organisation"} onClose={onClose}>
      {loading && <LoadingState />}
      {!loading && err && <ErrorState message={err} onRetry={() => void load()} />}
      {!loading && org && (
        <div className="flex flex-col gap-5">
          <section>
            {!editing ? (
              <>
                {canManage && !org.merged_into_id && (
                  <div className="mb-2 flex justify-end">
                    <Button size="sm" variant="outline" onClick={beginEdit}>Edit details</Button>
                  </div>
                )}
                <Detail label="Kind">{kindLabel(org.kind)}</Detail>
                <Detail label="Short name"><Unknown value={org.short_name} /></Detail>
                <Detail label="Status">{statusLabel(org.status)}</Detail>
                <Detail label="Historical">{org.is_historical ? "Yes" : "No"}</Detail>
                <Detail label="Notes"><Unknown value={org.notes} /></Detail>
                {org.merged_into_id && (
                  <Detail label="Merged into">
                    <Badge variant="warning">this record is merged</Badge>
                  </Detail>
                )}
              </>
            ) : (
              <div className="flex flex-col gap-3">
                <Field label="Name" hint="The previous name is kept as an alias; scorecards update automatically.">
                  <Input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} autoFocus />
                </Field>
                <Field label="Short name" hint="Optional display abbreviation.">
                  <Input value={form.short_name} onChange={(e) => setForm((f) => ({ ...f, short_name: e.target.value }))} />
                </Field>
                <Field label="Kind">
                  <Select value={form.kind} onChange={(e) => setForm((f) => ({ ...f, kind: e.target.value }))}>
                    {KINDS.map((k) => (
                      <option key={k} value={k}>{kindLabel(k)}</option>
                    ))}
                  </Select>
                </Field>
                <Field label="Status">
                  <Select value={form.status} onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))}>
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>{statusLabel(s)}</option>
                    ))}
                  </Select>
                </Field>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form.is_historical}
                    onChange={(e) => setForm((f) => ({ ...f, is_historical: e.target.checked }))}
                  />
                  Historical organisation
                </label>
                <Field label="Notes">
                  <Textarea value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} />
                </Field>
                <div className="flex justify-end gap-2">
                  <Button size="sm" variant="outline" onClick={() => setEditing(false)} disabled={busy}>Cancel</Button>
                  <Button size="sm" onClick={() => void saveEdit()} disabled={busy || !form.name.trim()}>
                    {busy ? "Saving..." : "Save"}
                  </Button>
                </div>
              </div>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Historical names</h3>
            {org.name_history.length === 0 ? (
              <p className="text-sm text-muted-foreground">No recorded names.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {org.name_history.map((n) => (
                  <li key={n.id} className="flex justify-between gap-3">
                    <span>{n.name}</span>
                    <span className="text-muted-foreground">
                      <Unknown value={n.valid_from} />
                      {" – "}
                      {n.valid_to ?? "present"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Source identities</h3>
            {org.source_identities.length === 0 ? (
              <p className="text-sm text-muted-foreground">No external source references.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {org.source_identities.map((s) => (
                  <li key={s.id} className="flex justify-between gap-3">
                    <span className="text-muted-foreground">{s.source_system}</span>
                    <span>{s.source_ref}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase text-muted-foreground">
              Possible duplicates
            </h3>
            <p className="mb-2 text-xs text-muted-foreground">
              Suggestions only — nothing is merged automatically. A name match alone is not proof.
            </p>
            {candidates.length === 0 ? (
              <p className="text-sm text-muted-foreground">No duplicate suggestions.</p>
            ) : (
              <ul className="space-y-2">
                {candidates.map((c) => (
                  <li
                    key={c.organisation_id}
                    className="flex items-center justify-between gap-2 rounded-[var(--radius-app)] border border-border p-2 text-sm"
                  >
                    <div className="min-w-0">
                      <div className="truncate">{c.name}</div>
                      <div className="flex gap-1">
                        <Badge variant={c.confidence === "strong" ? "warning" : "muted"}>{c.confidence}</Badge>
                        {c.evidence.map((ev) => (
                          <Badge key={ev} variant="outline">
                            {humanise(ev)}
                          </Badge>
                        ))}
                      </div>
                    </div>
                    {canManage && (
                      <div className="flex shrink-0 gap-1">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            setConfirm({ kind: "merge", candidateId: c.organisation_id!, candidateName: c.name })
                          }
                        >
                          <GitMerge className="h-4 w-4" aria-hidden /> Merge
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            setConfirm({ kind: "distinct", candidateId: c.organisation_id!, candidateName: c.name })
                          }
                        >
                          Mark distinct
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

      {confirm?.kind === "merge" && (
        <ConfirmDialog
          open
          danger
          busy={busy}
          title="Confirm merge"
          confirmLabel="Merge"
          description={
            <>
              Merge <b>{confirm.candidateName}</b> into <b>{org?.name}</b>? This is reversible — the
              merged record is preserved, not deleted, and can be restored later.
            </>
          }
          onConfirm={() => void runConfirm()}
          onCancel={() => setConfirm(null)}
        />
      )}
      {confirm?.kind === "distinct" && (
        <ConfirmDialog
          open
          busy={busy}
          title="Mark as distinct"
          confirmLabel="Mark distinct"
          description={
            <>
              Record that <b>{confirm.candidateName}</b> and <b>{org?.name}</b> are definitely
              different organisations? They will never be suggested as duplicates again and cannot be
              merged.
            </>
          }
          onConfirm={() => void runConfirm()}
          onCancel={() => setConfirm(null)}
        />
      )}
    </Modal>
  );
}
