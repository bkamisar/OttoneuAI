# Player Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a `players.html` page listing every rostered player with value, dynasty value, surplus, hold, trade value and FV, sortable and filterable.

**Architecture:** pure row/filter/sort helpers in a new `playerboard.js` (testable in the audit vm, like tradefinder.js); `players.html` loads data the way fa.html does, computes `calculateDynastyValues`, and renders with the helpers.

**Tech Stack:** plain browser JS (ES5 style like the other pages), shared.js engine, node:test via audit/lib/engine.js.

**Spec:** docs/superpowers/specs/2026-11-17-player-board-design.md

## Global Constraints
- Rostered players only (team !== 'Free Agent'); no trade search on load.
- Trade value = `offseasonTradeValue(dynastyValue, dynastyValue - dynastySurplus, null, market)` with market `{actual, sample, proj: projectedValue}` from `marketValueFor(p)` (partner view, same as the trade finder).
- Default sort: Surplus, high to low.
- `node --test audit/test/*.test.js` stays green.

## Review Focus
- Multi-position players ("2b/of") must match a single-position filter ("2B"), case-insensitive.
- Players with no projection (deep prospects) have null 2027 $: they sort last, never break the table.
- Nulls sort last in both directions.
- Name search ignores accents/case ("ramirez" finds "Ramírez").
- Missing ages.csv or prospect list: Age/FV blank, page still renders.

---

### Task 1: playerboard.js helpers

**Files:**
- Create: `playerboard.js`
- Test: `audit/test/playerboard.test.js` (loads shared.js via `loadEngine()`, then `e.get(playerboard.js)`)

**Interfaces — Produces:**
- `pbBuildRows(teams, dynMap, opts) -> Row[]` — `teams`: `{teamName: player[]}`; `opts`: `{myTeam, ages: {name: birthDate}, prospects: {name: {fv}}, season, market: function(p) -> {actual, sample}|null}`.
  Row: `{key, name, team, mine, pos, type, age, salary, y0, dyn, surplus, hold, tv, fv, prospect}` (`prospect` = has FV).
- `pbFilter(rows, f) -> Row[]` — `f`: `{search, team, pos, type, prospectsOnly, hideMine}`; empty/falsey fields don't filter.
- `pbSort(rows, key, dir) -> Row[]` — new array; `dir` 'asc'|'desc'; nulls last either way; strings by `localeCompare`.

- [ ] Step 1: tests — `pbBuildRows` skips 'Free Agent', sets `mine`, computes `tv` with and without market; `pbFilter` pos '2B' matches '2b/of', search 'ramirez' matches 'Pedro Ramírez', hideMine, prospectsOnly; `pbSort` desc by surplus with a null last, asc by name.
- [ ] Step 2: run, expect FAIL (functions undefined).
- [ ] Step 3: implement in `playerboard.js`.
- [ ] Step 4: `node --test audit/test/*.test.js` all pass.
- [ ] Step 5: commit.

### Task 2: players.html + navigation

**Files:**
- Create: `players.html` (styles/filter bar copied from fa.html)
- Modify: nav block in every page that has one (add `<a href="players.html">Player Board</a>` after Trade Targets); Data Hub link list in `index.html`.

**Interfaces — Consumes:** Task 1 helpers; shared.js `autoLoadFromRepo, loadData, matchPlayers, attachYearProjections, getFreeAgents, calculateDynastyValues, marketValueFor, offseasonTradeValue, ageInSeason, prospectSeason`.

- [ ] Step 1: page: load like fa.html (lines 156-254), build `teams`, dynasty map, ages (`ottoneu_ages`), prospects (`ottoneu_prospects` by name), market (`marketValueFor`); render filter bar (search, Team, Pos, H/P, Prospects only, Hide my team), sortable headers, count line; tint `mine` rows.
- [ ] Step 2: verify: extract inline script and `node --check`; run the helpers on real data in the audit harness and print the top 10 by surplus (sanity: Neto, Kurtz-type cheap starters near the top).
- [ ] Step 3: nav links; commit.
