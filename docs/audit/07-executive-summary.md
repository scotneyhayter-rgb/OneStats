# Audit Deliverable J — Executive Summary

Plain-English wrap-up of the OneStats ↔ CricketStatz audit. CricketStatz was used as the **trusted numerical
benchmark**, inspected live (read-only) with the user's authorisation; OneStats was compared from its code and
live database. Details are in docs/audit/00–06. **The headline: where OneStats has the same data, it reproduces
CricketStatz's numbers exactly — and it is already simpler and safer for everyday use.**

## 1. What CricketStatz does particularly well
- **Accurate, trusted numbers** — confirmed: our reconciliation matched it to the decimal (below).
- **Enormous report breadth** — ~230 reports, all driven by **one universal filter form** (a strong design).
- A suite of **~20 data-quality "linting" reports** that catch scorer errors.
- **Live, ball-by-ball scoring** from any device at the ground, and **per-batter dot balls**.

## 2. What OneStats already does better
- **Honesty by construction** — unknown is never treated as zero; incomplete figures are flagged as
  known-minimums; strike/economy use only recorded balls. CricketStatz shows raw numbers without this.
- **Safer data entry** — a draft→approved workflow, full audit log, reversible identity merges, and
  **real-time in-grid validation** (missing fielder, FOW gaps, batting-order and duplicate warnings caught
  *as you type*), where CricketStatz surfaces the same errors only later as reports and uses free-text name
  entry (the root of its duplicate-name ambiguity).
- **Automatic result/margin** (CricketStatz needs a manual "Calc"), **multi-fielder run-outs**, auto-derived
  **partnerships**, and **inline, identity-aware player creation**.
- **Richer captaincy and bowling-partnership** reporting, **per-club logos**, publishing with approval/privacy,
  and a **Historical Research Centre**.
- **New this audit** (all shipped): **opposition filtering**, **adjustable qualification**, **specific-ground
  filter + filter chips**, a **data-quality suite** (workspace and per-match), **Player Compare**,
  **season-vs-season compare**, and **Head-to-Head** — several of which *neither* app had before.

## 3. Where OneStats is currently weaker
- **Live ball-by-ball scoring at the ground** — the one genuine entry-capability gap (large to build).
- **Report discoverability** — the 79-report catalogue needs search / favourites / recent (breadth is fine).
- **Minor friction** — grade can't yet be picked without first choosing a competition; dot balls aren't
  recorded per batter.
- **Some report variants** CricketStatz has and OneStats doesn't yet: milestones *Achieved* / *Over-Time*,
  hat-tricks, catches in a season/match/innings, winning-margin / run-chase, debut reports, "On This Day".

## 4. What statistical errors were found
- **Calculation defects: zero.** A live numerical reconciliation (Deliverable E) of the top players — 19
  comparisons across batting and bowling — found **17 exact matches and 0 calculation errors**; batting
  average, bowling average and **economy** all agreed to the decimal with CricketStatz.
- **One real data-side defect: run-out fielder attribution was undercounted** — because OneStats was built
  from a *stale October export* that dropped the fielder on ~760 run-outs (and ~1,000 catches). OneStats was
  counting correctly; the data it was given was incomplete. **Fixed** with a fielder-refresh backfill (commit
  f0b3bff): re-import a fresher export and the real attributions apply, without overwriting manual fixes.
- The two remaining number differences (Taylor D batting, Cosgriff D bowling) are **stale-import source
  differences**, not errors — data you've added to CricketStatz since the export. A fresh re-import closes them.
- The data-quality scan surfaced **~3,481 scorer-data gaps** workspace-wide — overwhelmingly historical-import
  completeness (missing keepers/captains/fielders on old matches), not calculation errors; **0** duplicate
  batters/bowlers and **0** bowler-is-fielder mistakes (clean).

## 5. What improvements would make the greatest difference
1. **Close the stale-data gap**: take a fresh CricketStatz export and run the fielder backfill — fixes the
   run-out record (Hayter 13→18) and the catch/keeper gaps, with everything else already in agreement.
2. **Universal filtering**: opposition + adjustable qualification are **done**; finishing multi-grade/season and
   a single reusable FilterBar + saved presets completes the proposal.
3. **Report discoverability** (search/favourites) — unlocks the existing 79-report breadth.
4. **Decide on live scoring** — the main capability OneStats lacks; large, worth scoping separately.

## 6. What to implement first (recommended order)
1. **Rebuild & deploy** the 13 features already built and tested this audit (none are in the installed app yet).
2. **Fresh export + fielder backfill** to correct the run-out/catch data against the benchmark.
3. **Report discoverability** + finish the filter work (multi-grade/season, reusable FilterBar + presets).
4. Fill the **report gaps** that matter (milestones Achieved/Over-Time, hat-tricks, catch leaderboards,
   winning-margin/run-chase).
5. **Scope live ball-by-ball scoring** as a separate programme.

## Bottom line
OneStats is **not** a weaker CricketStatz — it is a more accurate-by-construction, safer, and more modern
platform that already matches the benchmark's numbers and now exceeds it on filtering, data-quality and
comparison tools. Its real gaps are **live scoring** and **report discoverability**, plus closing the one-off
**stale-import** data differences. Trust in CricketStatz's numbers is well-placed — and OneStats earns the same
trust, with better honesty about what is and isn't known.

*Deliverables: A (doc 01) · B/C (01 §2, 03) · D (02) · E (04) · F (05, 06) · G (new capabilities — shipped
this audit + doc 02 §3) · H (prioritised roadmap — doc 00) · I (implementation readiness — doc 00 Stage table)
· J (this).*
