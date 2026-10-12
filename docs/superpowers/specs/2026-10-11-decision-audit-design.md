# Decision Audit + League Year-in-Review — Design

**Date:** 2026-10-11 · **League:** Ottoneu 1648 (The Peacock League), 12 teams, 4x4 · **My team:** TeamID 10759

## Goal

One engine, two outputs:

1. **`audit.html` — coaching page (for me).** Grade every roster decision on *process*
   (good given what was known that day) and *result* (how it actually turned out), find
   patterns against the league baseline, show where I beat or lost to my own tools, and show
   which moves cost or won standings places.
2. **`review.html` — league year-in-review (for fun).** Screenshot-friendly cards with
   awards and stories for all 12 teams, with commentary written by Claude.

Success = I can name my two or three worst habits from the coaching page with sample sizes
behind them, and the review produces cards worth posting in the league chat.

## Non-goals

- No automated decision logging going forward beyond re-running the pipeline.
- No lineup tracking (data doesn't exist); handled as a stated approximation.
- No second implementation of the valuation model — `shared.js` is the only engine.

## Data sources (all first-party)

| Data | Source | Coverage | How it gets to disk |
|---|---|---|---|
| Transactions (add/cut/move/increase) | Ottoneu transactions pages | Mar 2024 → now | Claude runs a throttled read in the built-in browser and saves `data/transactions.csv` (Cloudflare blocks Node). Re-run on request. |
| Daily rosters (all teams) | git history of `data/roster.csv` | 2026-05-24 → now | already committed daily by Apps Script |
| Daily projections | git history of `data/proj_*.csv` | first projection commit → now | already committed daily |
| Daily standings (category totals) | git history of `data/standings.csv` | 2026 | already committed daily |
| Final standings 2024, 2025 | Ottoneu standings page | 2 pages | same browser read → `data/standings-final-<year>.csv` |
| Actual player stats by day | MLB Stats API `byDateRange`, one day at a time, `playerPool=all` | 2024–2026 seasons | Node phase, cached one compact file per day |

**Why daily league-wide stats:** it is the smallest source that answers every question
(ownership-window production, L15 hot tags for any date, counterfactual standings).
~185 days × 2 groups × 3 seasons ≈ 1,100 small requests, stored stripped to the fields used
(~30 KB/day). Per-stint queries would be ~3,000 requests.

### `data/transactions.csv` columns
`date` (ISO, ET), `type` (add|cut|move|increase), `player`, `ottoneuId`, `teamId`, `team`,
`fromTeamId`, `fromTeam`, `salary` (int). Team names are display-only; **TeamID is identity**
(renames don't split a team).

### Player identity
- `ottoneuId` from transactions → `FG MajorLeagueID` via the union of all `roster.csv`
  snapshots (has both columns).
- Projections (`Name`, `Team`) and MLB stats (MLBAM id, full name, team) join by normalized
  name + team, falling back to name alone when unique.
- Every unmatched player is listed in the run report; none are silently dropped.

## Pipeline — `audit/` (Node, reuses `shared.js`)

`node audit/run.js [--force | --force=<phase>] [--season=2026]`

`shared.js` is loaded in a `vm` context with a small shim for `localStorage`/`window`/
`document` (13 references). No edits to `shared.js` beyond what the shim can't cover.

Phases, each checkpointed to `audit/cache/<phase>.json` (gitignored); completed phases are
skipped on relaunch; `--force` redoes all, `--force=<phase>` redoes that phase and later ones.

1. **snapshots** — read every commit of `roster.csv`, `proj_*.csv`, `standings.csv`
   (`git show <sha>:<path>`), index by date.
2. **moves** — parse `transactions.csv` into moves:
   - `add` / `cut` / `increase` → one move each. March `add`s before Opening Day = **auction**.
   - `move` rows sharing one timestamp → **one trade**, grouped by the two TeamIDs.
   - Cross-check against snapshot diffs (2026): any roster change with no matching
     transaction is reported as `unexplained`.
   - **Stints:** each (player, team) ownership interval, start/end dates, salary.
3. **stats** — fetch MLB daily stats per day (hitting + pitching), cache per day.
4. **grade** — process + result per move (below).
5. **standings** — counterfactual standings per move (below).
6. **tags** — auto-tags per move.
7. **write** — `data/audit.json` (all teams, all moves, grades, tags, standings deltas,
   patterns) and `data/review.json` (card numbers).

Run report printed at the end: counts per phase, unmatched players, unexplained roster
changes.

## Grading

All values in Ottoneu dollars from `shared.js`.

**Process** (only where a projection snapshot exists on or before the move date; otherwise
`null` and labelled "result only"):
- Add / auction buy: projected value that day − salary.
- Cut: −(projected value − salary) vs. the in-season cut cost (half salary dead money;
  end-of-season cuts are free).
- Trade: each side's surplus change (Σ in − Σ out of projected value − salary). *(Plan
  decision: the `tradefinder.js` marginal-value math was dropped as more complexity than
  the grade needs.)*
- Increase (keeper raise): projected next-year value − new salary.

**Result** (every move): actual production during the stint, valued in the same dollars,
− salary paid for the stint. Cuts: production the player went on to have elsewhere that
season = what was given up. A trade's result runs to season end or until the player leaves
the receiving team, whichever is first.

**Luck** = result − process (only when process exists).

## Counterfactual standings

For each move: start from actual final category totals for all 12 teams. Undo the move by
removing the player's actual stint production from the team and adding a replacement's over
the same playing time. Trades are undone on both sides at once. Recompute roto points and
ranks with `buildStandings` in `shared.js` (deterministic roto; `standingsim.js` is the
Monte Carlo simulator and isn't needed here).

**Replacement:**
- **Paired swaps:** an `add` and a `cut` by the same team within 30 minutes of each other are
  one decision (`swap`). Undoing it restores the cut player's actual production for that
  team over the same window (what he actually produced that season, prorated to the stint),
  not a generic replacement. Ambiguous pairings (several adds/cuts in the window) pair in
  timestamp order; leftovers stay unpaired. Swaps are graded as one move in all phases.
- **Everything else** (unpaired adds/cuts, trades): the `shared.js` FA baseline, prorated.
- **Not modelled:** which bench player would have started — lineups are unknown, so this would
  be a guess on a guess, and there are no roster snapshots before 2026-05-24.

**Robustness check on decisive moves:** re-run each decisive move with a tougher replacement —
the best player on that team's own roster at that position that day (2026, from roster
snapshots). If the decisive verdict flips, the move is marked `fragile` and its card says
"close call" instead of stating it as fact. 2024–25 decisive moves have no roster snapshots
to check against; they are marked `unchecked` and their cards say so.

Output per move: roto points Δ and rank Δ for every team affected. **Decisive** = undoing
the move changes 1st place or a podium spot.

Stated approximations (shown on both pages):
- **Bench:** stats count while rostered; counted PA/IP capped at regular-starter pace and
  the 1,500 IP team cap.
- **Interaction:** each move is evaluated alone against reality. "All my cuts undone" is a
  separate joint run, never a sum.

## Tags (auto, from as-of data)

- `hot` — top quartile L15 HotScore on the move date (from cached daily stats; all seasons).
- `prospect` — no MLB playing time and present in `prospects.csv`.
- `need` — move adds to the team's weakest category in that day's standings (2026 only).
- Trades: `deadline` (Aug), `salary-dump` (sheds ≥$10 net), `consolidation` (2-for-1+).
- `contender` / `rebuilder` — top/bottom third by standings rank that day (2026 only).

Manual tag overrides and notes live in **browser localStorage only** (never committed — the
site is public).

## `audit.html` — coaching page

1. **Headline:** my total process / result / luck, each vs. league median; standings
   places won/lost by my moves.
2. **Patterns:** average grade by move type and tag, mine vs. league. **Shown only when
   n ≥ 5**; n always displayed.
3. **Me vs. my tools** (process era only): "followed the model" = process ≥ 0, "overruled
   the model" = process < 0, using the suite's own valuation that day (what `bid.html` and
   the trade tools are built on). Scored by result. *(Plan decision: replaying `bid.html`'s
   inline page logic was dropped.)*
4. **Standings:** my costliest and most valuable moves in places/points; joint "all cuts
   undone".
5. **Every move:** sortable table, my team by default, toggle for league.

Follows the suite's look (`theme.css`, nav).

## `review.html` — league year-in-review

Phone-width, self-contained cards; no URLs or tool links on cards. Cards for the season
(default 2026):

- Decisive moves (title / podium swings)
- Trade of the year · Fleecing of the year
- Pickup of the year (value vs. salary)
- The cut that haunts
- Luckiest / unluckiest manager (result − process)
- Most active / most patient manager
- Auction: best and worst buy
- All-time (2024–2026): career trade record by manager, best and worst deal ever

**Commentary:** after a run, Claude reads `data/review.json` and writes one line per card
into `data/review-commentary.json`; the page renders it. Light ribbing, never mean, every
claim backed by the card's numbers. Missing commentary → card renders without it.

## Testing

- Node unit tests (`node --test audit/`) for: transaction parsing + trade grouping, stint
  building, TeamID identity across renames, process/result math on hand-built fixtures,
  counterfactual on a 3-team toy league, tag rules.
- `shared.js` shim smoke test: values for a known snapshot match what the live page shows
  (spot-check a few players).
- Real-data checks: the Aug 15 Trout trade groups into one 3-player trade; every 2026
  roster diff is explained or reported.

## Open risks

- Cloudflare rate-limits the transactions read (hit at page 29 of 110 on first try);
  mitigated by a slow pace and resuming. Never bypass the challenge.
- Name joins for projections/stats will miss some players; the run report makes the gap
  visible.
