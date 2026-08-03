# Option-Valued Contracts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Price a dynasty contract as an option (best of rent / hold-1 / hold-2) instead of assuming a forced 3-year hold, so productive-but-overpaid players stop reading as huge liabilities.

**Architecture:** A pure helper `computeContractHorizon` evaluates three holding horizons and returns the value/cost/surplus of the winner plus a `holdHorizon` label. `calculateDynastyValues` calls it in place of its inline 3-year cost formula. Everything else in the suite reads the same `dynastyValue`/`dynastySurplus` fields it always has.

**Tech stack:** Vanilla browser JS (no build). Tests run in `test.html` via `assert()`/`assertEqual()`, verified by serving the repo with `python -m http.server` and confirming the green summary count.

**Source spec:** [docs/superpowers/specs/2026-08-02-trade-finder-redesign.md](../specs/2026-08-02-trade-finder-redesign.md) — this plan implements **Fix 1** only. The marginal-value engine (Fix 2) and the archetype generator get their own plans.

**Note on commits:** Commit locally after each task. NEVER `git push` — the user pushes via GitHub Desktop.

**Baseline:** `test.html` currently reports **112 assertions, 0 failed**. Every task must keep failed at 0.

---

### Task 1: `computeContractHorizon` helper

**Files:**
- Modify: `shared.js` (add the function immediately above `calculateDynastyValues`)
- Modify: `test.html` (add a test block before the `── Summary ──` block)

- [ ] **Step 1: Write the failing tests**

In `test.html`, insert this immediately before the `// ── Summary ──` comment:

```js
    // ── Option-valued contracts ──────────────────────────────────────────────
    section('Contract horizons');
    // Cheap productive player: keeping all three years is clearly best.
    var cheap = computeContractHorizon(20, 22, 21, 5, 0.90, 0.81, 0.45, 0);
    assertEqual(cheap.holdHorizon, 2, 'horizon: cheap productive contract → keeper (H2)');
    assert(cheap.dynastySurplus > 40, 'horizon: cheap contract surplus is large positive');

    // Productive but overpaid: renting beats holding. The spec's worked example.
    var rental = computeContractHorizon(12, 18, 15, 30, 0.90, 0.81, 0.45, 0);
    assertEqual(rental.holdHorizon, 0, 'horizon: overpaid productive → rental (H0)');
    assert(Math.abs(rental.dynastySurplus - (-1.5)) < 0.01,
      'horizon: rental surplus ≈ -1.5 (was -46 under forced 3-year hold)');
    assertEqual(rental.dynastyValue, 12, 'horizon: rental value is Y0 only');
    assert(Math.abs(rental.dynastyCost - 13.5) < 0.01, 'horizon: rental cost is prorated salary only');

    // Overpaid AND unproductive: negative at every horizon; max is still negative.
    var bad = computeContractHorizon(2, 3, 2, 25, 0.90, 0.81, 0.45, 0);
    assert(bad.dynastySurplus < 0, 'horizon: genuinely bad contract stays negative');
    assertEqual(bad.holdHorizon, 0, 'horizon: bad contract cuts at earliest horizon');

    // Prospect floor applies to the long horizon and wins there (invariant #6).
    var prospect = computeContractHorizon(0, 2, 3, 1, 0.90, 0.81, 0.45, 45);
    assertEqual(prospect.holdHorizon, 2, 'horizon: prospect floor → keeper (H2)');
    assertEqual(prospect.dynastyValue, 45, 'horizon: prospect floor becomes the H2 value');

    // Value and cost must always describe the SAME horizon.
    [cheap, rental, bad, prospect].forEach(function (h, i) {
      assert(Math.abs((h.dynastyValue - h.dynastyCost) - h.dynastySurplus) < 1e-9,
        'horizon: value-cost-surplus internally consistent (case ' + i + ')');
    });

    // Salary floor: a $0 salary is treated as $1, never free.
    var freebie = computeContractHorizon(10, 10, 10, 0, 0.90, 0.81, 1.0, 0);
    assert(freebie.dynastyCost > 0, 'horizon: zero salary floors to $1, cost is positive');
```

- [ ] **Step 2: Run tests to verify they fail**

Start the server from the repo root:

```bash
python -m http.server 8000
```

Open `http://localhost:8000/test.html` and hard-refresh (Ctrl+Shift+R).
Expected: the run halts early with a red `✗` and the summary does NOT reach 112 —
`computeContractHorizon` is not defined, which throws a ReferenceError.

- [ ] **Step 3: Write the implementation**

In `shared.js`, insert directly above `function calculateDynastyValues(`:

```js
// ── CONTRACT HORIZONS ────────────────────────────────────────────────────────
// A dynasty contract is an OPTION, not an obligation: cutting is free at
// season's end, so nobody is forced to carry an escalating salary for three
// years. Evaluate each holding horizon and return the best one:
//   H0 "rental" — keep through this season only, then cut
//   H1          — keep one additional year  (+$2 escalation)
//   H2 "keeper" — keep two additional years (+$2 / +$4)
// Y0 values are REST-OF-SEASON (invariant #1), so the year-0 salary term is
// prorated to match — charging a full season's salary against a partial
// season's production was a latent bug in the old formula.
// Value and cost ALWAYS describe the same horizon; reporting a 3-year value
// against a 1-year cost would credit production that was never paid for.
function computeContractHorizon(y0, y1, y2, s0, w1, w2, ros, floor) {
  const salary = Math.max(1, s0 || 0);
  const base0  = salary * ros;          // this season's remaining salary
  const esc1   = Math.max(1, salary + 2);
  const esc2   = Math.max(1, salary + 4);

  const v0 = y0;
  const v1 = y0 + w1 * y1;
  // The prospect floor is long-horizon by nature — it represents what a
  // prospect is worth if you hold him. Apply it to H2 only, as max() never
  // additive (invariant #6).
  let   v2 = y0 + w1 * y1 + w2 * y2;
  if (floor > v2) v2 = floor;

  const c0 = base0;
  const c1 = base0 + w1 * esc1;
  const c2 = base0 + w1 * esc1 + w2 * esc2;

  const options = [
    { holdHorizon: 0, dynastyValue: v0, dynastyCost: c0, dynastySurplus: v0 - c0 },
    { holdHorizon: 1, dynastyValue: v1, dynastyCost: c1, dynastySurplus: v1 - c1 },
    { holdHorizon: 2, dynastyValue: v2, dynastyCost: c2, dynastySurplus: v2 - c2 },
  ];
  return options.reduce((best, o) => (o.dynastySurplus > best.dynastySurplus ? o : best));
}
```

- [ ] **Step 4: Run tests to verify they pass**

Reload `http://localhost:8000/test.html` with a hard refresh (invariant #7 — `shared.js`
is cached aggressively).
Expected: green summary reading **127 passed, 0 failed** (112 baseline + 15 new).

- [ ] **Step 5: Commit**

```bash
git add shared.js test.html
git commit -m "feat(valuation): computeContractHorizon prices contracts as options"
```

---

### Task 2: Wire the helper into `calculateDynastyValues`

**Files:**
- Modify: `shared.js:682-694` (the body of the `Object.keys(vmY0).forEach` loop)

- [ ] **Step 1: Replace the inline cost formula**

In `shared.js`, find this block inside `calculateDynastyValues`:

```js
    const currentValue = v0.projectedValue || 0;
    let dynastyValue = currentValue
      + w1 * (v1.projectedValue || 0)
      + w2 * (v2.projectedValue || 0);
    const floor = prospectDynastyValue(keyToProspect[key]);
    if (floor > dynastyValue) dynastyValue = floor;
    const s0 = Math.max(1, v0.actualSalary || 0);
    const dynastyCost = s0 + w1 * Math.max(1, s0 + 2) + w2 * Math.max(1, s0 + 4);
    dynastyMap[key] = {
      ...v0,
      dynastyValue,
      dynastySurplus: dynastyValue - dynastyCost,
    };
```

Replace it with:

```js
    const h = computeContractHorizon(
      v0.projectedValue || 0,
      v1.projectedValue || 0,
      v2.projectedValue || 0,
      v0.actualSalary   || 0,
      w1, w2, rosProrationFactor(),
      prospectDynastyValue(keyToProspect[key])
    );
    dynastyMap[key] = {
      ...v0,
      dynastyValue:   h.dynastyValue,
      dynastyCost:    h.dynastyCost,
      dynastySurplus: h.dynastySurplus,
      holdHorizon:    h.holdHorizon,
    };
```

`dynastyCost` and `holdHorizon` are new additive fields — nothing reads them yet, and no
existing consumer of `dynastyValue`/`dynastySurplus` changes shape.

- [ ] **Step 2: Verify the existing suite still passes**

Reload `http://localhost:8000/test.html` with a hard refresh.
Expected: **127 passed, 0 failed** — unchanged. Existing dynasty tests must not regress.
If any dynasty assertion now fails, STOP: it encodes an expectation about the old forced
3-year cost, and the correct fix needs a human decision about which behavior is intended.

- [ ] **Step 3: Commit**

```bash
git add shared.js
git commit -m "feat(valuation): use option-valued horizons in calculateDynastyValues"
```

---

### Task 3: Diagnostic — separate the two effects

The change bundles two corrections. They must be measurable independently so any drift is
attributable: **(a)** the proration fix (affects everyone, raises surplus roughly
uniformly) and **(b)** the option floor (affects overpaid-but-productive players only).

**Files:**
- Modify: `shared.js` (add a diagnostic log at the end of `calculateDynastyValues`, before `return dynastyMap;`)

- [ ] **Step 1: Add the diagnostic**

In `shared.js`, immediately before `return dynastyMap;` at the end of
`calculateDynastyValues`, insert:

```js
  // Diagnostic: quantify the two corrections separately so suite-wide drift is
  // attributable. (a) proration — H2 under prorated vs full year-0 salary;
  // (b) option — the winning horizon vs always-H2.
  try {
    const ros = rosProrationFactor();
    let nH0 = 0, nH1 = 0, nH2 = 0, prorationGain = 0, optionGain = 0, n = 0;
    Object.keys(dynastyMap).forEach(k => {
      const d = dynastyMap[k];
      if (d.holdHorizon === 0) nH0++; else if (d.holdHorizon === 1) nH1++; else nH2++;
      const v0 = vmY0[k] || {}, v1 = vmY1 ? (vmY1[k] || {}) : {}, v2 = vmY2 ? (vmY2[k] || {}) : {};
      const s0 = Math.max(1, v0.actualSalary || 0);
      let val2 = (v0.projectedValue || 0) + w1 * (v1.projectedValue || 0) + w2 * (v2.projectedValue || 0);
      const fl = prospectDynastyValue(keyToProspect[k]);
      if (fl > val2) val2 = fl;
      const escSum = w1 * Math.max(1, s0 + 2) + w2 * Math.max(1, s0 + 4);
      const oldSurplus = val2 - (s0 + escSum);             // old: full s0, forced H2
      const proratedH2 = val2 - (s0 * ros + escSum);       // proration only, still H2
      prorationGain += proratedH2 - oldSurplus;
      optionGain    += d.dynastySurplus - proratedH2;
      n++;
    });
    console.log('[dynasty] horizons H0/H1/H2 = ' + nH0 + '/' + nH1 + '/' + nH2 +
      ' | mean proration gain $' + (prorationGain / (n || 1)).toFixed(2) +
      ' | mean option gain $' + (optionGain / (n || 1)).toFixed(2));
  } catch (e) { /* diagnostic only — never break valuation */ }
```

- [ ] **Step 2: Read the diagnostic**

Open `http://localhost:8000/roster.html`, hard-refresh, and read the browser console.
Expected: one `[dynasty]` line, e.g.
`[dynasty] horizons H0/H1/H2 = 41/12/470 | mean proration gain $6.20 | mean option gain $1.85`

Sanity checks on that line — if any fails, STOP and report rather than proceeding:
- **`mean option gain` is positive.** The option can only ever raise surplus (it takes a
  max), so a negative mean means the horizons are miscomputed.
- **No absurd positives.** Spot-check the most expensive contracts: a star on a rich deal
  must NOT show positive surplus late in the season. (An earlier draft prorated the
  year-0 salary and produced Bobby Witt Jr. at $68 with +$16 — that was the tell.)
- **H0 share ≈ 60%, but read it correctly.** Roughly 27 H0 players per team sounds high;
  ~163 of them league-wide are $1-3 fringe/deep-bench contracts whose routine churn nobody
  thinks of as "cutting someone." Meaningful cuts ($4+) are ~13 per team and $16+ are
  ~4.6 per team, which matches the league's actual offseason behavior. Verify the H0 calls
  are *decisive* rather than near-ties: >90% should beat H2 by more than $3. If most H0
  wins are sub-$1 margins, the label is noise and needs a longer-horizon tie-break.

- [ ] **Step 3: Commit**

```bash
git add shared.js
git commit -m "chore(valuation): [dynasty] diagnostic separating proration vs option effects"
```

---

### Task 4: Verify the anchors across the suite

No code changes — this task is verification. MODEL.md records sanity anchors that must
survive the change.

**Files:** none modified.

- [ ] **Step 1: Confirm Y0 anchors are untouched**

Open `http://localhost:8000/roster.html`, hard-refresh, read the `[values]` console line.
Expected (MODEL.md §2): hitShare ≈ 50%, top non-Ohtani hitter ≈ $55-65, aces $45-70,
~35% of rostered players at the $1 floor.

These come from `calculateAllValues`, which this plan does not touch — they must be
**unchanged**. Any movement means the edit leaked into Y0 valuation; STOP and report.

- [ ] **Step 2: Confirm prospect dynasty anchors are stable**

Open `http://localhost:8000/prospects.html`, hard-refresh. Check the three anchors named
in MODEL.md §4: **Made ≈ $59, Basallo ≈ $45, De Vries ≈ $41**.

Prospects carry $1-5 salaries and large future value, so H2 must win for them and their
values should be stable (small upward drift from the proration fix is expected and fine).
A prospect resolving to H0, or a value collapsing toward zero, means the floor is being
applied to the wrong horizon — STOP and report.

- [ ] **Step 3: Spot-check a known overpaid player**

Open `http://localhost:8000/roster.html`, hard-refresh, and sort by dynasty surplus
ascending. The most-negative players should now be genuinely bad contracts (overpaid AND
unproductive), not productive players on rich deals. Confirm at least one productive
player who previously sat deep negative has moved close to break-even.

Record the player name and before/after figure in the commit message for Task 5.

- [ ] **Step 4: Confirm no page throws**

Load each consumer with a hard refresh and confirm a clean console (no red errors):
`roster.html`, `trade.html`, `bid.html`, `prospects.html`, `targets.html`.

---

### Task 5: Update MODEL.md

**Files:**
- Modify: `MODEL.md` §4 (dynasty values), §7 (invariants)

- [ ] **Step 1: Rewrite the dynasty-cost bullet in §4**

In `MODEL.md` §4, replace the `**Dynasty cost:**` bullet with:

```markdown
- **Dynasty cost — contracts are OPTIONS, not obligations.** Cutting is free at
  season's end, so a contract is priced at the best available holding plan, not a
  forced 3-year hold. `computeContractHorizon` evaluates three horizons and returns
  the winner's value, cost and surplus plus `holdHorizon` (0/1/2):
  | Horizon | Value | Cost |
  |---|---|---|
  | H0 "rental" | `y0` | `s0×ros` |
  | H1 | `y0 + w1×y1` | `s0×ros + w1×(s0+2)` |
  | H2 "keeper" | `y0 + w1×y1 + w2×y2` | `s0×ros + w1×(s0+2) + w2×(s0+4)` |
  Ottoneu's +$2/yr base escalation still drives the cost side. The year-0 salary term
  is **prorated** (`rosProrationFactor()`) because Y0 values are rest-of-season —
  the previous formula charged a full season's salary against partial-season
  production, a latent invariant-#1 violation. **Known simplification:** arbitration
  adds ~$4-8/yr more to star salaries; the +$2/+$4 understates star keeper costs, and
  option-valuing pushes surplus up further, so star dynasty surplus reads somewhat
  rich. If tuning: raise the +2/+4, don't touch the value side.
```

- [ ] **Step 2: Add the new invariant in §7**

Append to the numbered list in `MODEL.md` §7:

```markdown
9. Dynasty value and dynasty cost must ALWAYS report the same holding horizon.
   Reporting a 3-year value against a 1-year cost credits production that was never
   paid for. `computeContractHorizon` returns the triple together for this reason —
   never recombine `dynastyValue` from one horizon with a cost from another. This is
   also load-bearing for the trade finder: the fairness filter matches value-for-value,
   so a rental must carry his rental value or no rental trade can ever clear.
```

- [ ] **Step 3: Note the prospect-floor horizon in §4**

In `MODEL.md` §4, append to the existing `**Prospect floor**` bullet:

```markdown
  The floor applies to the **H2 value only** — a prospect's scouting-based worth is
  inherently long-horizon — so prospects resolve to `holdHorizon = 2` and the floor
  stays `max(model, floor)`, never additive.
```

- [ ] **Step 4: Commit**

```bash
git add MODEL.md
git commit -m "docs(model): option-valued contract horizons + same-horizon invariant"
```

---

## Definition of done

- `test.html` reports **127 passed, 0 failed**.
- `[dynasty]` diagnostic prints, H2 is the majority horizon, both gains positive.
- Y0 anchors (`[values]`) unchanged; prospect anchors stable with H2.
- All five consumer pages load with a clean console.
- MODEL.md §4 and §7 updated.

## Out of scope (separate plans)

- **Fix 2 — marginal-value engine** (`tradefinder.js`): per-roster marginal value,
  blockedness, need gaps.
- **Phase 2 — archetype generator**: logjam/hole, rental/salary-dump, buy-now/sell-future,
  consolidation, plus `targets.html` rewiring.
- Arbitration escalation (+$2/+$4) stays as-is this pass — see spec Non-goals.
