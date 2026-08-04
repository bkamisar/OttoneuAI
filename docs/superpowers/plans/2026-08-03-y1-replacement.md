# Y1/Y2 Rank-Based Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (user preference: inline execution) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the future-year replacement level so dynasty values stop underweighting hitters and over-concentrating on elite arms.

**Diagnosis (verified 2026-08-03, Fable session; details in MODEL.md §8):** the Y1 FA
baseline averages the top-8 *currently unrostered* hitters' full-season projections.
Mid-season churn leaves Duran/Naylor/McLain-class regulars unrostered, so Y1 hitter
replacement lands at **league average** (OBP .325/SLG .427 vs `LG_MEAN` .325/.430) —
half the league's bats fall below replacement (63% at the $1 floor), the pool
concentrates absurdly (Skubal $168 = 3.5% of pool), and hitShare reads 39.9% vs Y0's
54.2%. The FA-pitcher baseline is honest (4.14 ERA) because the league hoards arms.
**Conceptual error: "unrostered today" ≠ "freely available next season."** §4's option
horizons already establish that the roster boundary dissolves in October.

**Fix (validated by experiment):** for future years, assume the league re-rosters the
top N players of each type by *that year's* value (N = currently rostered count of that
type) and take the replacement cohort from the boundary of what remains — ranks
`N..N+COHORT` of the full projection pool. Measured result: hitShare **43.1%**, floor
**31%**, Skubal **$92**, Ohtani **$59**. The residual gap to 50% may be genuine
league-level pitching scarcity — do NOT force it; report and sanity-check.

**Baseline:** `test.html` reports **161 passed, 0 failed**. Keep failed at 0 throughout.

**Note on commits:** Commit locally after each task. NEVER `git push`.

---

### Task 0: Baseline snapshot (correct call convention!)

- [ ] Record the pre-fix real-path Y1 numbers for the before/after report. The
signature is `calculateAllValues(rosters, extraPlayers, quiet, yearKey)` — **four
arguments**. Passing `'proj_y1'` third silently runs a garbage pass (MODEL.md §2
gotcha). Use the harness at `<scratchpad>/diag_real.js` (already correct) or replicate
its call: `calculateAllValues(y1Clone, null, false, 'proj_y1')`. Save output to
`<scratchpad>/baseline_before_y1fix.txt`. Expected (from the diagnosis):
`hitShare 39.9%, replH PA 609 HR 21 OBP .325, floor 325/518, Skubal $168, Ohtani $100`.

---

### Task 1: Per-type rostered counts in the matchPlayers snapshot

**Files:** Modify `shared.js` (the snapshot block in `matchPlayers`, ~line 515, and the
declaration block near `ROSTERED_IDS`, ~line 557); modify `test.html`.

- [ ] **Step 1:** Next to `let ROSTERED_IDS = null; let ROSTERED_NAMES = null;` add:

```js
let ROSTERED_COUNTS = null;  // { H, P } — rostered players by type, same snapshot
```

- [ ] **Step 2:** In `matchPlayers`, where `ROSTERED_IDS`/`ROSTERED_NAMES` are set, add:

```js
  ROSTERED_COUNTS = {
    H: rosterPlayers.filter(p => p.type === 'H').length,
    P: rosterPlayers.filter(p => p.type === 'P').length,
  };
```

- [ ] **Step 3:** Test (before `// ── Summary ──`):

```js
    // ── Y1 rank-based replacement ────────────────────────────────────────────
    section('Future-year replacement');
    // matchPlayers snapshot captures per-type rostered counts (invariant #8 family).
    assert(typeof ROSTERED_COUNTS === 'object' && ROSTERED_COUNTS.H > 0 && ROSTERED_COUNTS.P > 0,
      'ROSTERED_COUNTS: captured by matchPlayers');
```

(The existing suite already calls `matchPlayers` with fixture rosters earlier in the
file, so the snapshot is populated by the time this runs.)

- [ ] **Step 4:** Verify all green (~162). Commit:
`feat(valuation): snapshot per-type rostered counts in matchPlayers`

---

### Task 2: Rank-based future-year cohort in `computeFABaselines`

**Files:** Modify `shared.js` (`computeFABaselines`, ~line 559); modify `test.html`.

- [ ] **Step 1:** Replace the body of `computeFABaselines` with:

```js
function computeFABaselines(hittingProj, pitchingProj, rosterPlayers, yearKey) {
  const rosteredIds   = ROSTERED_IDS   || new Set(rosterPlayers.map(p => p.fgId).filter(Boolean));
  const rosteredNames = ROSTERED_NAMES || new Set(rosterPlayers.map(p => p.name));
  const isFA = p => !(p.fgId && rosteredIds.has(p.fgId)) && !rosteredNames.has(p.name);

  // Ranked pools (role floors applied first — same floors as before).
  const hPool = (hittingProj || [])
    .filter(p => p.proj && (p.proj.pa || 0) >= FA_MIN_PA)
    .sort((a, b) => valProxy({ type: 'H' }, b.proj) - valProxy({ type: 'H' }, a.proj));
  const pPool = (pitchingProj || [])
    .filter(p => p.proj && (p.proj.ip || 0) >= FA_MIN_IP)
    .sort((a, b) => valProxy({ type: 'P' }, b.proj) - valProxy({ type: 'P' }, a.proj));

  const future = yearKey && yearKey !== 'proj';
  let faH, faP;
  if (future) {
    // FUTURE YEARS: "unrostered today" is not "freely available next season" —
    // the offseason reshuffle re-rosters the best available (cutting is free at
    // season's end; ~60% of contracts resolve to the rental horizon, see §4).
    // Assume the league re-rosters the top N of each type by THIS year's value
    // (N = players it rosters today) and take replacement from the boundary of
    // what remains. Without this, mid-churn unrostered regulars (Duran/Naylor/
    // McLain class) set Y1 hitter replacement at league average and crush every
    // bat's margin.
    const counts = ROSTERED_COUNTS || {
      H: rosterPlayers.filter(p => p.type === 'H').length,
      P: rosterPlayers.filter(p => p.type === 'P').length,
    };
    faH = hPool.slice(counts.H, counts.H + FA_COHORT_H);
    faP = pPool.slice(counts.P, counts.P + FA_COHORT_P);
  } else {
    // Y0: today's rosters are current reality — the best actual FAs ARE the
    // freely available alternative right now.
    faH = hPool.filter(isFA).slice(0, FA_COHORT_H);
    faP = pPool.filter(isFA).slice(0, FA_COHORT_P);
  }

  FA_BASELINES[yearKey] = {
    H: avgCohortStats(faH.map(p => p.proj), ['pa', 'hr', 'r', 'obp', 'slg']),
    P: avgCohortStats(faP.map(p => p.proj), ['ip', 'so', 'era', 'whip', 'hr9']),
  };
}
```

Notes: the `avgCohortStats` `< 3 → null` guard is unchanged, so an empty Y2 pitching
file (0 rows today) still yields `P: null` and the existing weakest-quartile fallback —
same as current behavior. The future branch no longer uses `isFA` at all, which also
hardens the bid.html attach-to-FA-pool path (invariant #8).

- [ ] **Step 2:** Tests:

```js
    // Future years slice past the re-rostered boundary; Y0 slices the top of the FA pool.
    (function () {
      function hp(n, pa, obp, slg) { return { name: n, proj: { pa: pa, ab: pa*0.9, hr: 10, r: 50, obp: obp, slg: slg } }; }
      // Pool of 6 ranked hitters; league "rosters" 3 hitters (fixture counts below).
      var pool = [hp('h1',600,0.400,0.550), hp('h2',600,0.380,0.520), hp('h3',600,0.360,0.500),
                  hp('h4',600,0.340,0.470), hp('h5',600,0.320,0.440), hp('h6',600,0.300,0.410)];
      var savedCounts = ROSTERED_COUNTS, savedBase = FA_BASELINES['proj_y1'];
      ROSTERED_COUNTS = { H: 3, P: 3 };
      computeFABaselines(pool, [], [], 'proj_y1');
      var got = FA_BASELINES['proj_y1'].H;
      // ranks 4-6 average OBP = (.340+.320+.300)/3 = .320
      assert(Math.abs(got.obp - 0.320) < 1e-9,
        'computeFABaselines: future year takes the post-reshuffle boundary cohort');
      // Y0 path unchanged: same pool, everyone unrostered → top-of-pool cohort... but
      // cohort minimum is 3, and top-3 average OBP = .380.
      computeFABaselines(pool, [], [], 'proj');
      assert(Math.abs(FA_BASELINES['proj'].H.obp - 0.380) < 1e-9,
        'computeFABaselines: Y0 still averages the top FA cohort');
      // Pool thinner than the boundary → null → callers fall back (Y2 pitching case).
      ROSTERED_COUNTS = { H: 10, P: 10 };
      computeFABaselines(pool, [], [], 'proj_y2');
      assert(FA_BASELINES['proj_y2'].H === null,
        'computeFABaselines: pool thinner than the boundary yields null (fallback path)');
      ROSTERED_COUNTS = savedCounts; FA_BASELINES['proj_y1'] = savedBase;
      // restore Y0 baseline for any later tests
      delete FA_BASELINES['proj_y2'];
    })();
```

**Caution:** `computeFABaselines('proj', …)` in the test overwrites the fixture-derived
Y0 baseline. If any LATER existing assertion depends on `FA_BASELINES['proj']`, either
save/restore it exactly as the snippet does for `proj_y1`, or move this block to just
before `// ── Summary ──`. Verify by the total count staying green.

- [ ] **Step 3:** Verify all green (~165). Commit:
`fix(valuation): future-year replacement from the post-reshuffle boundary`

---

### Task 3: Harden the `calculateAllValues` signature

The four-arg signature silently produced a session of wrong numbers when `yearKey` was
passed third (MODEL.md §2 gotcha).

**Files:** Modify `shared.js` (`calculateAllValues`, ~line 1121); modify `test.html`.

- [ ] **Step 1:** At the top of `calculateAllValues`, before `isFutureYear`:

```js
  // Guard against the (rosters, extras, 'proj_y1') call shape — yearKey passed
  // in the quiet slot ran a silent Y0-baseline pass and cost a debugging session.
  if (typeof quiet === 'string') { yearKey = quiet; quiet = true; }
```

- [ ] **Step 2:** Test:

```js
    // Signature guard: yearKey passed in the quiet slot must still be honored.
    // (Indirect check: the guard shifts a string quiet into yearKey, so a
    // 3-arg misuse behaves identically to the correct 4-arg call.)
    assert((function () {
      var src = calculateAllValues.toString();
      return src.indexOf("typeof quiet === 'string'") !== -1;
    })(), 'calculateAllValues: string-quiet guard present');
```

- [ ] **Step 3:** Verify all green (~166). Commit:
`fix(valuation): tolerate yearKey passed in the quiet slot`

---

### Task 4: Live verification — before/after

- [ ] Run the corrected real-path harness (Task 0's) against the new code. Check
against `baseline_before_y1fix.txt`:
1. **Y1 hitShare ≈ 43%** (was 39.9%). If it lands outside 41-46%, STOP and report.
2. **Y1 floor ≈ 162/518 (~31%)** (was 63%); **Skubal ≈ $92** (was $168), **Ohtani ≈ $59**.
3. **Y0 is byte-identical** — the Y0 branch is untouched: hitShare 54.2%, same top
   values as `baseline_before_pa_budget.txt`'s "after" run. ANY Y0 movement is a bug.
4. **Dynasty pass:** re-run `calculateDynastyValues`; report the new `[dynasty]`
   H0/H1/H2 split (mid-tier Y1 values rise → expect somewhat more H1/H2 keepers) and
   the prospect anchors (Made/Basallo/De Vries are floor-driven and should hold within
   a dollar or two; McLean is projection-driven and may move — report, don't assert).
5. No commit (harness stays in scratchpad); record numbers for Task 5's commit message.

---

### Task 5: MODEL.md

- [ ] **§2:** replace the pre-fix Y1 anchor block with the measured post-fix numbers
(hitShare, top H/P values, floor share), keeping the four-arg gotcha note.
- [ ] **§8:** mark the Y1-replacement defect **RESOLVED**, one short paragraph: what it
was, the boundary-cohort fix, before → after numbers, and the note that the residual
gap to 50% is plausibly real league pitching scarcity (sanity-check against the
league's dynasty market before "fixing" further).
- [ ] **§1 or §7:** add one line documenting `ROSTERED_COUNTS` alongside the
`ROSTERED_IDS`/`ROSTERED_NAMES` snapshot in the invariant #8 description.
- [ ] Commit: `docs(model): Y1 replacement from post-reshuffle boundary — resolved`

---

## Definition of done

- Suite green (~166 assertions, failed = 0).
- Y1 hitShare 41-46%, floor ~31%, top values sane (top arm ≤ ~2% of pool).
- Y0 pass byte-identical to pre-fix.
- MODEL.md §2/§8 updated with measured numbers.

## Out of scope

- Forcing Y1 hitShare to 50% (residual gap may be real arm-hoarding scarcity).
- The archetype generator (next after this lands).
- Arbitration escalation (+$2/+$4), unchanged per spec non-goals.
