# Decision Audit v2 — Counted Production + Offseason Cap Moves

**Date:** 2026-10-12 · **Builds on:** `2026-10-11-decision-audit-design.md` (v1, shipped)

## Why

Two v1 flaws the user found:

1. **Results credited everything a player did in MLB while rostered**, and trades assumed the
   giving team would have kept playing the players it sent. The Donovan trade credited Bureau
   +5 standings points; he counted for 3 games for them (3 G, 15 AB, 2 R, 0 HR).
2. **Offseason cuts were treated like in-season cuts.** Oct → auction cuts are cap moves to get
   under $400 before the auction. Bryce Krispies cut Yordan Alvarez at $52 (Jan 31 2026) and
   re-bought him at the Mar 5 auction for $51 — v1 called it −17 points; it was a $1 reset.

User priority: **factual over hypothetical** — grade what actually happened.

## Data

New: `data/teamproduction.csv` (2,221 rows, from `/1648/teamproduction/<team>/<year>`),
columns `season,teamId,group,ottoneuId,player,acquired,G,c1..c5`:
- `H`: c1..c5 = AB, R, HR, OBP, SLG — **lineup-only stats that counted for that team that season**.
- `P`: c1..c5 = IP (baseball notation), K, HR9, ERA, WHIP.
- `PBENCH`: one row per team-season, the bench pitching line (did not count).
One row per player per team per season (all stints on that team that season combined).

Rows carry Ottoneu player ids, so counted lines need **no name matching**. MLB daily stats
(v1 cache) stay for: PA estimation, hot tags, and nothing else.

## Part 1 — Grade on counted production

**Counted line** `C(player, team, season)`: from teamproduction. Hitter PA isn't on the page:
`PA ≈ AB × (player's season PA/AB from MLB daily stats)`, fallback ×1.12. Missing row = the
player counted nothing for that team (a real zero).

**Value of a counted line:** same as v1 `lineValue` (SGP vs. the season's FA-cohort
replacement, final-standings denominators, league $/SGP rate), applied to the counted line.

**Result grades (replace v1 results for every move):**
- Add / swap-in / auction buy: `value(C(player, team)) − salary × fracHeld`.
- In-season cut: `salary × 0.5 × fracRemaining − value(C(player, whoever had him next))`
  (0 if nobody rostered him again that season).
- Trade side: `Σ_in [value(C(p, me)) − salary × fracHeld] − Σ_out [value(C(p, them)) − salary × fracHeld_them]`
  — "who actually got more out of it". The two sides are mirror images by construction.
- Swap: add part + cut part.
- Players with multiple stints on the same team in one season: their combined line is
  used and the move is flagged `combinedStints`.

**Process grades:** unchanged (2026, projection-based). **Luck** = result − process.

**Standings: roto points contributed (replaces the v1 counterfactual).**
- `ptsContributed(player, team, season)` = team's final points − its points with that player's
  counted line removed (counting stats subtracted; OBP/SLG/ERA/WHIP/HR9 recomputed over the
  remaining PA/IP; team PA/IP = sum of its counted lines). No replacement is invented.
  Ottoneu's 1,250-IP rule still applies.
- Move standings impact = Σ in `ptsContributed` − Σ out `ptsContributed(p, them)` for trades;
  Σ in for adds/auction; − ptsContributed elsewhere for cuts.
- **Title-deciding:** a move whose net points ≥ that team's margin over (or gap to) the
  neighbouring place, for 1st or the top-3 line. Replaces v1 `decisive` + `fragile`.
- Removed from v1: FA-replacement counterfactual, bench robustness check, joint-cuts replay.

## Part 2 — Offseason cap moves

**Offseason window** for season S: Oct 1 (S−1) → that season's auction day (earliest
`auction` move of S). Moves in it get `phase: 'offseason'`; others `phase: 'in-season'`.

- **Salary reset:** offseason cut + the same team buys the same player at S's auction →
  one move, kind `reset`, graded `old salary − new salary`, no production effect.
- **Other offseason cuts:** `full salary freed − value(C(player, whoever had him in S))`.
- **Offseason trades:** graded as Part 1 trades; the move also records `capDelta` (net salary
  change for this team).
- **Winter cap summary** per team per season: cap freed by cuts (excluding resets), reset
  savings, net trade salary, auction spend, auction return (Σ auction buys' results).

## Outputs

`audit.json` moves gain `phase`, `capDelta`, `combinedStints`, `ptsContributed` (replaces
`standings`), `titleDeciding` (replaces `decisive`/`fragile`); new top-level `winters`
`{season: {teamId: {freed, resetSavings, tradeSalary, auctionSpend, auctionReturn}}}`.

**audit.html:** patterns split by phase (offseason vs in-season); standings section shows
points contributed; new "Your winters" table; "decisive" chip → "title-deciding".
**review.html:** title cards from `titleDeciding`; cut-that-haunts excludes resets;
new "Winter of the Year" card (best auction return net of cap freed). Commentary redrafted.

## Testing

Unit tests (`node --test audit/test/*.test.js`): teamproduction parsing (IP notation, PBENCH);
PA estimate; counted-line value; trade side mirror; cut credited to the next owner's counted
line; reset detection (Yordan fixture) and non-reset offseason cut; offseason window from the
auction date; ptsContributed on a toy league incl. the 1,250-IP rule; title-deciding margins.
Output checks on `data/audit.json`: the 2026-05-13 Donovan trade gives Bureau ~0 pts
contributed; the 2026-01-31 Yordan cut is a `reset` worth +$1.

## Out of scope

Lineup-day modelling, re-fetching teamproduction automatically (manual refresh like
transactions), changes to process grades.
