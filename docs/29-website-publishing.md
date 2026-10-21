# 29. Website Publishing Architecture

**Deliverable 29 of 38** · §28

Automatic statistics publishing to a workspace's website — initial target: RMCC's
existing **Lovable-built** site. The public site must keep working **even when the
OneStats Windows server is offline**, and must never expose draft, disputed, private or
restricted records.

## 29.1 Decoupled publication edge

```mermaid
flowchart LR
  subgraph Server["OneStats server (may be offline)"]
    Approve["Approved reports/records<br/>(Verified only)"] --> Snap["Publication snapshot builder"]
  end
  Snap --> Cache[("Publication cache<br/>(hosted, read-only)")]
  Cache --> API["Read-only publishing API"]
  API --> Site["RMCC Lovable website"]
  API --> Portal["Mobile portal (deliverable 30)"]
  Snap -. "offline queue + retry" .-> Cache
```

- OneStats builds **publication snapshots** of approved content and pushes them to a
  **hosted publication cache** that serves a **read-only API**. The website reads the
  cache, so it is independent of the OneStats server's uptime (§28).
- **Offline queue + retry:** if the cache is unreachable, publishes queue and retry; the
  previously published snapshot stays live meanwhile.

## 29.2 What may be published

- **Only Verified / Verified Partial (within scope) and explicitly approved** statistics,
  records, honour boards and heritage items.
- **Never:** draft, disputed, private or restricted records; protected junior/DOB data
  (deliverables 24, 33).
- Publishing is **permission-gated** (approve/withdraw = Admin/Reviewer, deliverable 7)
  and **audited**; corrections and withdrawals are first-class (a withdrawal republishes a
  snapshot without the item).

## 29.3 RMCC Lovable website integration `[UNVERIFIED]`

- **Do not assume** the existing website has a compatible API (§28). Phase 15 begins by
  **confirming** what the Lovable site can consume (static JSON feed, embedded widget,
  REST). `[DECISION D17]`.
- **Preserve the existing website design** where practical — OneStats supplies **data +
  branding tokens**, the site owns presentation. Options: (a) published JSON the site
  fetches; (b) embeddable read-only widgets; (c) pre-rendered pages. Decide against the
  real site.

## 29.4 Sync & logging

- **Automatic and manual** synchronisation; publication logs record what was published,
  when, by whom, and the snapshot version.
- Each workspace has independent publishing settings and its own snapshot (isolation,
  deliverable 6).
- The read-only API is **read-only** and exposes only approved data; it never proxies the
  administrative database (§29/§33).

## 29.4a Player profiles

Approved, verified **player profiles** (+ branding and optional sponsor) publish through the
same snapshot/cache as statistics — design in
[12a-player-profile-and-badges.md](12a-player-profile-and-badges.md) §12a.6. Junior/DOB and
unverified data are excluded; a profile re-publishes through the normal approval flow after
a stat change or an identity merge (deliverable 12 §12.3a).

## 29.5 Phasing

Specified now; built in **Phase 15** (Website Publishing & Synchronisation), after the
stats/reporting engine (Phase 12) and records (Phase 13).
