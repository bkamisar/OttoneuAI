# Hot FA Board — Design Spec

**Date:** 2026-07-19
**Status:** Approved design, pre-implementation
**League context:** 12-team Ottoneu 4×4 — hitting R / HR / OBP / SLG, pitching K / HR9 / ERA / WHIP.

## Problem

The suite is entirely forward-looking (Steamer rest-of-season projections). Nothing
captures *what a player actually did over the last N days*, so there's no way to spot
free agents who are hot right now. This adds a recent-form scouting board.

## Goal & signal

Primary signal is **raw recent production** (option A): show the actual last-7/15/30-day
line in the categories that score in this league, ranked so hot players float up. Layered
on top is a lightweight **breakout flag** (option C): a badge when a player's recent rate
clearly beats his Steamer projection, hinting the model may be underrating him.

This is a *scouting* tool, not a second valuation engine. It does not compute SGP dollars
or replacement level.

## Data source

MLB StatsAPI `byDateRange` stats endpoint (first-party, free, already used by
`briefing.gs`). One call per window (7/15/30) per group (hitting/pitching) = 6 calls/day,
end date = yesterday (last completed slate), start = end − (window − 1).

**Open risk (first implementation task):** confirm `byDateRange` returns *all* qualified
players with pagination (`limit`/`offset`), not a truncated leaderboard. Spike this before
building on it. If it truncates and can't paginate, fall back to per-team stat pulls.

## Architecture

| Piece | File | Role |
|---|---|---|
| Daily snapshot | `scripts/hotstats.gs` (new) | Apps Script; pulls byDateRange, writes `data/hot.json`. Namespaced `hs*`, reuses `pushFile` + `GITHUB_TOKEN`. |
| Pure logic | `hotboard.js` (new) | `computeHotScore`, `classifyRole`, `meetsThreshold`, `breakoutBadge`, name-matching. Loaded by `hot.html` and `test.html`. Kept out of `shared.js` (valuation engine stays focused). |
| Page | `hot.html` (new) | UI. Loads `hot.json` + `roster.csv` + projection CSVs; uses `hotboard.js`. |
| Nav | all pages | Add "Hot FAs" link to the shared nav block in each page. |
| Tests | `test.html` | New unit tests for scoring, thresholds, role classification, FA matching. |

The data file carries **every player with recent activity** (not pre-filtered to FAs), so
FA-vs-rostered and below-threshold filtering both happen client-side and stay toggleable.

## `data/hot.json` shape

```json
{
  "generatedAt": "…ISO…",
  "ranges": { "7": {"start":"…","end":"…"}, "15": {…}, "30": {…} },
  "hitters": [
    { "id": 12345, "name": "…", "team": "…",
      "w": { "7": {"pa":…,"hr":…,"r":…,"obp":…,"slg":…} | null, "15": {…}, "30": {…} } }
  ],
  "pitchers": [
    { "id": 67890, "name": "…", "team": "…",
      "w": { "7": {"g":…,"gs":…,"ip":…,"so":…,"era":…,"whip":…,"hr9":…,"bf":…,"role":"SP|RP"} | null, "15": {…}, "30": {…} } }
  ]
}
```

- `role` is stored **per window** — a pitcher can be SP over 30d but all-relief over 7d.
- `role` = `SP` if starts make up at least half of appearances that window, else `RP`.
- A window is `null` when the player had no activity in it. Player appears in the array if
  active in *any* window (30-day set is the superset).
- Decimals rounded (obp/slg 3 places, era/whip/hr9 2) to keep file size to a few hundred KB.

## Page: `hot.html`

Visual language matches `fa.html` (nav, cards, tables, `pos-btn` pills).

**Controls bar**
- Window toggle `[7] [15] [30]`, default **15**.
- "Free agents only" toggle, **on** by default. Off → all players shown, rostered ones
  tagged with a chip.
- Position filter pills for hitters (All / C / 1B / 2B / 3B / SS / OF / Util). *Approximate*
  — from StatsAPI primary position, since FAs carry no Ottoneu eligibility. Documented
  limitation.
- "Show marginal (below threshold)" toggle, **off** by default.
- Name search box.

**Tables** (every column click-to-sort; default sort = HotScore desc)
- **Hitters:** Name · Pos · Team · PA · HR · R · OBP · SLG · OPS · 🔥 · HotScore
- **Pitchers → two sub-tables, SP and RP:** Name · Team · GS(SP)/G(RP) · IP · K · ERA ·
  WHIP · HR9 · K% · 🔥 · HotScore

## Metrics (plain language)

Everything below is driven by **tunable constants** (see table) so we can adjust after
seeing real output.

### Sample gates — "have we seen enough to trust it?"
A player only shows in the default view if he cleared a minimum workload for the window.
Below-gate players are still in the data and appear when "Show marginal" is on.

- Hitters: **≥ 12 / 25 / 45 PA** for 7 / 15 / 30 days.
- Starters: **≥ 1 / 2 / 3 starts**.
- Relievers: **≥ 3 / 5 / 8 appearances** — a usage gate, not innings/batters, because a
  dominant reliever faces *fewer* batters by design (three up, three down), so any
  innings- or batters-faced floor would filter out exactly the hot arms we want.

### HotScore — the default ranking number
The board needs one number to sort by. HotScore is an **equal-weight z-score across the
four scoring categories**, computed *within each pool separately* (hitters, SP, RP) for the
selected window.

- A z-score just means "how many standard deviations above or below the group average this
  player is in that stat." +1.0 ≈ clearly above the pack; 0 ≈ average; negative ≈ below.
- Hitters: `z(OBP) + z(SLG) + z(HR) + z(R)`.
- Pitchers: `z(K) − z(HR9) − z(ERA) − z(WHIP)` (the last three are subtracted because lower
  is better).
- Each category counts exactly ¼. ERA is a full partner, not demoted. Because four stats
  are averaged, no single category's small-sample fluke (a reliever's one-HR ERA spike, a
  hitter's one-week OPS mirage) can dominate the default order — but every column still
  sorts on its own if you want to rank by just one.
- The group mean and standard deviation are computed from the qualified pool itself each
  window (self-relative, like the SGP denominators). No external league constants.

**Worked example (hitters, 15-day window).** Say among qualified hitters the average line
is OBP .330 / SLG .430 / 4 HR / 11 R, with standard deviations of .040 / .080 / 2.5 HR /
4 R. A free agent posts .400 / .620 / 7 HR / 15 R over 15 days:
- z(OBP) = (.400 − .330)/.040 = **+1.75**
- z(SLG) = (.620 − .430)/.080 = **+2.38**
- z(HR)  = (7 − 4)/2.5 = **+1.20**
- z(R)   = (15 − 11)/4 = **+1.00**
- HotScore = 1.75 + 2.38 + 1.20 + 1.00 = **+6.33** → near the top of the board.

A guy hitting for empty average (.360 OBP, .410 SLG, 0 HR, 6 R) lands near 0 — "fine,
not hot." That's the intended behavior.

### 🔥 Breakout badge — "recent form beats the projection"
Match the player to his Steamer row by normalized name. Badge if recent rate clearly tops
projected:
- Hitters: recent OPS − projected OPS **≥ 0.075**.
- Pitchers: recent ERA **and** WHIP both below projected, **or** recent K% ≥ projected K% + 3 pts.
- No projection match → no badge (can't compute; a chunk of fringe/rookie FAs won't have one).

## Name matching

StatsAPI names → `roster.csv` (FA vs rostered) and → projection CSVs (breakout badge) by
normalized name, reusing the `bfNorm_`-style normalization from `briefing.gs` (lowercase,
strip accents/periods). Team abbreviation is the collision guard for duplicate names.
Accepted limitation: a small number of players may go unmatched (accents, Jr./Sr.,
nicknames) — they still show with raw stats, just without FA-tagging or a badge if the
match fails.

## Tunable knobs

| Knob | Default | Where |
|---|---|---|
| Windows | 7, 15, 30 | `hotstats.gs` + `hot.html` |
| Default window | 15 | `hot.html` |
| Hitter min PA (per window) | 12 / 25 / 45 | `hotboard.js` |
| SP min starts | 1 / 2 / 3 | `hotboard.js` |
| RP min appearances | 3 / 5 / 8 | `hotboard.js` |
| HotScore weights | equal (¼ each) | `hotboard.js` |
| Breakout: hitter OPS gap | 0.075 | `hotboard.js` |
| Breakout: pitcher K% gap | +3 pts | `hotboard.js` |

## Testing

Add to the existing `test.html` suite (keep it green):
- HotScore z-score math on a fixed pool (known mean/stdev → expected score).
- `meetsThreshold` at/over/under each gate for hitters, SP, RP.
- `classifyRole` (SP/RP by starts share).
- FA matching against a small roster fixture, including a collision guarded by team.
- `breakoutBadge` true/false around each threshold.

Pure functions live in `hotboard.js` precisely so they're unit-testable without the DOM.

## Phasing

**Phase 1 (this spec):** `hotstats.gs` + `data/hot.json` + `hotboard.js` + `hot.html` +
nav links + tests. Ship, confirm it's useful.

**Phase 2 (separate spec later):**
- `fa.html`: small "L15 form" indicator/column reading `hot.json`.
- Briefing: "Hot on the wire" card — top FA hitter/SP/RP by 15-day HotScore.

## Non-goals

- No SGP dollars / replacement-level valuation on this board.
- No stolen-base or saves/holds columns (not scored in this league).
- No exact Ottoneu position eligibility for FAs (StatsAPI primary position is the approximation).
