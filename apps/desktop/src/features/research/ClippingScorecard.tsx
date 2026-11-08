/**
 * Create scorecard from clipping (Phase 10, Stage 10.17).
 *
 * Turns OCR'd / transcribed scorecard text into a DRAFT the researcher reviews before anything is saved.
 * The core guarantee: **no players are created and no scorecard is written until the researcher clicks
 * "Create draft scorecard".** Parsing and the suggested existing-player matches are entirely read-only,
 * so the researcher can link each name to the right existing player (avoiding duplicates) or correct a
 * spelling and create a new one. Figures read as unknown stay blank — never defaulted to zero.
 */
import { useCallback, useEffect, useState } from "react";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { api, ApiError, type ParsedBatter, type ParsedClipping } from "../../lib/api";

// Parser dismissal "kind" -> the scorecard's dismissal_type vocabulary. Anything not cleanly mappable is
// left unset (the descriptive text is still kept in the entry notes, so nothing is lost or invented).
const DISMISSAL_TYPE_MAP: Record<string, string> = {
  bowled: "bowled",
  caught: "caught",
  caught_and_bowled: "caught_and_bowled",
  lbw: "lbw",
  run_out: "run_out",
  stumped: "stumped",
  not_out: "not_out",
  hit_wicket: "hit_wicket",
  did_not_bat: "dnb",
};

type Choice =
  | { mode: "existing"; personId: string }
  | { mode: "new"; name: string }
  | { mode: "skip" };

function defaultChoice(b: ParsedBatter): Choice {
  const exact = b.candidates.find((c) => c.exact);
  if (exact) return { mode: "existing", personId: exact.person_id };
  return { mode: "new", name: b.name };
}

function describeDismissal(b: ParsedBatter): string {
  if (b.dismissal_text) return b.dismissal_text;
  if (b.dismissal_kind) return b.dismissal_kind.replace(/_/g, " ");
  return "—";
}

export function ClippingScorecard({
  workspaceId,
  initialText,
  onClose,
  onCreated,
}: {
  workspaceId: string;
  initialText: string;
  onClose: () => void;
  onCreated?: (matchId: string) => void;
}) {
  const [text, setText] = useState(initialText);
  const [parsed, setParsed] = useState<ParsedClipping | null>(null);
  const [choices, setChoices] = useState<Record<number, Choice>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdId, setCreatedId] = useState<string | null>(null);

  const parse = useCallback(async () => {
    setBusy(true);
    setError(null);
    setCreatedId(null);
    try {
      const res = await api.researchParseClipping(workspaceId, text);
      setParsed(res);
      setChoices(Object.fromEntries(res.batters.map((b) => [b.position, defaultChoice(b)])));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not parse the clipping.");
      setParsed(null);
    } finally {
      setBusy(false);
    }
  }, [workspaceId, text]);

  useEffect(() => {
    if (initialText.trim()) void parse();
    // Parse once on open with the supplied text; further parses are user-driven.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setChoice = (pos: number, c: Choice) => setChoices((prev) => ({ ...prev, [pos]: c }));

  const createDraft = async () => {
    if (!parsed) return;
    setBusy(true);
    setError(null);
    try {
      // 1) Resolve each included batter to a person_id — creating a new person ONLY where the researcher
      //    chose "create new". This is the first and only point at which anything is written.
      const resolved: { b: ParsedBatter; personId: string | null }[] = [];
      for (const b of parsed.batters) {
        const choice = choices[b.position] ?? { mode: "skip" as const };
        if (choice.mode === "skip") continue;
        if (choice.mode === "existing") {
          resolved.push({ b, personId: choice.personId });
        } else {
          const name = choice.name.trim();
          if (!name) continue;
          const person = await api.createPerson(workspaceId, { display_name: name, roles: ["player"] });
          resolved.push({ b, personId: String((person as { id: string }).id) });
        }
      }
      if (resolved.length === 0) {
        setError("Select at least one batter to include before creating the draft.");
        setBusy(false);
        return;
      }
      // 2) Start a draft reconstruction (an unapproved, canonical match — the normal research workflow).
      const match = await api.researchStartReconstruction(workspaceId, {
        notes: "Created from a scorecard clipping (draft — review and verify before approval).",
      });
      const matchId = String(match.id);
      // 3) One batting innings, then the reviewed batters in reading order.
      const innings = await api.createInnings(workspaceId, matchId, {
        inns_number: 1,
        status: "unknown",
        notes: "Batting from clipping.",
      });
      const inningsId = String((innings as { id: string }).id);
      let position = 0;
      for (const { b, personId } of resolved) {
        position += 1;
        const dismissalType = b.dismissal_kind ? DISMISSAL_TYPE_MAP[b.dismissal_kind] ?? null : null;
        await api.createBatting(workspaceId, inningsId, {
          person_id: personId,
          batting_position: position,
          runs: b.runs,            // null stays null — unknown, never zero
          balls_faced: b.balls,
          dismissal_type: dismissalType,
          notes: b.dismissal_text ? `Clipping: ${b.dismissal_text}` : null,
          evidence: "clipping",
        });
      }
      setCreatedId(matchId);
      onCreated?.(matchId);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not create the draft scorecard.");
    } finally {
      setBusy(false);
    }
  };

  const includedCount = parsed
    ? parsed.batters.filter((b) => (choices[b.position] ?? { mode: "skip" }).mode !== "skip").length
    : 0;

  return (
    <div className="flex flex-col gap-3 rounded-[var(--radius-app)] border border-brand/40 bg-brand/5 p-3">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold">Create scorecard from clipping</span>
        <Badge variant="muted">draft</Badge>
        <button type="button" className="ml-auto text-xs text-muted-foreground hover:text-foreground" onClick={onClose}>
          Close
        </button>
      </div>

      <p className="rounded bg-background/70 p-2 text-xs text-muted-foreground">
        Nothing is saved and <span className="font-medium text-foreground">no players are created</span> until you
        click <span className="font-medium text-foreground">Create draft scorecard</span>. Link each name to the right
        existing player to avoid duplicates, fix a spelling, or create a new player. Scores read as unknown are left
        blank — never set to zero.
      </p>

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        className="w-full rounded-[var(--radius-app)] border border-border bg-background p-2 text-xs font-mono"
        placeholder="Paste or correct the scorecard text, then click Parse"
      />
      <div className="flex items-center gap-2">
        <Button size="sm" variant="outline" disabled={busy || !text.trim()} onClick={() => void parse()}>
          Parse
        </Button>
        {parsed && (
          <span className="text-xs text-muted-foreground">
            {parsed.batters.length} batter{parsed.batters.length === 1 ? "" : "s"} found
            {parsed.bowlers.length > 0 ? ` · ${parsed.bowlers.length} bowling figure(s)` : ""}
          </span>
        )}
      </div>

      {createdId && (
        <p className="rounded bg-success/10 p-2 text-xs text-success">
          Draft scorecard created. Find it under Review &amp; Verify to add details, attach the source, and submit it
          for verification.
        </p>
      )}

      {parsed && !createdId && (
        <>
          {parsed.batters.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              No batting rows were recognised. Check the text above (names followed by a dismissal and score), then Parse again.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="text-left text-muted-foreground">
                    <th className="px-1 py-1 font-medium">#</th>
                    <th className="px-1 py-1 font-medium">Read as</th>
                    <th className="px-1 py-1 font-medium">Runs</th>
                    <th className="px-1 py-1 font-medium">Dismissal</th>
                    <th className="px-1 py-1 font-medium">Player</th>
                  </tr>
                </thead>
                <tbody>
                  {parsed.batters.map((b) => {
                    const choice = choices[b.position] ?? { mode: "skip" as const };
                    const selectValue =
                      choice.mode === "existing" ? choice.personId : choice.mode === "new" ? "__new__" : "__skip__";
                    return (
                      <tr key={b.position} className="border-t border-border/60 align-top">
                        <td className="px-1 py-1 text-muted-foreground">{b.position}</td>
                        <td className="px-1 py-1 font-medium">{b.name}</td>
                        <td className="px-1 py-1">{b.runs ?? <span className="text-muted-foreground">unknown</span>}</td>
                        <td className="px-1 py-1 text-muted-foreground">{describeDismissal(b)}</td>
                        <td className="px-1 py-1">
                          <select
                            value={selectValue}
                            disabled={busy}
                            onChange={(e) => {
                              const v = e.target.value;
                              if (v === "__new__") setChoice(b.position, { mode: "new", name: b.name });
                              else if (v === "__skip__") setChoice(b.position, { mode: "skip" });
                              else setChoice(b.position, { mode: "existing", personId: v });
                            }}
                            className="w-full rounded border border-border bg-background px-1 py-1"
                          >
                            {b.candidates.map((c) => (
                              <option key={c.person_id} value={c.person_id}>
                                {c.display_name}
                                {c.exact ? " (exact match)" : ""}
                              </option>
                            ))}
                            <option value="__new__">➕ Create new player…</option>
                            <option value="__skip__">Skip this row</option>
                          </select>
                          {choice.mode === "new" && (
                            <input
                              value={choice.name}
                              disabled={busy}
                              onChange={(e) => setChoice(b.position, { mode: "new", name: e.target.value })}
                              className="mt-1 w-full rounded border border-border bg-background px-1 py-1"
                              placeholder="New player name"
                            />
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {parsed.batters.length > 0 && (
            <div className="flex items-center gap-2">
              <Button size="sm" disabled={busy || includedCount === 0} onClick={() => void createDraft()}>
                Create draft scorecard
              </Button>
              <span className="text-xs text-muted-foreground">
                {includedCount} batter{includedCount === 1 ? "" : "s"} will be added
              </span>
            </div>
          )}
        </>
      )}

      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
