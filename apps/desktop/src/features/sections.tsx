import { useState } from "react";
import { AppShell } from "../components/layout/AppShell";
import { Card, CardContent } from "../components/ui/card";
import { Select } from "../components/ui/select";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { canManage } from "../lib/permissions";
import { getUserScoreFormat, setUserScoreFormat } from "../lib/score-format";
import { useWorkspace } from "../lib/workspace-context";
import { Placeholder } from "./Placeholder";

// Matches and People now have full feature screens (features/scorecard, features/people);
// their old placeholders were removed. The sections below remain placeholders until built.

export function Statistics() {
  return (
    <Placeholder
      title="Statistics"
      subtitle="Records, reports and the statistics engine"
      planned={[
        "Club records and player statistics",
        "Batting, bowling, fielding and partnerships",
        "Teams & captains, milestones",
        "Report Builder and Data Integrity",
      ]}
    />
  );
}

export function Ask() {
  return (
    <Placeholder
      title="Ask OneStats"
      subtitle="Natural-language statistical queries"
      planned={[
        "Deterministic natural-language query mapping",
        "Answers from verified records only",
        "Supporting records and qualifications",
      ]}
    />
  );
}

export function Settings() {
  const { current, reload } = useWorkspace();
  const { user } = useAuth();
  const admin = canManage(user, current);
  const [wsFormat, setWsFormat] = useState<string>(current?.score_format ?? "au");
  const [userFormat, setUserFmt] = useState<string>(getUserScoreFormat() ?? "");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const saveWorkspace = async (v: string) => {
    if (!current) return;
    setWsFormat(v); setErr(null);
    try { await api.updateWorkspace(current.id, { score_format: v }); await reload(); setMsg("Workspace default updated."); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "Could not update the workspace default."); }
  };
  const example = (fmt: string) => (fmt === "en" ? "127/10" : "10/127");

  return (
    <AppShell title="Settings" subtitle="Workspace, display and configuration">
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        <Card><CardContent className="flex flex-col gap-4">
          <div>
            <h3 className="text-sm font-semibold">Scorecard Display</h3>
            <p className="text-xs text-muted-foreground">How innings scores are shown. Display only — runs and wickets are always stored separately and never changed by this.</p>
          </div>
          {msg && <p className="text-xs text-success">{msg}</p>}
          {err && <p className="text-xs text-danger">{err}</p>}
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">Workspace default {admin ? "" : "(admin only)"}</span>
            <Select value={wsFormat} disabled={!admin} onChange={(e) => void saveWorkspace(e.target.value)} className="max-w-xs">
              <option value="au">Australian — wickets/runs (e.g. 10/127)</option>
              <option value="en">English — runs/wickets (e.g. 127/10)</option>
            </Select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">My preference</span>
            <Select value={userFormat} className="max-w-xs"
              onChange={(e) => { const v = e.target.value; setUserFmt(v); setUserScoreFormat(v === "" ? null : (v as "au" | "en")); setMsg("Your display preference was updated."); }}>
              <option value="">Use the workspace default ({example(wsFormat)})</option>
              <option value="au">Australian — wickets/runs (e.g. 10/127)</option>
              <option value="en">English — runs/wickets (e.g. 127/10)</option>
            </Select>
            <span className="text-xs text-muted-foreground">Applies to your view across the app; it does not change anyone else's display or any stored data.</span>
          </label>
        </CardContent></Card>
      </div>
    </AppShell>
  );
}
