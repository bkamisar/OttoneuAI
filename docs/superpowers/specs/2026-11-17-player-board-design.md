# Player Board — design (short)

**Why:** hunting trade targets on other teams. The engine already computes next-season value,
six-season dynasty value, surplus and hold horizon for every player, but no page shows them
league-wide: fa.html is free agents only, roster.html is one team, targets.html buries values
inside trade suggestions.

**Goal:** one sortable, filterable table of every rostered player in the league.
**Non-goals:** free agents (fa.html has them); trade suggestions (targets.html); editing anything.
**Anti-goal:** a slow page. It must not run the trade search on load.

## Approaches
1. **New page `players.html`** — same data loading as fa.html, flat table. **Picked**: clean,
   fast, one job.
2. "All teams" mode on roster.html — rejected: that page is built around one team's lineup.
3. Tab on targets.html — rejected: heaviest page, runs the trade search on load.

## Design
- Loads like fa.html: `autoLoadFromRepo()`, match roster to projections (Y0 + Y1/Y2),
  `calculateDynastyValues(allRosters, weights)` with the stored dynasty weights.
- One row per rostered player. Columns: Player, Team, Pos, Age, Salary, 2027 $ (projectedValue),
  Dynasty $, Surplus, Hold (seasons), Trade value (`offseasonTradeValue`, partner view with the
  2026 market blend, as the trade finder uses), FV (prospects only).
- Every column header sorts (click again to reverse). Sorting by Team is the "grouping".
- Filter bar (fa.html style): name search, Team, Position, Hitters/Pitchers, Prospects only,
  Hide my team.
- My team's rows tinted, so they stand out when shown.
- Linked from the nav bar on the other pages and the Data Hub.

## Left to the builder
Column formatting, default sort (Surplus, high to low), age source (ages.csv via `ageInSeason`,
prospect-list age fallback), a test in test.html or audit/test for any new pure helper.
