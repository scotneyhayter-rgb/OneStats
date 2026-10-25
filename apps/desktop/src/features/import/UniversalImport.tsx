/**
 * Universal import (Phase 8) — bring matches in from CSV, Excel, JSON or XML through the shared
 * adapter pipeline. Pick a file → the server detects the format (overridable) → Preview (nothing
 * persists) → Import. Imported matches enter the normal draft/approval flow; nothing is auto-approved.
 */
import { FileSpreadsheet, Upload } from "lucide-react";
import { useState } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Select } from "../../components/ui/select";
import { api, ApiError, type GenericImportResult } from "../../lib/api";
import { useManage } from "../manage/_shared";

type Candidate = { format_id: string; display_name: string; confidence: number };

function _readText(file: File): Promise<string> {
  if (typeof file.text === "function") return file.text();
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result ?? ""));
    r.onerror = () => reject(r.error ?? new Error("read failed"));
    r.readAsText(file);
  });
}

function _readBytes(file: File): Promise<ArrayBuffer> {
  if (typeof file.arrayBuffer === "function") return file.arrayBuffer();
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result as ArrayBuffer);
    r.onerror = () => reject(r.error ?? new Error("read failed"));
    r.readAsArrayBuffer(file);
  });
}

/** Read a file as text (CSV/JSON/XML) or, for a binary workbook, as base64 for the request body. */
async function readFile(file: File): Promise<{ content?: string; content_base64?: string }> {
  const isBinary = /\.(xlsx|xlsm)$/i.test(file.name);
  if (!isBinary) return { content: await _readText(file) };
  const bytes = new Uint8Array(await _readBytes(file));
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return { content_base64: btoa(binary) };
}

export function UniversalImport() {
  const { workspaceId } = useManage();
  const [payload, setPayload] = useState<{ content?: string; content_base64?: string } | null>(null);
  const [fileName, setFileName] = useState("");
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [formatId, setFormatId] = useState("");
  const [preview, setPreview] = useState<GenericImportResult | null>(null);
  const [result, setResult] = useState<GenericImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => { setPreview(null); setResult(null); setError(null); };

  const onFile = async (file: File | null) => {
    if (!file || !workspaceId) return;
    reset(); setCandidates([]); setFormatId("");
    setBusy(true);
    try {
      const body = await readFile(file);
      setPayload(body); setFileName(file.name);
      const det = await api.importDetect(workspaceId, { ...body, filename: file.name });
      setCandidates(det.candidates);
      setFormatId(det.candidates[0]?.format_id ?? "");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not read or detect the file.");
    } finally { setBusy(false); }
  };

  const run = async (commit: boolean) => {
    if (!workspaceId || !payload) return;
    setBusy(true); setError(null);
    try {
      const out = await api.importGeneric(workspaceId, { ...payload, filename: fileName, format_id: formatId || undefined, commit });
      if (commit) setResult(out); else setPreview(out);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Import failed.");
    } finally { setBusy(false); }
  };

  return (
    <Card><CardContent className="flex flex-col gap-4">
      <div>
        <h3 className="text-sm font-semibold">Other formats — CSV, Excel, JSON, XML</h3>
        <p className="text-xs text-muted-foreground">One row/record per match (date, teams, competition, grade, venue, result, format, round). Imported matches are created as drafts for review.</p>
      </div>

      <label className="flex w-fit cursor-pointer items-center gap-2 rounded-[var(--radius-app)] border border-dashed border-border px-3 py-2 text-sm hover:bg-muted">
        <Upload className="h-4 w-4" aria-hidden />
        {fileName || "Choose a file (.csv, .xlsx, .json, .xml)"}
        <input type="file" accept=".csv,.xlsx,.xlsm,.json,.xml" className="hidden"
          onChange={(e) => void onFile(e.target.files?.[0] ?? null)} />
      </label>

      {error && <p className="text-xs text-danger">{error}</p>}

      {candidates.length > 0 && (
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs">Detected format
            <Select value={formatId} disabled={busy} onChange={(e) => { setFormatId(e.target.value); reset(); }} className="w-64">
              {candidates.map((c) => (
                <option key={c.format_id} value={c.format_id}>{c.display_name} ({Math.round(c.confidence * 100)}%)</option>
              ))}
            </Select>
          </label>
          <Button size="sm" variant="outline" disabled={busy || !formatId} onClick={() => void run(false)}>
            <FileSpreadsheet className="h-4 w-4" aria-hidden /> Preview
          </Button>
          <Button size="sm" disabled={busy || !preview} onClick={() => void run(true)}>Import</Button>
        </div>
      )}

      {candidates.length === 0 && fileName && !busy && (
        <p className="text-xs text-warning">No adapter recognised this file. Check it is a supported match-summary export.</p>
      )}

      {preview && !result && (
        <div className="rounded-[var(--radius-app)] border border-border bg-muted/30 p-3 text-sm">
          <div className="mb-1 font-medium">Preview — nothing imported yet</div>
          <div className="flex flex-wrap gap-2 text-xs">
            {Object.entries(preview.counts).map(([k, v]) => <Badge key={k} variant="outline">{k}: {v}</Badge>)}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">Click <strong>Import</strong> to bring these in as draft matches.</p>
        </div>
      )}

      {result && (
        <div className="rounded-[var(--radius-app)] border border-success/40 bg-success/5 p-3 text-sm">
          <div className="mb-1 font-medium text-success">Imported from {result.display_name}</div>
          <div className="flex flex-wrap gap-2 text-xs">
            {Object.entries(result.created ?? {}).filter(([, v]) => v > 0).map(([k, v]) => <Badge key={k} variant="success">created {k}: {v}</Badge>)}
            {Object.entries(result.matched ?? {}).filter(([, v]) => v > 0).map(([k, v]) => <Badge key={k} variant="muted">matched {k}: {v}</Badge>)}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">Matches are drafts — review and approve them before they count towards official statistics.</p>
        </div>
      )}
    </CardContent></Card>
  );
}
