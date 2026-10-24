/**
 * Universal "Create Person" wizard (Stage 7). ONE reusable component for creating any cricket
 * person — player, umpire, scorer, captain, official, … — writing to the single ``person`` identity
 * via the existing API (no duplicate person databases). The visible title adapts to the launching
 * field ("Create Player", "Create Umpire", …) but the record, validation and identity-matching are
 * the same everywhere.
 *
 * It searches existing people as you type and shows **possible matches** so the user can pick an
 * existing identity (optionally adding the new role) instead of creating a duplicate — identities
 * are NEVER merged automatically on a name. Creation is a single transactional API call (person +
 * roles). Cancel creates nothing. On success the created/selected person is returned to the
 * originating field.
 */

import { AlertTriangle, ArrowRight, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Modal } from "../../components/ui/dialog";
import { Input, Textarea } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { ErrorState } from "../../components/states/States";
import { api, ApiError, type Person } from "../../lib/api";
import { Field } from "../manage/_shared";

// person-level roles (match-specific captain/keeper are recorded on the match, not here)
const ROLES = ["player", "umpire", "scorer", "coach", "administrator", "selector", "captain", "official", "other"];
const DOB_PRECISIONS = ["unknown", "exact", "year", "month", "approx"];

export function PersonWizard({
  workspaceId, initialName, roleLabel = "Person", defaultRole = "player", onCreated, onCancel,
}: {
  workspaceId: string;
  initialName: string;
  roleLabel?: string;
  defaultRole?: string;
  onCreated: (p: Person) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initialName);
  const [roles, setRoles] = useState<string[]>(defaultRole ? [defaultRole] : []);
  const [dob, setDob] = useState("");
  const [dobPrecision, setDobPrecision] = useState("unknown");
  const [notes, setNotes] = useState("");
  const [showMore, setShowMore] = useState(false);
  const [matches, setMatches] = useState<Person[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // search existing people as the name is typed — surface possible duplicates (never auto-merge)
  useEffect(() => {
    const q = name.trim();
    if (q.length < 2) { setMatches([]); return; }
    const t = setTimeout(async () => {
      try {
        setMatches(await api.listPeople(workspaceId, { search: q }));
      } catch {
        setMatches([]);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [name, workspaceId]);

  const toggleRole = (r: string) =>
    setRoles((cur) => (cur.includes(r) ? cur.filter((x) => x !== r) : [...cur, r]));

  const useExisting = async (p: Person) => {
    setBusy(true);
    setErr(null);
    try {
      // add any newly-chosen person-level roles to the existing identity (no duplicate record)
      for (const r of roles) {
        try { await api.addPersonRole(workspaceId, p.id, r); } catch { /* role may already exist */ }
      }
      onCreated(p);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not update the existing person");
      setBusy(false);
    }
  };

  const create = async () => {
    const display_name = name.trim();
    if (!display_name) return;
    setBusy(true);
    setErr(null);
    try {
      const created = (await api.createPerson(workspaceId, {
        display_name, roles,
        dob: dob || null, dob_precision: dob ? dobPrecision : "unknown",
        notes: notes || null,
      })) as { id: string };
      onCreated({
        id: created.id, display_name, status: "active", is_junior: false, privacy_protected: false,
        dob: dob || null, dob_precision: dob ? dobPrecision : "unknown", notes: notes || null, merged_into_id: null,
      });
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Could not create the person");
      setBusy(false);
    }
  };

  return (
    <Modal open title={`Create ${roleLabel}`} onClose={onCancel} footer={
      <>
        <Button variant="outline" size="sm" onClick={onCancel} disabled={busy}>Cancel</Button>
        <Button size="sm" onClick={() => void create()} disabled={busy || !name.trim()}>
          <UserPlus className="h-4 w-4" aria-hidden /> {busy ? "Creating…" : "Create Person"}
        </Button>
      </>
    }>
      <div className="flex flex-col gap-4">
        {err && <ErrorState message={err} />}

        <Field label="Name" hint="One stable identity. Flexible for historical names (e.g. “J Smith”). Unknown stays unknown — nothing is invented.">
          <Input value={name} autoFocus onChange={(e) => setName(e.target.value)} placeholder="e.g. Tony Cacciola" />
        </Field>

        {matches.length > 0 && (
          <div className="rounded-[var(--radius-app)] border border-warning/40 bg-warning/5 p-3">
            <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-warning">
              <AlertTriangle className="h-3.5 w-3.5" aria-hidden /> Possible existing people
            </div>
            <p className="mb-2 text-xs text-muted-foreground">
              Two people can share a name — only pick an existing person if it is the same individual. Identities are never merged automatically.
            </p>
            <ul className="flex max-h-40 flex-col gap-1 overflow-auto">
              {matches.map((p) => (
                <li key={p.id}>
                  <button type="button" onClick={() => void useExisting(p)} disabled={busy}
                    className="flex w-full items-center gap-2 rounded-[var(--radius-app)] px-2 py-1.5 text-left text-sm hover:bg-muted">
                    <ArrowRight className="h-3.5 w-3.5 shrink-0 text-brand" aria-hidden />
                    <span className="truncate">Use existing: {p.display_name}</span>
                    {p.is_junior && <Badge variant="warning">junior</Badge>}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <Field label="Role(s)" hint="A person can hold several roles. Match-specific captaincy/keeping is recorded on the match, not here.">
          <div className="flex flex-wrap gap-1.5">
            {ROLES.map((r) => (
              <button key={r} type="button" onClick={() => toggleRole(r)}
                aria-pressed={roles.includes(r)}
                className={`rounded-full px-2.5 py-1 text-xs capitalize ${roles.includes(r) ? "bg-brand/15 text-brand" : "bg-muted text-muted-foreground hover:bg-muted/70"}`}>
                {r}
              </button>
            ))}
          </div>
        </Field>

        <button type="button" onClick={() => setShowMore((v) => !v)} className="self-start text-xs text-brand hover:underline">
          {showMore ? "Hide optional details" : "Add optional details (date of birth, notes)"}
        </button>
        {showMore && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Date of birth" hint="Leave blank if unknown.">
              <Input type="date" value={dob} onChange={(e) => setDob(e.target.value)} />
            </Field>
            <Field label="DOB precision">
              <Select value={dobPrecision} onChange={(e) => setDobPrecision(e.target.value)} disabled={!dob}>
                {DOB_PRECISIONS.map((p) => <option key={p} value={p}>{p}</option>)}
              </Select>
            </Field>
            <div className="sm:col-span-2">
              <Field label="Notes / source">
                <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. historical source reference" />
              </Field>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
