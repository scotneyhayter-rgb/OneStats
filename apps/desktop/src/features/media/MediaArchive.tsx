/**
 * OneStats Media Archive (Phase 11) — Club Management → Media Archive.
 *
 * Preserve original scorecard images, photographs and documents at original quality, with provenance,
 * copyright and publication controls; curate a Club Heritage Collection; and check archive integrity.
 * Storage is internal by default; external references and (optional, capability-detected) OneVault are
 * shown when available. Built to be usable by non-technical volunteers: guided uploads, clear previews,
 * plain-language actions. All data is read from the backend; nothing is fabricated.
 */
import { CheckCircle2, HardDrive, Image as ImageIcon, Landmark, ShieldCheck, Smartphone, Upload } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AppShell } from "../../components/layout/AppShell";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Select } from "../../components/ui/select";
import {
  api,
  ApiError,
  type HeritageCollection,
  type HeritageItem,
  type MediaAsset,
  type MediaProviderInfo,
  type MediaVerifyReport,
  type UploadSession,
} from "../../lib/api";
import { NoWorkspace, useManage } from "../manage/_shared";

type Tab = "library" | "heritage" | "integrity";

const KINDS = ["document", "scorecard", "photograph", "scan", "logo", "other"];

export function MediaArchive() {
  const { workspaceId } = useManage();
  const [tab, setTab] = useState<Tab>("library");
  const [assets, setAssets] = useState<MediaAsset[]>([]);
  const [providers, setProviders] = useState<MediaProviderInfo[]>([]);
  const [collections, setCollections] = useState<HeritageCollection[]>([]);
  const [verify, setVerify] = useState<MediaVerifyReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const loadFor = useCallback(async (which: Tab) => {
    if (!workspaceId) return;
    try {
      if (which === "library") {
        const [a, p] = await Promise.all([api.mediaAssets(workspaceId), api.mediaProviders(workspaceId)]);
        setAssets(a);
        setProviders(p);
      } else if (which === "heritage") {
        setCollections(await api.mediaHeritageCollections(workspaceId));
      } else if (which === "integrity") {
        const [p] = await Promise.all([api.mediaProviders(workspaceId)]);
        setProviders(p);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not load the Media Archive.");
    }
  }, [workspaceId]);
  useEffect(() => {
    void loadFor(tab);
  }, [loadFor, tab]);

  if (!workspaceId) return <NoWorkspace />;

  const act = async (fn: () => Promise<unknown>, msg: string) => {
    setBusy(true);
    setError(null);
    setFlash(null);
    try {
      await fn();
      setFlash(msg);
      await loadFor(tab);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  };

  const upload = async (file: File, kind: string, title: string) => {
    setBusy(true);
    setError(null);
    setFlash(null);
    try {
      const r = await api.mediaUpload(workspaceId, file, kind, title || undefined);
      setFlash(r.duplicate_of ? "Uploaded — identical content already exists in the archive." : "Media uploaded.");
      await loadFor("library");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Upload failed.");
    } finally {
      setBusy(false);
    }
  };

  const runVerify = () =>
    act(async () => { setVerify(await api.mediaVerify(workspaceId)); }, "Integrity check complete.");

  const tabBtn = (key: Tab, label: string, icon: React.ReactNode) => (
    <button type="button" onClick={() => setTab(key)}
      className={`flex items-center gap-1.5 rounded-[var(--radius-app)] border px-3 py-1.5 text-sm ${
        tab === key ? "border-brand bg-brand/10 font-medium text-brand" : "border-border text-muted-foreground"}`}>
      {icon}{label}
    </button>
  );

  return (
    <AppShell title="Media Archive" subtitle="Preserve original images and documents at original quality">
      <div className="mx-auto flex max-w-5xl flex-col gap-4">
        {error && <p className="rounded-[var(--radius-app)] border border-danger/40 bg-danger/5 px-3 py-2 text-sm text-danger">{error}</p>}
        {flash && <p className="rounded-[var(--radius-app)] border border-success/40 bg-success/5 px-3 py-2 text-sm text-success">{flash}</p>}

        <div className="flex flex-wrap items-center gap-2">
          {tabBtn("library", "Library", <ImageIcon className="h-4 w-4" aria-hidden />)}
          {tabBtn("heritage", "Heritage Collection", <Landmark className="h-4 w-4" aria-hidden />)}
          {tabBtn("integrity", "Storage & Integrity", <ShieldCheck className="h-4 w-4" aria-hidden />)}
        </div>

        {tab === "library" && (
          <>
            <Card><CardContent className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Upload original media</h3>
              <p className="text-xs text-muted-foreground">
                Originals (JPEG, PNG, TIFF, PDF) are preserved at original quality; a thumbnail is generated
                separately. Record copyright before marking anything for publication.
              </p>
              <UploadForm busy={busy} onUpload={upload} />
            </CardContent></Card>

            <MobileUploadCard workspaceId={workspaceId} />

            <Card><CardContent className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Media library ({assets.length})</h3>
              {assets.length === 0 && <p className="text-xs text-muted-foreground">No media yet. Upload a scorecard image, photograph or document above.</p>}
              {assets.map((a) => (
                <AssetRow key={a.id} workspaceId={workspaceId} asset={a} busy={busy}
                  onUpdate={(body) => act(() => api.mediaUpdateAsset(workspaceId, a.id, body), "Media updated.")} />
              ))}
            </CardContent></Card>
          </>
        )}

        {tab === "heritage" && (
          <Card><CardContent className="flex flex-col gap-3">
            <h3 className="text-sm font-semibold">Club Heritage Collection ({collections.length})</h3>
            <p className="text-xs text-muted-foreground">
              A curated set of significant items for optional future website publication — permission-controlled,
              never published by default.
            </p>
            {collections.map((c) => (
              <HeritageCollectionRow key={c.id} workspaceId={workspaceId} collection={c} assets={assets} busy={busy}
                onChanged={() => void loadFor("heritage")} />
            ))}
            <CreateCollection busy={busy} onCreate={(name) => act(() => api.mediaCreateCollection(workspaceId, { name }), "Collection created.")} />
          </CardContent></Card>
        )}

        {tab === "integrity" && (
          <>
            <Card><CardContent className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Storage providers</h3>
              {providers.map((p) => (
                <div key={p.name} className="flex flex-wrap items-center gap-2 text-sm">
                  <HardDrive className="h-4 w-4 text-muted-foreground" aria-hidden />
                  <span className="font-medium capitalize">{p.name}</span>
                  <Badge variant={p.available ? "success" : "muted"}>{p.available ? "available" : "unavailable"}</Badge>
                  {p.default && <Badge variant="brand">default</Badge>}
                  <span className="text-xs text-muted-foreground">{p.note}</span>
                </div>
              ))}
            </CardContent></Card>
            <Card><CardContent className="flex flex-col gap-3">
              <h3 className="text-sm font-semibold">Archive integrity</h3>
              <p className="text-xs text-muted-foreground">
                Checks every stored original for missing files and checksum mismatches (corruption detection).
              </p>
              <Button size="sm" className="self-start" disabled={busy} onClick={() => void runVerify()}>
                <CheckCircle2 className="h-4 w-4" aria-hidden /> Verify archive
              </Button>
              {verify && (
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 text-sm">
                  <Stat label="Total" n={verify.total} />
                  <Stat label="Verified OK" n={verify.verified_ok} />
                  <Stat label="Missing" n={verify.missing.length} warn={verify.missing.length > 0} />
                  <Stat label="Checksum fail" n={verify.mismatch.length} warn={verify.mismatch.length > 0} />
                </div>
              )}
            </CardContent></Card>
          </>
        )}
      </div>
    </AppShell>
  );
}

function Stat({ label, n, warn }: { label: string; n: number; warn?: boolean }) {
  return (
    <div className="rounded-[var(--radius-app)] border border-border p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`text-xl font-semibold tabular-nums ${warn ? "text-danger" : ""}`}>{n}</div>
    </div>
  );
}

function UploadForm({ busy, onUpload }: { busy: boolean; onUpload: (f: File, kind: string, title: string) => void }) {
  const [kind, setKind] = useState("photograph");
  const [title, setTitle] = useState("");
  return (
    <div className="flex flex-wrap items-end gap-2 text-xs">
      <label className="flex flex-col gap-1">
        <span className="text-muted-foreground">Kind</span>
        <Select value={kind} onChange={(e) => setKind(e.target.value)} className="w-40">
          {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
        </Select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-muted-foreground">Title (optional)</span>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. 1891 team photo"
          className="w-56 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1" />
      </label>
      <label className={`flex items-center gap-1.5 rounded-[var(--radius-app)] border border-brand bg-brand/10 px-3 py-1.5 text-sm text-brand ${busy ? "opacity-50" : "cursor-pointer"}`}>
        <Upload className="h-4 w-4" aria-hidden /> Choose file to upload
        <input type="file" accept="image/*,application/pdf" className="hidden" disabled={busy}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(f, kind, title); e.target.value = ""; }} />
      </label>
    </div>
  );
}

function AssetRow({ workspaceId, asset, busy, onUpdate }: {
  workspaceId: string; asset: MediaAsset; busy: boolean; onUpdate: (body: Record<string, unknown>) => void;
}) {
  const [thumb, setThumb] = useState<string | null>(null);
  const [copyright, setCopyright] = useState(asset.copyright_status ?? "");
  useEffect(() => {
    let revoked = false;
    if (asset.thumbnail_ref && asset.storage_provider === "internal") {
      api.mediaThumbnailObjectUrl(workspaceId, asset.id).then((u) => { if (!revoked) setThumb(u); }).catch(() => {});
    }
    return () => { revoked = true; };
  }, [workspaceId, asset.id, asset.thumbnail_ref, asset.storage_provider]);

  return (
    <div className="flex flex-wrap items-center gap-3 border-t border-border pt-2 text-sm first:border-0">
      {thumb
        ? <img src={thumb} alt={asset.title ?? "media"} className="h-12 w-12 rounded object-cover" />
        : <div className="flex h-12 w-12 items-center justify-center rounded bg-muted/40 text-muted-foreground"><ImageIcon className="h-5 w-5" aria-hidden /></div>}
      <div className="flex flex-col">
        <span className="font-medium">{asset.title || asset.original_filename || "Untitled"}</span>
        <span className="text-xs text-muted-foreground">
          {asset.kind} · {asset.storage_provider}{asset.file_bytes ? ` · ${Math.round(asset.file_bytes / 1024)} KB` : ""}
        </span>
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-2">
        {asset.junior_protected && <Badge variant="warning">junior</Badge>}
        {asset.sensitive && <Badge variant="warning">sensitive</Badge>}
        <Badge variant={asset.publication_eligible ? "success" : "muted"}>
          {asset.publication_eligible ? "publishable" : asset.visibility}
        </Badge>
        <input value={copyright} onChange={(e) => setCopyright(e.target.value)} placeholder="copyright"
          className="w-28 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1 text-xs" />
        <Button size="sm" variant="outline" disabled={busy}
          onClick={() => onUpdate({ copyright_status: copyright || null })}>Save</Button>
        {!asset.publication_eligible ? (
          <Button size="sm" disabled={busy || !copyright || asset.junior_protected || asset.sensitive}
            onClick={() => onUpdate({ visibility: "publishable", publication_eligible: true, copyright_status: copyright })}>
            Mark publishable
          </Button>
        ) : (
          <Button size="sm" variant="outline" disabled={busy}
            onClick={() => onUpdate({ visibility: "workspace", publication_eligible: false })}>Unpublish</Button>
        )}
        <Button size="sm" variant="outline" disabled={busy}
          onClick={() => onUpdate({ junior_protected: !asset.junior_protected })}>
          {asset.junior_protected ? "Unmark junior" : "Mark junior"}
        </Button>
      </div>
    </div>
  );
}

function CreateCollection({ busy, onCreate }: { busy: boolean; onCreate: (name: string) => void }) {
  const [name, setName] = useState("");
  return (
    <form className="flex flex-wrap items-end gap-2 border-t border-border pt-3 text-xs"
      onSubmit={(e) => { e.preventDefault(); if (name.trim()) { onCreate(name.trim()); setName(""); } }}>
      <label className="flex flex-col gap-1">
        <span className="text-muted-foreground">New collection name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. RMCC Heritage"
          className="w-56 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1" />
      </label>
      <Button size="sm" type="submit" disabled={busy || !name.trim()}>Create collection</Button>
    </form>
  );
}

function HeritageCollectionRow({ workspaceId, collection, assets, busy, onChanged }: {
  workspaceId: string; collection: HeritageCollection; assets: MediaAsset[]; busy: boolean; onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<HeritageItem[]>([]);
  const [assetId, setAssetId] = useState("");
  const [significance, setSignificance] = useState("");

  const load = useCallback(async () => {
    setItems(await api.mediaCollectionItems(workspaceId, collection.id));
  }, [workspaceId, collection.id]);
  useEffect(() => { if (open) void load(); }, [open, load]);

  const add = async () => {
    await api.mediaAddHeritageItem(workspaceId, collection.id,
      { media_asset_id: assetId || null, significance: significance || null });
    setSignificance("");
    setAssetId("");
    await load();
    onChanged();
  };

  return (
    <div className="flex flex-col gap-2 border-t border-border pt-2 first:border-0">
      <div className="flex items-center gap-2 text-sm">
        <span className="font-medium">{collection.name}</span>
        <Badge variant="muted">{collection.items} item{collection.items === 1 ? "" : "s"}</Badge>
        <Button size="sm" variant="outline" className="ml-auto" onClick={() => setOpen(!open)}>
          {open ? "Close" : "Open"}
        </Button>
      </div>
      {open && (
        <div className="flex flex-col gap-2 rounded-[var(--radius-app)] border border-border bg-muted/20 p-2 text-xs">
          {items.map((it) => (
            <div key={it.id} className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{it.title || "Item"}</span>
              {it.significance && <span className="text-muted-foreground">{it.significance}</span>}
              {it.publication_eligible && <Badge variant="success">publishable</Badge>}
            </div>
          ))}
          <div className="flex flex-wrap items-end gap-2 border-t border-border pt-2">
            <label className="flex flex-col gap-1">
              <span className="text-muted-foreground">Media</span>
              <Select value={assetId} onChange={(e) => setAssetId(e.target.value)} className="w-48">
                <option value="">(choose a media item)</option>
                {assets.map((a) => <option key={a.id} value={a.id}>{a.title || a.original_filename || a.id.slice(0, 8)}</option>)}
              </Select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-muted-foreground">Historical significance</span>
              <input value={significance} onChange={(e) => setSignificance(e.target.value)}
                placeholder="e.g. Earliest known RMCC photograph"
                className="w-64 rounded-[var(--radius-app)] border border-border bg-background px-2 py-1" />
            </label>
            <Button size="sm" disabled={busy} onClick={() => void add()}>Add to collection</Button>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Mobile upload pairing (deliverable 20a). An authenticated admin starts a short-lived, scoped pairing
 * session; the phone uses the one-time token (shown once here) to upload media over the LAN. The token is
 * never stored or shown again after this; sessions are revocable and expire. Uploaded files land in the
 * media review queue (unassigned) — nothing is auto-published.
 */
function MobileUploadCard({ workspaceId }: { workspaceId: string }) {
  const [sessions, setSessions] = useState<UploadSession[]>([]);
  const [created, setCreated] = useState<UploadSession | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setSessions(await api.mobileUploadSessions(workspaceId)); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not load pairing sessions."); }
  }, [workspaceId]);
  useEffect(() => { void load(); }, [load]);

  const start = async () => {
    setBusy(true); setError(null);
    try { setCreated(await api.mobileUploadCreate(workspaceId, { ttl_minutes: 30 })); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not start pairing."); }
    finally { setBusy(false); }
  };
  const revoke = async (id: string) => {
    setBusy(true); setError(null);
    try { await api.mobileUploadRevoke(workspaceId, id); if (created?.id === id) setCreated(null); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Could not revoke."); }
    finally { setBusy(false); }
  };

  const active = sessions.filter((s) => s.active);

  return (
    <Card><CardContent className="flex flex-col gap-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <Smartphone className="h-4 w-4 text-brand" aria-hidden /> Upload from a phone
      </h3>
      <p className="text-xs text-muted-foreground">
        Start a secure, time-limited pairing session, then open the link on a phone connected to the same
        network to upload photos or PDFs straight into the media review queue. The one-time code is shown
        once and never stored.
      </p>
      {error && <p className="text-xs text-danger">{error}</p>}

      <div><Button size="sm" disabled={busy} onClick={() => void start()}>Start pairing session</Button></div>

      {created?.token && (
        <div className="flex flex-col gap-1 rounded-[var(--radius-app)] border border-brand/40 bg-brand/5 p-3 text-xs">
          <span className="font-medium text-brand">Pairing started — enter this on the phone now (shown once):</span>
          <span className="break-all">Upload path: <code>{created.upload_path}</code></span>
          <span className="break-all">One-time code: <code>{created.token}</code></span>
          <span className="text-muted-foreground">
            Open the path on the server's LAN address from the phone and supply the code as the
            <code> X-Upload-Token</code> header. Expires {created.expires_at ? new Date(created.expires_at).toLocaleString() : "soon"}.
          </span>
        </div>
      )}

      {active.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-xs font-medium">Active sessions</span>
          {active.map((s) => (
            <div key={s.id} className="flex flex-wrap items-center gap-2 text-xs">
              <Badge variant="success">active</Badge>
              <span className="text-muted-foreground">{s.upload_count} uploaded · expires {s.expires_at ? new Date(s.expires_at).toLocaleString() : "—"}</span>
              <Button size="sm" variant="outline" disabled={busy} className="ml-auto" onClick={() => void revoke(s.id)}>Revoke</Button>
            </div>
          ))}
        </div>
      )}
    </CardContent></Card>
  );
}
