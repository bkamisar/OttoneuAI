# shared.js valuation-math audit — 2026-07-19 (Fable line-by-line)

First adversarial line-by-line review of the valuation core (`shared.js`, all
1,255 lines) against MODEL.md's documented intent. Complements the 2026-07-04
league-wide OUTPUT audit (which checked results; this checked the math).
Findings ranked by importance. Nothing here is urgent; none invalidates
current values during the season.

## Verified CLEAN (checked, correct — don't re-litigate)

- **SGP marginal math**: rate stats (OBP/SLG, ERA/WHIP/HR9) scale by
  `pa/avgPA` / `ip/avgIP` — the correct marginal-team-impact approximation;
  counting-stat asymmetry (hitter HR/R pro-rate the replacement, pitcher SO
  raw) matches MODEL.md invariant 3 exactly.
- **SLG aggregation is AB-weighted** (`ab×slg / totAB`), OBP PA-weighted —
  the classic ratio-stat aggregation mistake is NOT present.
- **IP cap honored at both sites** (valuation `ipBudget`, blendStats
  `remIP`), per invariant 2.
- **Pool conservation**: $1 × entries + `distributable` distributed by
  positive-SGP share; starter-only split with all-positive rate denominators
  matches MODEL.md §2.5.
- **Positional offsets are year-consistent** (computed inside each
  `calculateAllValues` pass on the cloned rosters) and pool-neutral.
- **Y2→Y1 fallback machinery** and the year-specific two-way `projP`
  forwarding (`yearProjP`) work as documented, including the deliberate
  "explicit null ≠ fall back to Y0" distinction.
- **Invariant 8 honored**: `computeFABaselines` reads the
  ROSTERED_IDS/NAMES snapshot, so attaching year projections to FA pools
  cannot redefine the roster.

## Findings

### 1. Two-way FREE AGENTS lose their pitching value entirely (live code path)
`calculateAllValues`' rostered loop adds two-way pitching SGP (projP block,
~line 1041). The `extraPlayers` loop (~1089–1108) has NO such block — and
fa.html + bid.html pass the FA pool as `extraPlayers`, so this is the live FA
path. Worse: `getFreeAgents` concatenates hitting+pitching projection files;
a two-way FA appears in both with the same fgId, and the extras loop's
`if (valueMap[key]) return` keeps only the hitting entry — the pitching half
is silently dropped. Impact today: zero (no two-way FA of consequence);
impact the day an Ohtani-type hits waivers: badly wrong FA value.
**Fix when convenient**: mirror the projP block in the extras loop, or merge
same-fgId FA entries in `getFreeAgents`.

### 2. Seasonal degeneracy — offseason and September behavior is undefined
Two independent mechanisms quietly change the model at season edges,
neither documented in MODEL.md:
- **Oct 1 – Mar 27**: `rosProrationFactor()` returns 0 after Sept 28, so the
  Y0 `ipBudget` floors at `IP_MAX × 0.1 = 150 IP` and Y0 runs on whatever
  stale RoS files remain — Y0 values are garbage all offseason (Y1/Y2 remain
  fine). Pre–Mar 28 returns 1.0, so spring is correct.
- **September**: `FA_MIN_PA = 100` exceeds max possible RoS PA (~63 by
  mid-Sept), so the FA hitter cohort empties and the baseline silently flips
  to the weakest-roster-quartile fallback — replacement level jumps
  mid-month. `FA_MIN_IP = 30` does the same for arms slightly later.
**Recommendation**: prorate the floors (e.g. `max(15, 100 × rosProration
Factor())`) and/or have index.html surface "offseason mode — Y0 unreliable,
use dynasty view". At minimum it is now documented (MODEL.md §8).

### 3. MODEL.md overstates the $1 floor
"Every rostered player gets a $1 floor" — in code, rostered players with NO
matched projection (`noProj`) get no value entry at all (no floor, and they
are excluded from the `reserved` count, which is what keeps the pool
conserved). Internally consistent; the DOC was wrong. Corrected in §2.5.

### 4. Hygiene (fix opportunistically, none affect outputs)
- `parsePitchingProjections` emits `h: n('h')` but `PITCHING_PROJ_COLS` has
  no `h` key (FanGraphs pitching export has no hits column) → pitcher
  `proj.h` is always 0 and unused. Dead field; delete or wire it if WHIP
  reconstruction is ever wanted.
- `valProxy` (FA cohort ranking: `ip×(1/ERA + SO/1000)`, no WHIP) and
  `selectPitchers._value` (`ip×(1/ERA + 1/WHIP + SO/100)`) are different
  proxies. Each is used consistently; the divergence is just confusing.
- Two-way pitching SGP is only added when positive (`if (pitSGP > 0)`) — a
  two-way player is never docked for bad pitching. Defensible; now
  documented rather than implicit.
- Y1/Y2 attach is name-only within type (no IDs in those files — known);
  duplicate names within a type resolve last-parsed-wins with no warning.
  Risk accepted; a console warning on dup names would cost three lines.

## Suggested implementation queue (all mechanical, Sonnet-sized)
1. Extras-loop projP block + same-fgId FA merge (finding 1).
2. Prorated FA cohort floors + offseason banner (finding 2).
3. Optional: dup-name console warning (finding 4d).
