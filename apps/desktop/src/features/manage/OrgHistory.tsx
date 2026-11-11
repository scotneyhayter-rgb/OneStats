import { CalendarClock, Plus, Tag, Undo2, Waypoints } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { EmptyState, ErrorState, LoadingState } from "../../components/states/States";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { ConfirmDialog, Modal } from "../../components/ui/dialog";
import { Input, Textarea } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import {
  ApiError,
  api,
  type Organisation,
  type OrgRelationship,
  type OrgTimeline,
} from "../../lib/api";
import { Field, NoWorkspace, Unknown, humanise, useManage } from "./_shared";
import { useToast } from "../../lib/toast";

const REL_TYPES = [
  "merger",
  "amalgamation",
  "rename",
  "affiliation",
  "association_transfer",
  "predecessor",
  "successor",
  "other",
];

export function OrgHistory() {
  const { workspaceId, canManage } = useManage();
  const [orgs, setOrgs] = useState<Organisation[]>([]);
  const [orgId, setOrgId] = useState("");
  const [timeline, setTimeline] = useState<OrgTimeline | null>(null);
  const [rels, setRels] = useState<OrgRelationship[]>([]);
  const [includeVoid, setIncludeVoid] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [confirmVoid, setConfirmVoid] = useState<OrgRelationship | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const orgName = useCallback((id: string) => orgs.find((o) => o.id === id)?.name ?? id.slice(0, 8), [orgs]);

  useEffect(() => {
    if (!workspaceId) return;
    void api.listOrganisations(workspaceId, { include_merged: true }).then((o) => {
      setOrgs(o);
      if (o[0]) setOrgId(o[0].id);
    });
  }, [workspaceId]);

  const load = useCallback(async () => {
    if (!workspaceId || !orgId) return;
    setLoading(true);
    setError(null);
    try {
      const [tl, r] = await Promise.all([
        api.orgTimeline(workspaceId, orgId),
        api.listRelationships(workspaceId, orgId, { include_void: includeVoid }),
      ]);
      setTimeline(tl);
      setRels(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load history");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, orgId, includeVoid]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!workspaceId) {
    return (
      <AppShell title="Organisation History" subtitle="Timeline, relationships and provenance">
        <NoWorkspace />
      </AppShell>
    );
  }

  const doVoid = async () => {
    if (!confirmVoid) return;
    setBusy(true);
    try {
      await api.voidRelationship(workspaceId, confirmVoid.id);
      toast.success("Relationship reversed (voided). It is preserved and can be restored.");
      setConfirmVoid(null);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to void relationship");
    } finally {
      setBusy(false);
    }
  };

  const restore = async (id: string) => {
    setBusy(true);
    try {
      await api.restoreRelationship(workspaceId, id);
      toast.success("Relationship restored.");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to restore");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppShell title="Organisation History" subtitle="Timeline, relationships and provenance">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select value={orgId} onChange={(e) => setOrgId(e.target.value)} className="max-w-sm">
          {orgs.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </Select>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <input type="checkbox" checked={includeVoid} onChange={(e) => setIncludeVoid(e.target.checked)} />
          Show reversed
        </label>
        <div className="flex-1" />
        {canManage && orgId && (
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4" aria-hidden /> Add relationship
          </Button>
        )}
      </div>

      {orgs.length === 0 && <EmptyState title="No organisations" description="Create organisations first, then record their history." />}
      {loading && <LoadingState label="Loading history..." />}
      {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}

      {!loading && !error && timeline && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              {timeline.events.length === 0 ? (
                <p className="text-sm text-muted-foreground">No recorded history yet.</p>
              ) : (
                <ol className="relative ml-3 border-l border-border">
                  {timeline.events.map((ev, i) => (
                    <li key={i} className="mb-4 ml-4">
                      <span className="absolute -left-[7px] mt-1.5 h-3 w-3 rounded-full border border-border bg-card" aria-hidden />
                      <div className="flex items-center gap-2">
                        {ev.kind === "name" ? (
                          <Tag className="h-4 w-4 text-muted-foreground" aria-hidden />
                        ) : (
                          <Waypoints className="h-4 w-4 text-muted-foreground" aria-hidden />
                        )}
                        <span className="text-sm font-medium">
                          {ev.kind === "name" ? ev.name : humanise(ev.rel_type ?? "relationship")}
                        </span>
                        {ev.uncertain && <Badge variant="warning">date uncertain</Badge>}
                      </div>
                      <div className="mt-0.5 text-xs text-muted-foreground">
                        {ev.kind === "relationship" && ev.from_org_id && ev.to_org_id && (
                          <span>
                            {orgName(ev.from_org_id)} → {orgName(ev.to_org_id)} ·{" "}
                          </span>
                        )}
                        <Unknown value={ev.valid_from} />
                        {" – "}
                        {ev.valid_to ?? "present"}
                        {ev.evidence ? ` · evidence: ${ev.evidence}` : ""}
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Relationships</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-3 text-xs text-muted-foreground">
                Relationships document history between <b>distinct</b> organisations. They never merge
                identities — administrative duplicate merges live under Organisations.
              </p>
              {rels.length === 0 ? (
                <p className="text-sm text-muted-foreground">No relationships recorded.</p>
              ) : (
                <ul className="space-y-2">
                  {rels.map((r) => (
                    <li key={r.id} className="rounded-[var(--radius-app)] border border-border p-3 text-sm">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <CalendarClock className="h-4 w-4 text-muted-foreground" aria-hidden />
                          <Badge variant="brand">{humanise(r.rel_type)}</Badge>
                          {r.is_void && <Badge variant="muted">reversed</Badge>}
                        </div>
                        {canManage &&
                          (r.is_void ? (
                            <Button size="sm" variant="ghost" onClick={() => void restore(r.id)} disabled={busy}>
                              <Undo2 className="h-4 w-4" aria-hidden /> Restore
                            </Button>
                          ) : (
                            <Button size="sm" variant="ghost" onClick={() => setConfirmVoid(r)} disabled={busy}>
                              Reverse
                            </Button>
                          ))}
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {orgName(r.from_org_id)} → {orgName(r.to_org_id)} ·{" "}
                        <Unknown value={r.valid_from} /> {" – "} {r.valid_to ?? "present"}
                      </div>
                      {r.evidence && <div className="mt-1 text-xs">Evidence: {r.evidence}</div>}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {showCreate && orgId && (
        <CreateRelationshipModal
          workspaceId={workspaceId}
          orgId={orgId}
          orgs={orgs}
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            toast.success("Relationship recorded.");
            void load();
          }}
        />
      )}
      {confirmVoid && (
        <ConfirmDialog
          open
          busy={busy}
          title="Reverse relationship"
          confirmLabel="Reverse"
          description="Reverse (void) this relationship? It is preserved and can be restored later — nothing is deleted."
          onConfirm={() => void doVoid()}
          onCancel={() => setConfirmVoid(null)}
        />
      )}
    </AppShell>
  );
}

function CreateRelationshipModal({
  workspaceId,
  orgId,
  orgs,
  onClose,
  onCreated,
}: {
  workspaceId: string;
  orgId: string;
  orgs: Organisation[];
  onClose: () => void;
  onCreated: () => void;
}) {
  const [direction, setDirection] = useState<"from" | "to">("from");
  const [otherId, setOtherId] = useState("");
  const [relType, setRelType] = useState("amalgamation");
  const [validFrom, setValidFrom] = useState("");
  const [validTo, setValidTo] = useState("");
  const [evidence, setEvidence] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const others = orgs.filter((o) => o.id !== orgId);

  const submit = async () => {
    if (!otherId) {
      setErr("Choose the other organisation.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      await api.createRelationship(workspaceId, {
        from_org_id: direction === "from" ? orgId : otherId,
        to_org_id: direction === "from" ? otherId : orgId,
        rel_type: relType,
        valid_from: validFrom || null,
        valid_to: validTo || null,
        evidence: evidence || null,
        notes: notes || null,
      });
      onCreated();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Failed to create relationship");
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      title="Add relationship"
      onClose={onClose}
      footer={
        <>
          <Button variant="outline" size="sm" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button size="sm" onClick={() => void submit()} disabled={busy || !otherId}>
            {busy ? "Saving..." : "Save"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        {err && <ErrorState message={err} />}
        <Field label="Type">
          <Select value={relType} onChange={(e) => setRelType(e.target.value)}>
            {REL_TYPES.map((t) => (
              <option key={t} value={t}>
                {humanise(t)}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Direction">
          <Select value={direction} onChange={(e) => setDirection(e.target.value as "from" | "to")}>
            <option value="from">This organisation → other</option>
            <option value="to">Other → this organisation</option>
          </Select>
        </Field>
        <Field label="Other organisation">
          <Select value={otherId} onChange={(e) => setOtherId(e.target.value)}>
            <option value="">Select…</option>
            {others.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Valid from" hint="Blank = unknown.">
            <Input type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} />
          </Field>
          <Field label="Valid to" hint="Blank = open/unknown.">
            <Input type="date" value={validTo} onChange={(e) => setValidTo(e.target.value)} />
          </Field>
        </div>
        <Field label="Supporting evidence">
          <Input value={evidence} onChange={(e) => setEvidence(e.target.value)} placeholder="e.g. 1980 league handbook" />
        </Field>
        <Field label="Notes">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
      </div>
    </Modal>
  );
}
