import { SlidersHorizontal } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { ErrorState, LoadingState } from "../../components/states/States";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import {
  ApiError,
  api,
  type Competition,
  type CompetitionDetail,
  type ResolvedConditions,
} from "../../lib/api";
import { Field, NoWorkspace, useManage } from "./_shared";
import { useToast } from "../../lib/toast";

const NUMERIC_FIELDS = ["overs_limit", "max_players", "balls_per_over", "innings_per_side"] as const;
const FIELD_LABELS: Record<string, string> = {
  overs_limit: "Overs limit",
  max_players: "Max players (team size)",
  balls_per_over: "Balls per over",
  innings_per_side: "Innings per side",
  format: "Match format",
  points: "Points scheme",
};

export function PlayingConditions() {
  const { workspaceId, canManage } = useManage();
  const [comps, setComps] = useState<Competition[]>([]);
  const [compId, setCompId] = useState("");
  const [detail, setDetail] = useState<CompetitionDetail | null>(null);
  const [seasonId, setSeasonId] = useState("");
  const [gradeId, setGradeId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resolved, setResolved] = useState<ResolvedConditions | null>(null);
  const toast = useToast();

  // configure form
  const [scope, setScope] = useState("competition");
  const [form, setForm] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!workspaceId) return;
    void api
      .listCompetitions(workspaceId)
      .then((c) => {
        setComps(c);
        if (c[0]) setCompId(c[0].id);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load competitions"));
  }, [workspaceId]);

  const loadDetail = useCallback(async () => {
    if (!workspaceId || !compId) return;
    setLoading(true);
    setError(null);
    try {
      setDetail(await api.getCompetition(workspaceId, compId));
      setSeasonId("");
      setGradeId("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load competition");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, compId]);

  useEffect(() => {
    void loadDetail();
  }, [loadDetail]);

  const resolve = useCallback(async () => {
    if (!workspaceId || !compId) return;
    try {
      const opts: Record<string, string> = { competition_id: compId };
      if (seasonId) opts.season_id = seasonId;
      if (gradeId) opts.grade_id = gradeId;
      setResolved(await api.resolveConditions(workspaceId, opts));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to resolve conditions");
    }
  }, [workspaceId, compId, seasonId, gradeId]);

  useEffect(() => {
    void resolve();
  }, [resolve]);

  if (!workspaceId) {
    return (
      <AppShell title="Playing Conditions" subtitle="Historical rules by competition, season, grade and match">
        <NoWorkspace />
      </AppShell>
    );
  }

  const targetForScope = (): string => {
    if (scope === "competition") return compId;
    if (scope === "season") return seasonId;
    if (scope === "grade") return gradeId;
    return form.match_id ?? "";
  };

  const deepestSelected = (): string => {
    if (gradeId) return "grade";
    if (seasonId) return "season";
    return "competition";
  };

  const save = async () => {
    const target = targetForScope();
    if (!target) {
      setError(`Select a ${scope} target first.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { scope, target_id: target };
      for (const f of NUMERIC_FIELDS) {
        if (form[f]) body[f] = Number(form[f]);
      }
      if (form.format) body.format = form.format;
      if (form.points) {
        try {
          body.points = JSON.parse(form.points);
        } catch {
          setError("Points must be valid JSON, e.g. {\"win\": 6, \"draw\": 1}");
          setBusy(false);
          return;
        }
      }
      await api.setConditions(workspaceId, body);
      toast.success(`Saved ${scope} playing conditions.`);
      setForm({});
      await resolve();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to save conditions");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppShell title="Playing Conditions" subtitle="Historical rules by competition, season, grade and match">
      {comps.length === 0 ? (
        <ErrorState message="Create a competition first — playing conditions attach to competitions, seasons and grades." />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Scope</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <Field label="Competition">
                <Select value={compId} onChange={(e) => setCompId(e.target.value)}>
                  {comps.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Season" hint="Optional — narrows the resolved rules.">
                <Select value={seasonId} onChange={(e) => setSeasonId(e.target.value)} disabled={!detail?.seasons.length}>
                  <option value="">(competition-wide)</option>
                  {detail?.seasons.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Grade" hint="Optional — most specific scope.">
                <Select value={gradeId} onChange={(e) => setGradeId(e.target.value)} disabled={!detail?.grades.length}>
                  <option value="">(all grades)</option>
                  {detail?.grades.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                    </option>
                  ))}
                </Select>
              </Field>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Effective conditions</CardTitle>
            </CardHeader>
            <CardContent>
              {loading && <LoadingState />}
              {!loading && error && <ErrorState message={error} onRetry={() => void resolve()} />}
              {!loading && resolved && (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase text-muted-foreground">
                      <th className="pb-2 font-medium">Rule</th>
                      <th className="pb-2 font-medium">Value</th>
                      <th className="pb-2 font-medium">Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.keys(FIELD_LABELS).map((f) => {
                      const value = resolved.conditions[f];
                      const source = resolved.sources[f];
                      return (
                        <tr key={f} className="border-t border-border">
                          <td className="py-1.5">{FIELD_LABELS[f]}</td>
                          <td className="py-1.5">
                            {value === null || value === undefined ? (
                              <span className="italic text-muted-foreground">Unknown</span>
                            ) : typeof value === "object" ? (
                              <code className="text-xs">{JSON.stringify(value)}</code>
                            ) : (
                              String(value)
                            )}
                          </td>
                          <td className="py-1.5">
                            {source === null || source === undefined ? (
                              <Badge variant="outline">unknown</Badge>
                            ) : source === deepestSelected() ? (
                              <Badge variant="brand">configured here</Badge>
                            ) : (
                              <Badge variant="muted">inherited · {source}</Badge>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
              <p className="mt-3 text-xs text-muted-foreground">
                Resolution order: match → grade → season → competition. Unknown values are never
                defaulted.
              </p>
            </CardContent>
          </Card>

          {canManage && (
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Configure conditions</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <Field label="Apply at scope">
                    <Select value={scope} onChange={(e) => setScope(e.target.value)}>
                      <option value="competition">Competition</option>
                      <option value="season" disabled={!seasonId}>
                        Season {seasonId ? "" : "(select a season)"}
                      </option>
                      <option value="grade" disabled={!gradeId}>
                        Grade {gradeId ? "" : "(select a grade)"}
                      </option>
                      <option value="match">Match (by id)</option>
                    </Select>
                  </Field>
                  {scope === "match" && (
                    <Field label="Match id">
                      <Input value={form.match_id ?? ""} onChange={(e) => setForm((v) => ({ ...v, match_id: e.target.value }))} />
                    </Field>
                  )}
                  {NUMERIC_FIELDS.map((f) => (
                    <Field key={f} label={FIELD_LABELS[f]} hint="Blank = leave unknown.">
                      <Input
                        type="number"
                        min={1}
                        value={form[f] ?? ""}
                        onChange={(e) => setForm((v) => ({ ...v, [f]: e.target.value }))}
                      />
                    </Field>
                  ))}
                  <Field label="Format">
                    <Input value={form.format ?? ""} onChange={(e) => setForm((v) => ({ ...v, format: e.target.value }))} placeholder="e.g. two_day" />
                  </Field>
                  <Field label="Points (JSON)" hint='e.g. {"win":6,"draw":1}'>
                    <Input value={form.points ?? ""} onChange={(e) => setForm((v) => ({ ...v, points: e.target.value }))} />
                  </Field>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => void save()} disabled={busy}>
                    <SlidersHorizontal className="h-4 w-4" aria-hidden /> Save conditions
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Only the fields you fill are applied; blank fields stay unknown. Team-size limits
                  (e.g. 15 for juniors) are configured here, never imposed by default.
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </AppShell>
  );
}
