/**
 * Website Publishing (Phase 15) — hosting-neutral. Publish a report (or a player profile) to a permanent
 * public URL backed by a durable snapshot: serve it from the built-in public edge (preview / future
 * central service) or download the static files for existing website hosting (e.g. the RMCC site's
 * External URL field). Publish / unpublish / revoke, auto-staleness after approved-stat changes, refresh,
 * and club branding. Admin only.
 */
import { Copy, Download, RefreshCw, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { ConfirmDialog } from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { Select } from "../../components/ui/select";
import { api, ApiError, type GithubConnection, type Publication, type ReportCatalogue } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { canManage } from "../../lib/permissions";
import { useWorkspace } from "../../lib/workspace-context";

export function Publishing() {
  const { current } = useWorkspace();
  const { user } = useAuth();
  const admin = canManage(user, current);
  const [cat, setCat] = useState<ReportCatalogue | null>(null);
  const [pubs, setPubs] = useState<Publication[]>([]);
  const [reportId, setReportId] = useState("");
  const [title, setTitle] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [baseSaved, setBaseSaved] = useState<string | null>(null);
  const [gh, setGh] = useState<GithubConnection | null>(null);
  const [ghRepo, setGhRepo] = useState("");
  const [ghBranch, setGhBranch] = useState("main");
  const [ghToken, setGhToken] = useState("");
  const [ghBusy, setGhBusy] = useState(false);
  const [ghResult, setGhResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [toRemove, setToRemove] = useState<Publication | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!current) return;
    try {
      const [c, p, s, g] = await Promise.all([
        api.statsCatalogue(current.id), api.publicationsList(current.id),
        api.publicationSettingsGet(current.id), api.publicationGithubGet(current.id),
      ]);
      setCat(c); setPubs(p); setBaseUrl(s.public_base_url ?? ""); setBaseSaved(s.public_base_url ?? null);
      setGh(g); setGhRepo(g.repo ?? ""); setGhBranch(g.branch || "main");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load publishing.");
    }
  }, [current]);
  useEffect(() => { void load(); }, [load]);

  const reports = useMemo(() => (cat?.categories ?? []).flatMap((c) => c.reports), [cat]);

  const publish = useCallback(async () => {
    if (!current || !reportId) return;
    setError(null); setMsg(null);
    const r = reports.find((x) => x.id === reportId);
    try {
      await api.publicationCreate(current.id, { kind: "report", report_id: reportId, title: title.trim() || r?.name || reportId });
      setMsg("Published. A permanent public URL was created."); setTitle(""); setReportId("");
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Publish failed.");
    }
  }, [current, reportId, title, reports, load]);

  const act = useCallback(async (fn: () => Promise<unknown>, ok: string) => {
    setError(null); setMsg(null);
    try { await fn(); setMsg(ok); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Action failed."); }
  }, [load]);

  const copy = (text: string) => { try { void navigator.clipboard.writeText(text); setMsg("Copied."); } catch { /* clipboard unavailable */ } };

  const saveBase = useCallback(async () => {
    if (!current) return;
    await act(() => api.publicationSettingsSet(current.id, baseUrl.trim() || null), "Public site address saved.");
  }, [current, baseUrl, act]);

  const exportSite = useCallback(async () => {
    if (!current) return;
    try {
      const url = await api.publicationSiteZipUrl(current.id);
      const a = document.createElement("a");
      a.href = url; a.download = "onestats-public-site.zip"; a.click();
      URL.revokeObjectURL(url);
      setMsg("Whole-site .zip downloaded — unzip it and upload the contents to your host (e.g. GitHub Pages).");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Site export failed.");
    }
  }, [current]);

  const saveGithub = useCallback(async () => {
    if (!current) return;
    const body: { repo: string | null; branch: string; token?: string } = {
      repo: ghRepo.trim() || null, branch: ghBranch.trim() || "main",
    };
    if (ghToken) body.token = ghToken; // only send the token when the user typed one (blank keeps it)
    await act(async () => { const g = await api.publicationGithubSet(current.id, body); setGh(g); setGhToken(""); },
      "GitHub connection saved.");
  }, [current, ghRepo, ghBranch, ghToken, act]);

  const publishGithub = useCallback(async () => {
    if (!current) return;
    setError(null); setMsg(null); setGhResult(null); setGhBusy(true);
    try {
      const r = await api.publicationGithubPublish(current.id);
      const text = `Pushed ${r.files} file${r.files === 1 ? "" : "s"} to ${r.repo} (commit ${r.commit.slice(0, 7)}). `
        + (r.pages_url
          ? `Your site is live shortly at ${r.pages_url}`
          : "GitHub Pages isn't enabled on the repo yet — turn it on at Settings → Pages → Deploy from a branch → "
            + `${r.branch} → / (root). (Your token needs Pages: Read and write for OneStats to do that for you.)`);
      setGhResult({ ok: true, text });
      await load();
    } catch (e) {
      setGhResult({ ok: false, text: e instanceof ApiError ? e.message : "GitHub publish failed — check the repo and token." });
    } finally { setGhBusy(false); }
  }, [current, load]);

  const download = useCallback(async (p: Publication) => {
    if (!current) return;
    try {
      const { files } = await api.publicationExport(current.id, p.id);
      for (const [name, content] of Object.entries(files)) {
        const blob = new Blob([content], { type: name.endsWith(".json") ? "application/json" : "text/html" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob); a.download = name; a.click();
        URL.revokeObjectURL(a.href);
      }
      setMsg("Static files downloaded — upload these to your website host.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Export failed.");
    }
  }, [current]);

  if (!current) return <AppShell title="Website Publishing" subtitle="Select a workspace"><div /></AppShell>;
  if (!admin) return <AppShell title="Website Publishing" subtitle={current.name}><p className="text-sm text-muted-foreground">Publishing is available to workspace administrators.</p></AppShell>;

  const statusBadge = (s: string) => s === "published" ? <Badge variant="success">published</Badge>
    : s === "revoked" ? <Badge variant="danger">revoked</Badge> : <Badge variant="muted">unpublished</Badge>;

  return (
    <AppShell title="Website Publishing" subtitle={current.name}>
      <div className="mx-auto flex max-w-4xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}
        {msg && <p className="text-xs text-success">{msg}</p>}

        <Card><CardContent className="flex flex-wrap items-center gap-2">
          <div className="text-sm"><span className="font-medium">Public records portal</span>
            <span className="ml-2 text-xs text-muted-foreground">a mobile-first page listing everything you publish</span></div>
          <Button size="sm" variant="outline" className="ml-auto"
            onClick={() => window.open(api.publicPreviewUrl(`/api/v1/public/club/${current.id}`), "_blank")}>
            Open portal
          </Button>
        </CardContent></Card>

        <Card><CardContent className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold">Go live on the web</h3>
          <p className="text-xs text-muted-foreground">
            Export your whole public site as one bundle and upload it to a free static host such as GitHub Pages.
            It serves cached, approved-only snapshots — never your database — and stays live even when this
            computer is off. Set the address below once your site is up so each report shows its live link.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-1 flex-col gap-1 text-xs">Public site address
              <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://yourname.github.io/club-stats" />
            </label>
            <Button size="sm" variant="outline" onClick={() => void saveBase()}>Save address</Button>
            <Button size="sm" onClick={() => void exportSite()}><Download className="h-4 w-4" aria-hidden /> Export entire site (.zip)</Button>
          </div>
          <ol className="flex list-decimal flex-col gap-0.5 pl-5 text-xs text-muted-foreground">
            <li>Click <b>Export entire site</b> and unzip the download.</li>
            <li>Create a GitHub repository and upload everything, keeping the <code>r/</code> and <code>p/</code> folders and the <code>.nojekyll</code> file.</li>
            <li>In the repository: <b>Settings → Pages → Deploy from a branch → main → / (root)</b>.</li>
            <li>Your site goes live at <code>https://&lt;username&gt;.github.io/&lt;repo&gt;/</code> — paste that above and <b>Save address</b>.</li>
            <li>When stats change: <b>Refresh all</b>, export again, and re-upload.</li>
          </ol>
          {baseSaved && <p className="text-xs text-success">Public address set — live links appear below. Hosted at <code className="rounded bg-muted/40 px-1.5 py-0.5">{baseSaved}</code></p>}
        </CardContent></Card>

        <Card><CardContent className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold">Publish directly to GitHub</h3>
          <p className="text-xs text-muted-foreground">
            Connect a GitHub repository once, then publish your whole site with one click — OneStats commits
            the exported files straight to the repo as a single commit and GitHub Pages redeploys. Your token
            is stored on this computer only and is never shown again. Only approved, public data is pushed.
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-1 flex-col gap-1 text-xs">Repository (owner/name)
              <Input value={ghRepo} onChange={(e) => setGhRepo(e.target.value)} placeholder="scotneyhayter-rgb/rmcc-stats" />
            </label>
            <label className="flex w-24 flex-col gap-1 text-xs">Branch
              <Input value={ghBranch} onChange={(e) => setGhBranch(e.target.value)} placeholder="main" />
            </label>
          </div>
          <label className="flex flex-col gap-1 text-xs">Access token (fine-grained, Contents: Read and write)
            <Input type="password" value={ghToken} onChange={(e) => setGhToken(e.target.value)}
              placeholder={gh?.token_set ? "•••••••• saved — leave blank to keep" : "github_pat_…"} />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => void saveGithub()}>Save connection</Button>
            <Button size="sm" disabled={ghBusy || !gh?.token_set || !gh?.repo} onClick={() => void publishGithub()}>
              <Upload className="h-4 w-4" aria-hidden /> {ghBusy ? "Publishing…" : "Publish to GitHub now"}
            </Button>
            {gh?.token_set && <span className="text-xs text-success">Connected{gh.repo ? ` to ${gh.repo}` : ""}</span>}
          </div>
          {ghBusy && <p className="text-xs text-muted-foreground">Pushing your whole site to GitHub… this can take a moment for a large club.</p>}
          {ghResult && (
            <p className={`rounded-[var(--radius-app)] border px-3 py-2 text-xs ${ghResult.ok ? "border-success/40 bg-success/5 text-success" : "border-danger/40 bg-danger/5 text-danger"}`}>
              {ghResult.text}
            </p>
          )}
          <p className="text-[11px] text-muted-foreground">
            Create a token at GitHub → Settings → Developer settings → Fine-grained tokens, scoped to just
            this one repository with <b>Contents: Read and write</b> (add <b>Pages: Read and write</b> to let
            OneStats turn Pages on for you). The token never leaves this computer except to push to your repo.
          </p>
        </CardContent></Card>

        <Card><CardContent className="flex flex-col gap-3">
          <h3 className="text-sm font-semibold">Publish a report</h3>
          <p className="text-xs text-muted-foreground">Creates a permanent public URL backed by a snapshot (approved data only, club-branded). It keeps serving the last published snapshot even while this computer is offline.</p>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-xs">Report
              <Select value={reportId} onChange={(e) => setReportId(e.target.value)} className="w-64">
                <option value="">— choose a report —</option>
                {(cat?.categories ?? []).map((c) => (
                  <optgroup key={c.category} label={c.category}>
                    {c.reports.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                  </optgroup>
                ))}
              </Select>
            </label>
            <label className="flex flex-1 flex-col gap-1 text-xs">Public title (optional)
              <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Defaults to the report name" />
            </label>
            <Button size="sm" disabled={!reportId} onClick={() => void publish()}>Publish</Button>
          </div>
        </CardContent></Card>

        <Card><CardContent className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">Published reports &amp; profiles</h3>
            <Button size="sm" variant="outline" className="ml-auto" onClick={() => void act(() => api.publicationRefreshAll(current.id), "All published snapshots refreshed.")}>
              <RefreshCw className="h-4 w-4" aria-hidden /> Refresh all
            </Button>
          </div>
          {pubs.length === 0 ? <p className="text-xs text-muted-foreground">Nothing published yet.</p> :
            <div className="flex flex-col divide-y divide-border">
              {pubs.map((p) => (
                <div key={p.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                  <span className="font-medium">{p.title}</span>
                  <Badge variant="muted">{p.kind === "player_profile" ? "profile" : "report"}</Badge>
                  {statusBadge(p.status)}
                  {p.stale && <Badge variant="warning">needs refresh</Badge>}
                  {p.public_url
                    ? <code className="truncate rounded bg-muted/40 px-1.5 py-0.5 text-xs text-muted-foreground">{p.public_url}</code>
                    : <span className="text-xs italic text-muted-foreground">Not publicly hosted yet — download it and upload to your website</span>}
                  <div className="ml-auto flex flex-wrap gap-1">
                    {p.public_url && <Button size="sm" variant="ghost" onClick={() => copy(p.public_url!)} aria-label="Copy public URL" title="Copy the public web address"><Copy className="h-4 w-4" aria-hidden /></Button>}
                    {p.public_path && <Button size="sm" variant="ghost" onClick={() => window.open(api.publicPreviewUrl(p.public_path!), "_blank")}>Preview</Button>}
                    <Button size="sm" variant="ghost" onClick={() => void download(p)} aria-label="Download for your website" title="Download the HTML + JSON to upload to your website, then paste that page's address into the site's Stats URL / link field"><Download className="h-4 w-4" aria-hidden /> Download</Button>
                    {p.status === "published"
                      ? <Button size="sm" variant="ghost" onClick={() => void act(() => api.publicationRefresh(current.id, p.id), "Snapshot refreshed.")}>Refresh</Button>
                      : <Button size="sm" variant="ghost" onClick={() => void act(() => api.publicationSetStatus(current.id, p.id, "published"), "Re-published.")}>Publish</Button>}
                    {p.status === "published" && <Button size="sm" variant="ghost" onClick={() => void act(() => api.publicationSetStatus(current.id, p.id, "unpublished"), "Unpublished.")}>Unpublish</Button>}
                    {p.status !== "revoked" && <Button size="sm" variant="ghost" onClick={() => void act(() => api.publicationSetStatus(current.id, p.id, "revoked"), "Revoked — the URL no longer resolves.")}>Revoke</Button>}
                    <Button size="sm" variant="ghost" className="text-danger hover:text-danger" onClick={() => setToRemove(p)} aria-label={`Remove ${p.title}`} title="Permanently remove this published item"><Trash2 className="h-4 w-4" aria-hidden /> Remove</Button>
                  </div>
                </div>
              ))}
            </div>}
          <p className="text-xs text-muted-foreground">To show a profile or report on your club website, use <b>Download</b> to get a self-contained HTML + JSON page, upload it to your site's hosting, then paste that page's web address into the site's link / &ldquo;Stats URL&rdquo; field. A copyable public URL only appears here once a public hosting address is configured; the Preview link opens the page on this computer only. Public serving never exposes the database.</p>
        </CardContent></Card>
      </div>

      <ConfirmDialog
        open={toRemove !== null}
        title="Remove this published item?"
        description={`“${toRemove?.title ?? ""}” will be permanently removed from publishing and its public URL will stop resolving.${toRemove?.public_url ? " If your site is on a static host (e.g. GitHub Pages), re-publish or re-export to drop the file there too." : ""} This cannot be undone.`}
        confirmLabel="Remove"
        danger
        onCancel={() => setToRemove(null)}
        onConfirm={() => { const p = toRemove; setToRemove(null); if (p) void act(() => api.publicationDelete(current.id, p.id), "Removed from publishing."); }}
      />
    </AppShell>
  );
}
