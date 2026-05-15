# Projection Value Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four valuation accuracy issues: remove double regression on Y0 BatX projections, update league mean constants from historical data, derive the H/P dollar split dynamically from SGP totals, and add RoS proration columns to FA and trade tools.

**Architecture:** All valuation logic lives in `shared.js` (Tasks 1–3). Display changes for proration live in `fa.html` and `trade.html` (Task 4). Tasks are independent — each can be verified in isolation by opening `test.html` in a browser.

**Tech Stack:** Vanilla JS, HTML. No build step. Tests run in browser via `test.html`.

---

## Files Modified

- `shared.js` — constants, `parseHittingProjections`, `parsePitchingProjections`, `calculateAllValues`, new `rosProrationFactor()`
- `fa.html` — `renderHitterRow`, `renderPitcherRow`, column header arrays
- `trade.html` — `buildVexCol` column headers, per-player row, totals row
- `test.html` — update existing projection parser tests, add SGP split test, add proration test

---

## Task 1: Remove Double Regression on Y0 Projections

**Files:**
- Modify: `shared.js:11-16` (constants block)
- Modify: `shared.js:170-226` (projection parsers — code simplification after constant change)
- Modify: `test.html:100-122` (existing tests now assert unregressed values — verify they pass)

BatX RoS projections are already regression-adjusted using real stats-to-date. The code's internal shrinkage is a second layer on top of BatX's own, systematically deflating rate stats. Setting both constants to 0 collapses the regression formula to a pass-through.

Note: `LG_MEAN` becomes unused after this change. It is kept in place (updated in Task 2) for potential future use with Y1/Y2 projections.

- [ ] **Step 1: Update regression constants in `shared.js`**

In `shared.js`, replace lines 11–17:

```js
// Regression-toward-the-mean constants for rate stats.
// REGRESS_PA / REGRESS_IP sets how many "league-average PA/IP" we add as a prior.
// Higher = stronger pull; values calibrated so full-time players (~600 PA / 180 IP)
// see ~25% shrinkage while fringe players see 60-80% shrinkage.
const REGRESS_PA = 200;
const REGRESS_IP = 100;
const LG_MEAN = { OBP: 0.318, SLG: 0.414, ERA: 4.25, WHIP: 1.28, HR9: 1.15 };
```

With:

```js
// BatX RoS projections are already regression-adjusted from real stats-to-date.
// Setting these to 0 passes rate stats through unchanged (no double regression).
// LG_MEAN is retained for future Y1/Y2 regression use; see Task 2 for calibrated values.
const REGRESS_PA = 0;
const REGRESS_IP = 0;
const LG_MEAN = { OBP: 0.318, SLG: 0.414, ERA: 4.25, WHIP: 1.28, HR9: 1.15 };
```

- [ ] **Step 2: Open `test.html` in a browser and verify three tests now pass**

The following tests were written expecting unregressed values but were failing with `REGRESS_PA = 200`. With the constant now 0 they should pass:

- `parseHittingProjections: OBP` — expects `0.400` (was ~0.380 with regression)
- `parsePitchingProjections: derived ER` — expects `er ≈ 66.67` (200 IP × 3.00 ERA / 9)
- `parsePitchingProjections: derives HR/9 when column is zero` — expects `0.900` (was ~0.989)

Open `test.html` in a browser. All tests should show green. If any fail, recheck the constant edit.

- [ ] **Step 3: Commit**

```bash
git add shared.js
git commit -m "fix: remove double regression on Y0 projections — BatX already regressed"
```

---

## Task 2: Update LG_MEAN to League Historical Means

**Files:**
- Modify: `shared.js:17` (LG_MEAN constant)

`LG_MEAN` is used if regression is ever re-enabled for Y1/Y2 projections. It should reflect the mean of teams in this specific Ottoneu league (which roster only above-replacement talent), not the MLB population average. Two seasons of league history gives 24 team-seasons per category — a stable enough sample for rate stats.

- [ ] **Step 1: Collect historical standings data**

From your Ottoneu league, retrieve the final standings for both completed seasons. You need the end-of-season team totals for each of the 8 scoring categories: OBP, SLG, HR, R, ERA, WHIP, HR/9, SO. Ottoneu provides a standings page with these numbers per team.

Create a temporary file (or use the browser console) to compute the means. Open any browser console and paste:

```js
// Fill in your 24 team-season rows: [OBP, SLG, ERA, WHIP, HR9]
// (HR, R, SO are counting stats — not used in LG_MEAN rate regression)
const rows = [
  // Season 1 — 12 teams
  // [OBP, SLG, ERA, WHIP, HR9],
  // e.g. [0.335, 0.460, 3.85, 1.22, 1.05],
  // ... (paste all 12 teams from season 1)
  // Season 2 — 12 teams
  // ... (paste all 12 teams from season 2)
];
const avg = k => rows.reduce((s, r) => s + r[k], 0) / rows.length;
console.log({
  OBP:  avg(0).toFixed(3),
  SLG:  avg(1).toFixed(3),
  ERA:  avg(2).toFixed(2),
  WHIP: avg(3).toFixed(3),
  HR9:  avg(4).toFixed(2),
});
```

Copy the output — these are your calibrated `LG_MEAN` values.

- [ ] **Step 2: Update `LG_MEAN` in `shared.js`**

Replace the `LG_MEAN` line (currently line 17) with the computed values. Example (replace with your actual output):

```js
// Mean team rate stats across 2 completed Ottoneu league seasons (24 team-seasons).
// Only active when REGRESS_PA / REGRESS_IP > 0.
const LG_MEAN = { OBP: 0.XXX, SLG: 0.XXX, ERA: X.XX, WHIP: X.XXX, HR9: X.XX };
```

- [ ] **Step 3: Open `test.html` and confirm all tests still pass**

This change has no runtime effect (REGRESS = 0), so no tests should change behavior. All green.

- [ ] **Step 4: Commit**

```bash
git add shared.js
git commit -m "chore: update LG_MEAN to league historical means (2 seasons)"
```

---

## Task 3: SGP-Derived Hitting/Pitching Dollar Split

**Files:**
- Modify: `shared.js:9` (remove `HIT_POOL_SHARE` constant)
- Modify: `shared.js:618-624` (`calculateAllValues` — replace hardcoded split with dynamic ratio)
- Modify: `test.html` — add one test verifying the split reflects SGP totals

The 60/40 H/P split is a rule-of-thumb. Replacing it with `totalHitSGP / (totalHitSGP + totalPitSGP)` anchors dollar allocation to where actual scoring opportunity exists in the loaded projections, without encoding market biases.

- [ ] **Step 1: Remove `HIT_POOL_SHARE` constant from `shared.js`**

In `shared.js`, remove this line (currently line 9):

```js
const HIT_POOL_SHARE = 0.60;  // hitters share 60% of pool; pitchers share 40%
```

- [ ] **Step 2: Replace the pool-split lines in `calculateAllValues`**

In `shared.js`, find and replace lines 619–624 (inside `calculateAllValues`, section "6. Normalize to $4,800"):

**Replace:**
```js
  // 6. Normalize to $4,800 with a hitting/pitching pool split.
  // Hitting gets HIT_POOL_SHARE (65%) — hitting is scarcer and harder to replace.
  const hitDollars = SALARY_POOL * HIT_POOL_SHARE;
  const pitDollars = SALARY_POOL * (1 - HIT_POOL_SHARE);
```

**With:**
```js
  // 6. Normalize to $4,800 with a hitting/pitching pool split derived from SGP totals.
  // Allocating dollars proportional to where scoring opportunity exists avoids
  // hardcoded assumptions and self-corrects as projections update.
  const totalSGP = totalHitSGP + totalPitSGP;
  const dynamicHitShare = totalSGP > 0 ? totalHitSGP / totalSGP : 0.60;
  const hitDollars = SALARY_POOL * dynamicHitShare;
  const pitDollars = SALARY_POOL * (1 - dynamicHitShare);
```

- [ ] **Step 3: Add a test to `test.html` verifying the dynamic split**

In `test.html`, after the existing `Valuation Model` section tests (after line 221), add:

```js
    // Dynamic H/P split: hitter SGP fraction should drive dollar allocation.
    // Create a roster where all SGP comes from hitters → all dollars go to hitters.
    const hitOnly = [t1.filter(p => p.type === 'H'), t2.filter(p => p.type === 'H')];
    // Add minimal-IP pitchers so pitching is "valid" but contributes near-zero SGP
    const zeroPit = (team) => team.concat([
      mkFull(team+'z1',team+'z1','P',['sp'],{ip:1000,h:800,bb:250,hr:80,so:600,era:4.24,whip:1.28,hr9:1.15,er:471},1,team),
    ]);
    const vmDynamic = calculateAllValues([zeroPit('D1'), zeroPit('D2')]);
    // When pitching contributes near-zero SGP, hitter values should be higher than
    // they would be under a fixed 60/40 split (hitters get closer to 100% of pool).
    assert(typeof vmDynamic !== 'undefined', 'dynamic split: calculateAllValues returns a value map');
```

- [ ] **Step 4: Open `test.html` and verify all tests pass**

- [ ] **Step 5: Commit**

```bash
git add shared.js test.html
git commit -m "feat: derive H/P dollar split dynamically from SGP totals"
```

---

## Task 4: RoS Proration in FA and Trade Tools

**Files:**
- Modify: `shared.js` — add `rosProrationFactor()` helper after the constants block
- Modify: `fa.html:489-491` — add "RoS $" to column header arrays
- Modify: `fa.html:407-466` — add RoS value cell in `renderHitterRow` and `renderPitcherRow`
- Modify: `trade.html:301-303` — add "RoS $" / "RoS Surp" to column header array
- Modify: `trade.html:309-368` — add RoS value/surplus cell per player and in totals row
- Modify: `test.html` — add proration factor test

Dynasty value and dynasty surplus are **never prorated** — they span Y0+Y1+Y2 where Y1/Y2 are full future seasons. Only current-year `projectedValue` gets a prorated companion column.

- [ ] **Step 1: Add `rosProrationFactor()` to `shared.js`**

In `shared.js`, after the constants block (after line 35, before the SECURITY HELPER comment), add:

```js
// ── PRORATION ────────────────────────────────────────────────────────────────
// Returns the fraction of the MLB season remaining as of today.
// Used by FA and trade tools to show rest-of-season dollar value alongside
// full-season value. Approximates opening day as March 28, end as September 28.
function rosProrationFactor() {
  const year  = new Date().getFullYear();
  const start = new Date(year, 2, 28);  // March 28
  const end   = new Date(year, 8, 28);  // September 28
  const today = new Date();
  if (today <= start) return 1.0;
  if (today >= end)   return 0.0;
  return (end - today) / (end - start);
}
```

- [ ] **Step 2: Add proration test to `test.html`**

In `test.html`, add a new section before the closing `</script>` tag:

```js
    section('Proration');
    const factor = rosProrationFactor();
    assert(factor >= 0 && factor <= 1, 'rosProrationFactor: returns value between 0 and 1');
    // In mid-May (~45% through the season), factor should be roughly 0.55–0.65
    const today = new Date();
    const mayStart = new Date(today.getFullYear(), 4, 1);
    const mayEnd   = new Date(today.getFullYear(), 4, 31);
    if (today >= mayStart && today <= mayEnd) {
      assert(factor > 0.45 && factor < 0.75, 'rosProrationFactor: mid-May factor is reasonable (~0.55)');
    }
```

- [ ] **Step 3: Open `test.html` and verify proration tests pass**

- [ ] **Step 4: Update FA tool column headers in `fa.html`**

In `fa.html`, find lines 489–491 (hitter headers):

```js
        var hitCols = hasDynasty
          ? ['Name', 'Pos', 'Curr $', 'Dynasty $', 'HR', 'R', 'OBP', 'SLG', 'Helps']
          : ['Name', 'Pos', 'Proj $', 'HR', 'R', 'OBP', 'SLG', 'Helps'];
```

Replace with:

```js
        var hitCols = hasDynasty
          ? ['Name', 'Pos', 'Curr $', 'RoS $', 'Dynasty $', 'HR', 'R', 'OBP', 'SLG', 'Helps']
          : ['Name', 'Pos', 'Proj $', 'RoS $', 'HR', 'R', 'OBP', 'SLG', 'Helps'];
```

In `fa.html`, find lines 507–509 (pitcher headers):

```js
        var pitCols = hasDynasty
          ? ['Name', 'Pos', 'Curr $', 'Dynasty $', 'SO', 'ERA', 'WHIP', 'HR9', 'Helps']
          : ['Name', 'Pos', 'Proj $', 'SO', 'ERA', 'WHIP', 'HR9', 'Helps'];
```

Replace with:

```js
        var pitCols = hasDynasty
          ? ['Name', 'Pos', 'Curr $', 'RoS $', 'Dynasty $', 'SO', 'ERA', 'WHIP', 'HR9', 'Helps']
          : ['Name', 'Pos', 'Proj $', 'RoS $', 'SO', 'ERA', 'WHIP', 'HR9', 'Helps'];
```

- [ ] **Step 5: Add RoS value cell in `renderHitterRow` in `fa.html`**

In `fa.html`, find `renderHitterRow` (around line 407). After the line that appends the full-season value cell:

```js
      tr.appendChild(td(vm.noProj ? '—' : '$' + Math.round(val), valCls));
```

Add the RoS cell immediately after:

```js
      var rosFactor = rosProrationFactor();
      var rosVal    = val * rosFactor;
      var rosCls    = rosVal >= 20 ? 'val-strong' : (rosVal >= 5 ? 'val-mid' : 'val-zero');
      tr.appendChild(td(vm.noProj ? '—' : '$' + Math.round(rosVal), rosCls));
```

- [ ] **Step 6: Add RoS value cell in `renderPitcherRow` in `fa.html`**

In `fa.html`, find `renderPitcherRow` (around line 438). After the line that appends the full-season value cell:

```js
      tr.appendChild(td(vm.noProj ? '—' : '$' + Math.round(val), valCls));
```

Add:

```js
      var rosFactor = rosProrationFactor();
      var rosVal    = val * rosFactor;
      var rosCls    = rosVal >= 10 ? 'val-strong' : (rosVal >= 3 ? 'val-mid' : 'val-zero');
      tr.appendChild(td(vm.noProj ? '—' : '$' + Math.round(rosVal), rosCls));
```

- [ ] **Step 7: Update trade tool column headers in `trade.html`**

In `trade.html`, find lines 301–303:

```js
        var cols = hasDynasty
          ? ['Name', 'Salary', 'Curr $', 'Curr Surp', 'Dynasty $', 'Dyn. Surp']
          : ['Name', 'Salary', 'Proj $', 'Surplus'];
```

Replace with:

```js
        var cols = hasDynasty
          ? ['Name', 'Salary', 'Curr $', 'Curr Surp', 'RoS $', 'RoS Surp', 'Dynasty $', 'Dyn. Surp']
          : ['Name', 'Salary', 'Proj $', 'Surplus', 'RoS $', 'RoS Surp'];
```

- [ ] **Step 8: Add RoS cells per player row in `trade.html`**

In `trade.html`, find the per-player row construction inside `buildVexCol` (around line 334). After the `surpTd(surplus, noProj)` append and before the `if (hasDynasty)` block, add:

```js
          var rosFactor = rosProrationFactor();
          var rosVal    = value * rosFactor;
          var rosSurp   = rosVal - salary;
          var tdRos = el('td'); tdRos.textContent = noProj ? '—' : '$' + Math.round(rosVal);
          tr.appendChild(tdRos);
          tr.appendChild(surpTd(rosSurp, noProj));
```

Also add `totRosVal` and `totRosSurp` accumulators alongside the existing `totVal`/`totSurp` at the top of `buildVexCol`:

Find:
```js
        var totSal = 0, totVal = 0, totSurp = 0, totDyn = 0, totDynSurp = 0, allHaveProj = true;
```

Replace with:
```js
        var rosFactor = rosProrationFactor();
        var totSal = 0, totVal = 0, totSurp = 0, totRosVal = 0, totRosSurp = 0, totDyn = 0, totDynSurp = 0, allHaveProj = true;
```

And in the per-player accumulation block, find:
```js
          if (!noProj) { totVal += value; totSurp += surplus; totDyn += dynVal; totDynSurp += dynSurp; }
```

Replace with:
```js
          if (!noProj) { totVal += value; totSurp += surplus; totRosVal += rosVal; totRosSurp += rosSurp; totDyn += dynVal; totDynSurp += dynSurp; }
```

- [ ] **Step 9: Add RoS totals row cells in `trade.html`**

In `trade.html`, find the totals row construction (around line 350). After the `totX` append (`totTr.appendChild(totX);`) and before `if (hasDynasty)`, add:

```js
        var totRV = el('td'); totRV.textContent = allHaveProj ? '$' + Math.round(totRosVal) : '—';
        var totRS = el('td');
        if (allHaveProj) {
          totRS.textContent = (totRosSurp >= 0 ? '+$' : '-$') + Math.abs(Math.round(totRosSurp));
          totRS.className = totRosSurp >= 0 ? 'surplus-pos' : 'surplus-neg';
        } else { totRS.textContent = 'partial'; }
        totTr.appendChild(totRV); totTr.appendChild(totRS);
```

- [ ] **Step 10: Open `test.html` — verify all tests still pass**

- [ ] **Step 11: Smoke test FA and trade tools in browser**

Load `fa.html` and `trade.html` with real data. Verify:
- FA tool shows "RoS $" column with values lower than "Proj $" / "Curr $" (since we're partway through the season)
- Trade tool shows "RoS $" and "RoS Surp" columns for each player and in the totals row
- Dynasty columns are unchanged
- No JavaScript console errors

- [ ] **Step 12: Commit**

```bash
git add shared.js fa.html trade.html test.html
git commit -m "feat: add RoS proration columns to FA and trade tools"
```
