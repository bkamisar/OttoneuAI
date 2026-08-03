# PA-Budget Lineup Implementation Plan — v2 (post design review)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (user preference: inline execution) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the lineup optimizer from discarding injured stars, and rank hitters by what this league actually scores instead of raw volume or raw OPS.

**Status:** v2, 2026-08-03. Supersedes v1 after a design review that answered the six open
questions in `docs/superpowers/specs/2026-08-02-lineup-model-review-brief.md` and audited
the shipped Fix 1/Fix 2 code. v1 was never executed; no unwinding needed.

**Baseline:** `test.html` reports **140 passed, 0 failed**. Every task must keep failed at 0.
Test-count expectations below are approximate — verify the *failed = 0* invariant, and
update this plan's numbers to observed reality rather than forcing them.

**Note on commits:** Commit locally after each task. NEVER `git push` — the user pushes via
GitHub Desktop.

---

## Design decisions from the review (what changed vs v1 and why)

**D1 — Ranking key: denominator-aware, not OPS.** OPS weights OBP and SLG equally and
ignores HR/R entirely, but this 4×4 league scores all four. Derived from the live SGP
denominators (Aug 2026: D_OBP .0083, D_SLG .0094, D_HR 8.39, D_R 17.84; avg lineup
PA 2355 / AB 2082), the per-rate-unit z-weights for filling one slot, normalized to
OBP = 1, are: **slg 0.905, hr/pa 2.34, r/pa 1.10**. HR+R carry ~24% of a typical
starter's rank score — and empirically **380 rostered-hitter pairs flip order** between
OPS and this key (OPS overrates Arraez-types, underrates Perez-types). Weights are baked
constants (tunable knobs), not computed at runtime: deriving them live would be circular
(denominators need lineups). Seasonal drift in the ratios is an accepted approximation.

**D2 — Uncapped primary is principled, not pragmatic** (v1 called it a compromise; the
review found the real justification). A slot's true capacity is **162 games**
(`SLOT_CAP`, until now dead code), and a single player physically cannot exceed it — he
plays at most his team's games. So the primary is never capped. `PA_PER_SLOT = 650` is
not a capacity; it is the **expected PA of a full-timer**, i.e. the level below which the
slot has leftover days a bench bat would really cover. The PA arithmetic approximates the
games arithmetic well (verified: Judge 97 PA ≈ 24 games of a ~49-game RoS slot; the 99-PA
supplement ≈ the other 25 games). Backups sharing days with the primary is an accepted
approximation.

**D3 — Constant budget, year-aware.** Do not self-derive the budget from league data
(circular: observed slot PA already includes the injured players we are correcting for).
But it must be **year-aware**: Y1/Y2 valuation passes use full-season projections, so they
get the unprorated 650, exactly as `ipBudget` already does at [shared.js:971](../../shared.js).
v1 silently used the prorated budget for future years.

**D4 — Prorate the small-sample thresholds.** v1's fixed `PA_FULL_RATE = 50` inverts in
September: when every RoS projection is under 50 PA, the ramp multiplies everyone by
`pa/50` and the ranking silently degrades back to volume-biased — the original bug,
returning exactly when volume differences are pure noise. Thresholds are defined as
full-season constants × `max(rosProrationFactor(), 0.1)`.

**D5 — Two-phase assignment.** v1 supplemented each slot inline while iterating. That
lets a scarce player (e.g. the only backup catcher) be consumed as an OF backup before
the C slot is even processed. Phase 1 assigns every primary; phase 2 supplements.

**D6 — Loop supplementation** (v1: one backup, arbitrarily). Deep-injury slots can need
two. Loop while the shortfall exceeds the threshold, capped at 3 contributors per slot.

**D7 — `tfNeedGaps` must ignore derived `_n` keys** — a bug v1 would have introduced.
It medians each slot id across teams; backup keys exist only on injury-thinned teams, so
healthy teams would show `median − 0` = a phantom "need" at slots they don't have.
Filter to the primary `HITTER_SLOTS` ids.

**Kept from v1:** the 12-slot abstraction (it encodes position eligibility, which a pure
PA pool like `selectPitchers` cannot express — a global assignment optimizer is not
warranted); supplement-only design (healthy full-time lineups stay byte-identical);
`scaleHitterUsage` clones via `_proj` (verified: `computeTeamStats` reads `_proj || proj`);
no-duplicate-assignment invariant (a player fills at most one slot).

**Fix 1 / Fix 2 audit outcome:** sound. H0's full-`s0` cost matches Ottoneu's
full-salary cap accounting (MODEL.md §5); no other defects found beyond D7.

---

### Task 0: Baseline snapshot (before any code changes)

- [ ] Run the existing harness (`<scratchpad>/verify_marginal.js`) and save its output plus
the `[values]` line to `<scratchpad>/baseline_before_pa_budget.txt`. This is the
"before" for Task 5's before/after report. No commit.

---

### Task 1: Constants, rate key, usage scaling

**Files:**
- Modify: `shared.js` (constants near `SLOT_CAP`; helpers above `optimizeHitterLineup`)
- Modify: `test.html`

- [ ] **Step 1: Add constants** (in `shared.js`, immediately after `const SLOT_CAP = 162;`):

```js
// ── PA-BUDGET LINEUP ────────────────────────────────────────────────────────
// A lineup slot's hard capacity is SLOT_CAP games — one player can never exceed
// it, so primaries are never capped. PA_PER_SLOT is the EXPECTED full-season PA
// of a full-timer: below it, the slot has leftover days a bench bat would cover.
const PA_PER_SLOT = 650;
// Full-season thresholds, prorated at use (see paMinShare / hitterRateValue).
// Prorating matters: fixed thresholds invert in September, when every RoS
// projection is tiny and a fixed ramp would re-introduce volume bias.
const PA_FULL_RATE_FULL = 150;  // below (prorated) this, rate is ramped down as a partial sample
const PA_MIN_SHARE_FULL = 100;  // don't supplement (or accept a backup) below this (prorated)
// Hitter ranking weights: per-rate-unit z-value of filling one slot, derived
// from the Aug 2026 SGP denominators (D_OBP .0083, D_SLG .0094, D_HR 8.39,
// D_R 17.84; avg lineup PA 2355 / AB 2082), normalized to OBP = 1:
//   w_obp = 1/(T_PA·D_OBP)   w_slg = 0.9/(T_AB·D_SLG)   w_hr = 1/D_HR   w_r = 1/D_R
// OPS alone misranks: it overweights empty OBP/AVG and ignores HR/R (~24% of a
// starter's rank score); 380 rostered pairs flip order vs this key.
const HIT_RANK_W = { obp: 1.0, slg: 0.905, hrPerPA: 2.34, rPerPA: 1.10 };
```

- [ ] **Step 2: Add helpers** (immediately above `function optimizeHitterLineup`):

```js
// RoS plate appearances a single lineup slot is expected to absorb.
// NOTE: this is the ONLY date-dependent entry point. The ramp and min-share
// thresholds are derived from the budget inside optimizeHitterLineup, so the
// optimizer itself is a pure function of (hitters, budget) — deterministic in
// tests and correct in September, when fixed thresholds would exceed every
// projection and silently re-introduce volume bias.
function paSlotBudget() { return PA_PER_SLOT * Math.max(rosProrationFactor(), 0.1); }

// Ranking key for lineup selection: rate quality weighted by what this league
// scores (HIT_RANK_W), NOT raw volume and NOT raw OPS. Volume is handled by the
// slot budget — a short-PA player simply leaves room for a backup. The ramp only
// suppresses genuinely tiny samples. rampPA is overridable for deterministic tests.
function hitterRateValue(p, rampPA) {
  const b = p._proj || p.proj || {};
  const pa = b.pa || 0;
  const rate = (b.obp || 0) * HIT_RANK_W.obp
             + (b.slg || 0) * HIT_RANK_W.slg
             + (pa > 0 ? (b.hr || 0) / pa : 0) * HIT_RANK_W.hrPerPA
             + (pa > 0 ? (b.r  || 0) / pa : 0) * HIT_RANK_W.rPerPA;
  const ramp = Math.min(1, pa / (rampPA || PA_FULL_RATE_FULL * Math.max(rosProrationFactor(), 0.1)));
  return rate * ramp;
}

// A player contributing only part of a slot: rate stats unchanged, counting
// stats scaled to the fraction of his projection actually used.
function scaleHitterUsage(p, usedPA) {
  const b = p._proj || p.proj || {};
  const full = b.pa || 0;
  if (!full || usedPA >= full) return p;
  const f = usedPA / full;
  return Object.assign({}, p, { _proj: Object.assign({}, b, {
    pa: usedPA,
    ab: (b.ab || 0) * f,
    hr: (b.hr || 0) * f,
    r:  (b.r  || 0) * f,
  }) });
}
```

- [ ] **Step 3: Tests** (insert before `// ── Summary ──` in `test.html`). Tests pass an
explicit `rampPA` so they are date-independent:

```js
    // ── PA-budget lineup: rate key + scaling ─────────────────────────────────
    section('PA budget');
    var paJudge = { name: 'judge', type: 'H', positions: ['of'], proj: { pa: 97,  ab: 85,  obp: 0.420, slg: 0.551, hr: 8, r: 15 } };
    var paRaf   = { name: 'raf',   type: 'H', positions: ['of'], proj: { pa: 213, ab: 195, obp: 0.300, slg: 0.411, hr: 6, r: 22 } };
    assert(hitterRateValue(paJudge, 45) > hitterRateValue(paRaf, 45),
      'hitterRateValue: injured star outranks healthy mediocrity');

    // The league scores HR and R: a power/R profile must beat an empty-OPS profile
    // that raw OPS would prefer. (Perez-vs-Arraez shape.)
    var paPower = { name: 'power', type: 'H', positions: ['c'], proj: { pa: 400, ab: 370, obp: 0.310, slg: 0.470, hr: 20, r: 44 } };
    var paEmpty = { name: 'empty', type: 'H', positions: ['c'], proj: { pa: 400, ab: 360, obp: 0.350, slg: 0.450, hr: 4,  r: 40 } };
    assert(((paEmpty.proj.obp + paEmpty.proj.slg) > (paPower.proj.obp + paPower.proj.slg)),
      'fixture check: OPS actually prefers the empty profile');
    assert(hitterRateValue(paPower, 45) > hitterRateValue(paEmpty, 45),
      'hitterRateValue: z-weights prefer the power/R profile OPS misses');

    var paFluke = { name: 'fluke', type: 'H', positions: ['of'], proj: { pa: 1, ab: 1, obp: 0.500, slg: 0.900, hr: 1, r: 1 } };
    assert(hitterRateValue(paFluke, 45) < hitterRateValue(paRaf, 45),
      'hitterRateValue: a 1-PA fluke is ramped below a real regular');

    var paScaled = scaleHitterUsage(paRaf, 100);
    assertEqual(paScaled._proj.pa, 100, 'scaleHitterUsage: PA set to the used amount');
    assertEqual(paScaled._proj.obp, 0.300, 'scaleHitterUsage: rate stats unchanged');
    assert(Math.abs(paScaled._proj.r - 22 * (100 / 213)) < 1e-9,
      'scaleHitterUsage: counting stats scale by the used fraction');
    assert(scaleHitterUsage(paRaf, 500) === paRaf,
      'scaleHitterUsage: asking for more than projected returns the player untouched');
    assert(paSlotBudget() > 0, 'paSlotBudget: positive');
```

- [ ] **Step 4: Verify** — hard-refresh `http://localhost:8000/test.html`; all green
(~140 + 9 new). **Step 5: Commit** `feat(lineup): denominator-aware rate key + partial-usage scaling`.

---

### Task 2: Two-phase optimizer with loop supplementation

**Files:**
- Modify: `shared.js` (`optimizeHitterLineup`, ~line 830)
- Modify: `test.html`

- [ ] **Step 1: Replace `optimizeHitterLineup`** with:

```js
// Assigns hitters to slots under a PA budget. Returns { slotId: player } map;
// derived keys (OF1_2, C_3, …) are scaled backup contributions for slots whose
// primary cannot fill the budget. paBudget overridable: future-year valuation
// passes full-season PA_PER_SLOT; tests pass explicit budgets.
function optimizeHitterLineup(hitters, paBudget) {
  const budget = paBudget || paSlotBudget();
  // Thresholds scale with the budget, keeping this a pure function of its
  // arguments: a September budget shrinks the ramp and min-share with it.
  const rampPA   = budget * PA_FULL_RATE_FULL / PA_PER_SLOT;   // ≈ 0.23 × budget
  const minShare = budget * PA_MIN_SHARE_FULL / PA_PER_SLOT;   // ≈ 0.15 × budget
  const scored = hitters
    .filter(p => p.type === 'H')
    .map(p => {
      const b = p.proj || {};
      return { ...p, _proj: b, _value: hitterRateValue(p, rampPA) };
    })
    .sort((a, b) => b._value - a._value);

  const slots = [...HITTER_SLOTS].sort((a, b) =>
    scored.filter(p => a.eligible(p)).length - scored.filter(p => b.eligible(p)).length
  );

  const assignment = {};
  const used = new Set();

  // Phase 1 — primaries only. No player may be consumed as a backup before
  // every slot has its best available starter (a lone backup catcher must not
  // be eaten by an OF slot's supplementation).
  for (const slot of slots) {
    const best = scored.find(p => slot.eligible(p) && !used.has(p.fgId || p.name));
    if (best) { assignment[slot.id] = best; used.add(best.fgId || best.name); }
  }

  // Phase 2 — supplementation. The primary always contributes his FULL
  // projection (one player cannot exceed the slot's SLOT_CAP-game capacity, so
  // he is never capped). When injury or part-time usage leaves the slot short
  // of the budget, bench bats absorb the remainder as scaled clones — the slot
  // is shared, as it would be in a real daily lineup.
  for (const slot of slots) {
    const primary = assignment[slot.id];
    if (!primary) continue;
    let shortfall = budget - ((primary._proj && primary._proj.pa) || 0);
    let n = 2;
    while (shortfall >= minShare && n <= 3) {
      const backup = scored.find(p => slot.eligible(p) && !used.has(p.fgId || p.name)
        && ((p._proj && p._proj.pa) || 0) >= minShare);
      if (!backup) break;
      const give = Math.min(shortfall, backup._proj.pa);
      assignment[slot.id + '_' + n] = scaleHitterUsage(backup, give);
      used.add(backup.fgId || backup.name);
      shortfall -= give;
      n++;
    }
  }
  return assignment;
}
```

- [ ] **Step 2: Tests** (explicit budgets → date-independent):

```js
    // ── PA-budget lineup: supplementation ────────────────────────────────────
    function paC(name, pa, obp, slg, hr, r) {
      return { name: name, fgId: name, type: 'H', positions: ['c'],
               proj: { pa: pa, ab: pa * 0.9, obp: obp, slg: slg, hr: hr, r: r } };
    }
    // Injured elite + healthy mediocre catcher, budget 196.
    var paLu = optimizeHitterLineup([paC('eliteC', 97, 0.420, 0.551, 8, 15),
                                     paC('okC',   213, 0.300, 0.411, 6, 22)], 196);
    assertEqual(paLu['C'].name, 'eliteC', 'optimizer: elite injured bat is the PRIMARY');
    assert(paLu['C_2'] && paLu['C_2'].name === 'okC', 'optimizer: backup fills the shortfall');
    assert(Math.abs(paLu['C_2']._proj.pa - 99) < 1e-9, 'optimizer: backup scaled to 196−97 PA');

    // Full-timer overflows the budget: NO backup, full projection kept.
    var paLu2 = optimizeHitterLineup([paC('fullC', 250, 0.340, 0.450, 10, 30),
                                      paC('benchC', 200, 0.300, 0.400, 5, 20)], 196);
    assertEqual(paLu2['C'].name, 'fullC', 'optimizer: full-timer is primary');
    assert(!paLu2['C_2'], 'optimizer: no supplementation when the primary exceeds the budget');
    assertEqual(paLu2['C']._proj.pa, 250, 'optimizer: primary is never capped');

    // Deep shortfall loops to a third contributor.
    var paLu3 = optimizeHitterLineup([paC('c1', 60, 0.380, 0.500, 5, 10),
                                      paC('c2', 60, 0.340, 0.450, 4, 9),
                                      paC('c3', 100, 0.320, 0.420, 4, 12)], 196);
    assert(paLu3['C'] && paLu3['C_2'] && paLu3['C_3'], 'optimizer: loop supplements twice on a deep shortfall');
    var paNames3 = Object.values(paLu3).map(function (p) { return p.name; });
    assertEqual(paNames3.length, new Set(paNames3).size, 'optimizer: no duplicates across primary+backup keys');

    // Incentive check: a healthy full-timer beats an injured star + mediocre
    // backup of the same blended volume — supplementation must never make
    // rostering injuries BETTER than health.
    function paTeamZ(lu) {
      var st = computeTeamStats(lu, [], 0);
      return st.HR / 8.39 + st.R / 17.84 + st.OBP / 0.0083 + st.SLG / 0.0094;
    }
    var paHealthy = optimizeHitterLineup([paC('healthy', 196, 0.420, 0.551, 16, 30)], 196);
    var paInjured = optimizeHitterLineup([paC('star', 97, 0.420, 0.551, 8, 15),
                                          paC('bench', 99, 0.300, 0.411, 3, 10)], 196);
    assert(paTeamZ(paHealthy) >= paTeamZ(paInjured),
      'optimizer: healthy full-timer ≥ injured star + backup (no perverse incentive)');
```

- [ ] **Step 3: Verify** — all green, existing optimizer fixture untouched (12 hitters, all
consumed as primaries, no bench → no `_n` keys regardless of date). **If
`optimizer: no duplicate assignments` fails, STOP** — the `used` bookkeeping is wrong.
- [ ] **Step 4: Commit** `feat(lineup): two-phase PA-budget assignment with loop supplementation`.

---

### Task 3: Year-aware budget at the valuation call site

**Files:**
- Modify: `shared.js:1045` (inside `calculateAllValues`'s teamLineups map)

- [ ] **Step 1:** The block at ~1041 already has year-aware `ipBudget` (from ~line 971,
`isFutureYear ? IP_MAX : …`). Change line 1045 from
`const lineup = optimizeHitterLineup(hitters);` to:

```js
    const lineup   = optimizeHitterLineup(hitters, isFutureYear ? PA_PER_SLOT : undefined);
```

(If `isFutureYear` is not in scope at that line, derive it exactly as the `ipBudget`
computation does — mirror, don't invent.) The seven page-level callers stay unchanged:
they are all Y0 contexts and the prorated default is correct for them.

- [ ] **Step 2:** Verify test.html still all green. **Step 3: Commit**
`fix(lineup): full-season PA budget for Y1/Y2 valuation passes`.

---

### Task 4: `tfNeedGaps` must ignore backup keys

**Files:**
- Modify: `tradefinder.js` (`tfNeedGaps`)
- Modify: `test.html`

- [ ] **Step 1:** In `tfNeedGaps`, restrict the slot-id universe to primary slots.
Where slot ids are collected, replace with:

```js
  var primaryIds = {};
  HITTER_SLOTS.forEach(function (s) { primaryIds[s.id] = 1; });
  var slotIds = {};
  teams.forEach(function (t) {
    Object.keys(occ[t]).forEach(function (s) { if (primaryIds[s]) slotIds[s] = 1; });
  });
```

Rationale (comment it): backup keys (`C_2`, `OF1_3`) exist only on injury-thinned rosters;
mediating them across teams would show healthy teams a phantom "need" of
`median − 0` at slots they don't have.

- [ ] **Step 2: Test:**

```js
    // A team with a supplemented slot must not create phantom needs elsewhere.
    var paGapRosters = {
      Whole:  [paC('wc1', 250, 0.340, 0.450, 10, 30)],
      Injured:[paC('ic1', 97, 0.420, 0.551, 8, 15), paC('ic2', 213, 0.300, 0.411, 6, 22)]
    };
    var paGapMarg = tfAllMarginals(paGapRosters, tfDen, 400);
    var paGaps2 = tfNeedGaps(paGapRosters, paGapMarg);
    assert(!Object.keys(paGaps2.Whole).some(function (s) { return s.indexOf('_') > -1; }),
      'tfNeedGaps: no derived backup keys in the gap map');
```

- [ ] **Step 3:** Verify green. **Step 4: Commit**
`fix(trade): need gaps ignore supplemented backup slots`.

---

### Task 5: Live verification — before/after

**Files:** `<scratchpad>/verify_lineup.js` (throwaway, do NOT commit)

- [ ] Reuse v1's harness (same sandbox pattern; remember `var __CATS = CATS;` for const
extraction). Check, comparing against Task 0's baseline snapshot:
1. **Judge and Soto START** (primary or backup key) and carry **non-zero marginal value**.
2. **Shared slots are a minority** of the 144 league-wide slots. If most slots have `_n`
   keys, `PA_PER_SLOT` is manufacturing phantom playing time — STOP.
3. **Y0 values still sum to ~$4800** (pool conservation is by construction; drift means a leak).
4. **§2 anchors move modestly, not upheaval**: hitShare ≈ 50% ± a couple points; top
   hitters/aces shift but stay in-band; report before → after numbers, don't assert equality.
   Judge/Soto's own Y0 values should RISE (they now contribute to team aggregation).
5. Print the horizon diagnostic (`[dynasty]`) once — dynasty numbers ride on Y0, so record
   the new H0/H1/H2 split for MODEL.md if it moved.

---

### Task 6: MODEL.md

- [ ] **§2 step 1:** describe the lineup as "12 slots under a PA budget (`PA_PER_SLOT` ×
proration; full-season for Y1/Y2), denominator-aware rate ranking (`HIT_RANK_W`),
supplementation for injury-thinned slots."
- [ ] **§3:** replace the "hitting needs no volume cap (one hitter per active slot)" clause —
hitting now has the PA-budget analog of the pitching innings budget.
- [ ] **§5:** the "inherited lineup flaw" caveat under marginal value → resolved, pointing here.
- [ ] **§6 knobs:** `PA_PER_SLOT` 650, `PA_FULL_RATE_FULL` 150, `PA_MIN_SHARE_FULL` 100,
`HIT_RANK_W` {1.0/0.905/2.34/1.10} with the derivation formula.
- [ ] **§8:** mark the volume-bias limitation **RESOLVED** (short note: what it was, the two
measured defects, where the fix lives). Update anchor numbers if Task 5 moved them.
- [ ] **Commit** `docs(model): PA-budget lineup + denominator-aware ranking`.

---

## Definition of done

- `test.html` all green (~140 + ~14 new; verify empirically).
- Judge and Soto start with non-zero marginals; shared slots a minority; Y0 sums to ~$4800.
- Before/after anchor movement reported (not asserted away).
- MODEL.md §2, §3, §5, §6, §8 updated.

## Explicitly out of scope

- The archetype generator (next plan — unblocked once this ships).
- Arbitration escalation (+$2/+$4) — unchanged, per spec non-goals.
- Global assignment optimization / reopening the 12-slot abstraction (reviewed and kept).
