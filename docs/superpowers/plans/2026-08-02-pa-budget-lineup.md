# PA-Budget Lineup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the lineup optimizer from discarding injured stars. Rank hitters by rate quality rather than raw volume, and let a second bat absorb a slot's unused plate appearances — mirroring how `selectPitchers` already fills an innings budget.

**Architecture:** `optimizeHitterLineup` keeps its 12 position slots and its scarcity ordering. Two changes: (1) the ranking key drops the volume multiplier, and (2) when a slot's primary occupant projects fewer PA than the slot's budget, a second eligible bat is added under a derived key (`OF1_2`) with counting stats scaled to the shortfall. Full-time slots are untouched.

**Tech stack:** Vanilla browser JS (no build). Unit tests in `test.html`. Live-data verification in Node (the in-app browser's fetch proxy caps ~400KB; `proj_pitching.csv` is 438KB).

**Source:** MODEL.md §8 "optimizeHitterLineup is volume-biased". Measured Aug 2026 on the Misiorowski Index roster: the misranking alone costs **0.915 z (~$13.7)**, and the either/or assumption costs a further **1.694 z (~$25.4)**.

**Note on commits:** Commit locally after each task. NEVER `git push` — the user pushes via GitHub Desktop.

**Baseline:** `test.html` reports **140 passed, 0 failed**. Every task must keep failed at 0.

---

## Why this design

Three constraints shaped it, all verified against the codebase:

1. **`computeTeamStats` reads `p._proj || p.proj`** ([shared.js:893](../../shared.js)), so a partial-usage player can be passed as a scaled clone with `_proj` set — no change to the consumer.
2. **6 of 7 callers pass the lineup straight into `computeTeamStats`** without inspecting slot keys; `bid.html:283` iterates `Object.keys` to build a starter set (extra keys are correct there); `test.html:161` reads `lu['C']`. So adding `OF1_2`-style keys is safe if primary keys keep their meaning.
3. **`test.html:169` asserts no duplicate assignments.** Therefore a player fills **at most one slot** — leftover PA beyond a slot's budget is not carried elsewhere. A player cannot occupy two lineup spots at once.

**Only supplement, never cap.** The primary occupant always contributes his full projection. A backup is added *only* when the primary falls short of the budget. This means healthy full-time lineups produce byte-identical results to today, and only injury-thinned slots change — the smallest blast radius that fixes the bug.

`OF_GAME_CAP` and `SLOT_CAP` already exist in `shared.js` but are **dead constants, referenced nowhere**. They are leftovers from exactly this intent. This plan completes it.

---

### Task 1: Ranking key and slot-budget constants

**Files:**
- Modify: `shared.js` (constants near `SLOT_CAP`; new helper above `optimizeHitterLineup`)
- Modify: `test.html`

- [ ] **Step 1: Add the constants and the ranking helper**

In `shared.js`, immediately after the `const SLOT_CAP = 162;` line, add:

```js
// Full-season plate appearances one lineup slot absorbs. Prorated for RoS use.
// Calibrated Aug 2026: 650 × rosProrationFactor(0.302) = 196 PA/slot, against an
// observed 194 PA/slot across the league's 12 optimized starters.
const PA_PER_SLOT  = 650;
// Below this many projected PA a hitter is treated as a partial sample and his
// rate is ramped down, so a 1-PA fluke cannot outrank a real regular.
const PA_FULL_RATE = 50;
// Don't bother supplementing a slot for a trivial shortfall.
const PA_MIN_SHARE = 30;
```

Then, immediately above `function optimizeHitterLineup(hitters) {`, add:

```js
// RoS plate appearances a single lineup slot absorbs.
function paSlotBudget() {
  return PA_PER_SLOT * Math.max(rosProrationFactor(), 0.1);
}

// Ranking key for lineup selection. RATE-first: volume is handled by the slot
// budget (a short-PA player simply leaves room for a backup), so multiplying by
// PA — as the old key did — double-counted volume and benched injured stars
// behind healthy mediocrities. The PA_FULL_RATE ramp only suppresses genuinely
// tiny samples; anyone at or above it is judged purely on rate.
function hitterRateValue(p) {
  const b = p._proj || p.proj || {};
  const ops = (b.obp || 0) + (b.slg || 0);
  const ramp = Math.min(1, (b.pa || 0) / PA_FULL_RATE);
  return ops * ramp;
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

- [ ] **Step 2: Add the failing tests**

Insert before `// ── Summary ──` in `test.html`:

```js
    // ── PA-budget lineup ─────────────────────────────────────────────────────
    section('PA budget');
    // Rate-first ranking: the injured star outranks the healthy mediocrity.
    var paJudge = { name: 'judge', type: 'H', positions: ['of'], proj: { pa: 97,  ab: 85,  obp: 0.420, slg: 0.551, hr: 8, r: 15 } };
    var paRaf   = { name: 'raf',   type: 'H', positions: ['of'], proj: { pa: 213, ab: 195, obp: 0.300, slg: 0.411, hr: 6, r: 22 } };
    assert(hitterRateValue(paJudge) > hitterRateValue(paRaf),
      'hitterRateValue: injured star (.971 OPS, 97 PA) outranks healthy mediocrity (.711, 213 PA)');

    // Tiny samples are ramped down so a fluke cannot lead the board.
    var paFluke = { name: 'fluke', type: 'H', positions: ['of'], proj: { pa: 1, ab: 1, obp: 0.500, slg: 0.900, hr: 1, r: 1 } };
    assert(hitterRateValue(paFluke) < hitterRateValue(paRaf),
      'hitterRateValue: a 1-PA fluke is ramped below a real regular');

    // Scaling: rates hold, counting stats shrink proportionally.
    var paScaled = scaleHitterUsage(paRaf, 100);
    assertEqual(paScaled._proj.pa, 100, 'scaleHitterUsage: PA set to the used amount');
    assertEqual(paScaled._proj.obp, 0.300, 'scaleHitterUsage: rate stats unchanged');
    assert(Math.abs(paScaled._proj.r - 22 * (100 / 213)) < 1e-9,
      'scaleHitterUsage: counting stats scale by the used fraction');
    assert(scaleHitterUsage(paRaf, 500) === paRaf,
      'scaleHitterUsage: asking for more than projected returns the player untouched');

    assert(paSlotBudget() > 0, 'paSlotBudget: positive');
```

- [ ] **Step 3: Run and verify**

Serve the repo and hard-refresh `http://localhost:8000/test.html` (invariant #7).
Expected: **147 passed, 0 failed** (140 + 7 new).

- [ ] **Step 4: Commit**

```bash
git add shared.js test.html
git commit -m "feat(lineup): rate-first ranking key + partial-usage scaling"
```

---

### Task 2: Slot supplementation in `optimizeHitterLineup`

**Files:**
- Modify: `shared.js` (`optimizeHitterLineup`, currently at ~line 830)

- [ ] **Step 1: Replace the function body**

Find:

```js
function optimizeHitterLineup(hitters) {
  const scored = hitters
    .filter(p => p.type === 'H')
    .map(p => {
      const b = p.proj || {};
      return { ...p, _proj: b, _value: (b.pa || 0) * ((b.obp || 0) + (b.slg || 0)) };
    })
    .sort((a, b) => b._value - a._value);

  const slots = [...HITTER_SLOTS].sort((a, b) =>
    scored.filter(p => a.eligible(p)).length - scored.filter(p => b.eligible(p)).length
  );

  const assignment = {};
  const used = new Set();
  for (const slot of slots) {
    const best = scored.find(p => slot.eligible(p) && !used.has(p.fgId || p.name));
    if (best) {
      assignment[slot.id] = best;
      used.add(best.fgId || best.name);
    }
  }
  return assignment;
}
```

Replace with:

```js
function optimizeHitterLineup(hitters) {
  const scored = hitters
    .filter(p => p.type === 'H')
    .map(p => {
      const b = p.proj || {};
      return { ...p, _proj: b, _value: hitterRateValue(p) };
    })
    .sort((a, b) => b._value - a._value);

  const slots = [...HITTER_SLOTS].sort((a, b) =>
    scored.filter(p => a.eligible(p)).length - scored.filter(p => b.eligible(p)).length
  );

  const budget = paSlotBudget();
  const assignment = {};
  const used = new Set();
  for (const slot of slots) {
    const best = scored.find(p => slot.eligible(p) && !used.has(p.fgId || p.name));
    if (!best) continue;
    assignment[slot.id] = best;                 // primary contributes his FULL projection
    used.add(best.fgId || best.name);

    // If an injured or part-time primary cannot fill the slot, a second eligible
    // bat absorbs the remaining plate appearances — the slot is shared, exactly
    // as it would be in a real daily lineup.
    const shortfall = budget - ((best._proj && best._proj.pa) || 0);
    if (shortfall < PA_MIN_SHARE) continue;
    const backup = scored.find(p => slot.eligible(p) && !used.has(p.fgId || p.name));
    if (!backup) continue;
    assignment[slot.id + '_2'] = scaleHitterUsage(backup, shortfall);
    used.add(backup.fgId || backup.name);
  }
  return assignment;
}
```

Each player is added to `used` when assigned, so no player occupies two slots and the
existing "no duplicate assignments" assertion still holds.

- [ ] **Step 2: Verify the existing suite did not regress**

Hard-refresh `http://localhost:8000/test.html`.
Expected: **147 passed, 0 failed** — unchanged.

The existing optimizer fixture uses 400-600 PA hitters against a ~196 PA budget, so every
shortfall is negative and no `_2` keys are created — those assertions must be untouched.
**If `optimizer: no duplicate assignments` fails, STOP**: a player is being assigned twice
and the `used` bookkeeping is wrong.

- [ ] **Step 3: Commit**

```bash
git add shared.js
git commit -m "feat(lineup): share a slot when the primary cannot fill its PA budget"
```

---

### Task 3: Verify the Judge/Soto case and measure suite-wide impact

**Files:**
- Create: `<scratchpad>/verify_lineup.js` (throwaway — do NOT commit)

- [ ] **Step 1: Write the harness**

```js
const fs = require('fs'), vm = require('vm'), path = require('path');
const REPO = 'C:/Users/bkami/Documents/OttoneuAI';
const read = f => fs.readFileSync(path.join(REPO, f), 'utf8');
const store = {};
const sb = { console,
  localStorage: { getItem: k => (k in store ? store[k] : null),
                  setItem: (k, v) => { store[k] = String(v); }, removeItem: k => { delete store[k]; } },
  fetch: () => Promise.reject(new Error('no network')), setTimeout, clearTimeout };
sb.window = sb; sb.globalThis = sb; vm.createContext(sb);
const L = console.log; console.log = () => {};
vm.runInContext(read('shared.js'), sb, { filename: 'shared.js' });
vm.runInContext(read('tradefinder.js'), sb, { filename: 'tradefinder.js' });
vm.runInContext('var __CATS = CATS;', sb);          // const does not attach to the sandbox global
const S = sb;
const roster = S.parseRosterCSV(read('data/roster.csv'));
const merged = S.matchPlayers(roster,
  S.parseHittingProjections(read('data/proj_hitting.csv')),
  S.parsePitchingProjections(read('data/proj_pitching.csv')));
console.log = L;

const byTeam = {};
merged.forEach(p => { if (p.team && p.team !== 'Free Agent') (byTeam[p.team] = byTeam[p.team] || []).push(p); });

console.log('SHARED SLOTS BY TEAM (a "_2" key means the primary could not fill the slot):');
let shared = 0;
Object.keys(byTeam).forEach(t => {
  const lu = S.optimizeHitterLineup(byTeam[t].filter(p => p.type === 'H'));
  const extras = Object.keys(lu).filter(k => k.indexOf('_2') > -1);
  shared += extras.length;
  if (extras.length) console.log('  ' + t.slice(0, 22).padEnd(23) + extras.map(k =>
    k.replace('_2', '') + '=' + (lu[k].rawName || lu[k].name) + '(' + Math.round(lu[k]._proj.pa) + 'PA)').join(', '));
});
console.log('  total shared slots: ' + shared);

console.log('');
console.log('ARE JUDGE AND SOTO NOW IN THEIR LINEUPS?');
['Aaron Judge', 'Juan Soto'].forEach(n => {
  const t = Object.keys(byTeam).find(x => byTeam[x].some(p => (p.rawName || p.name) === n));
  if (!t) { console.log('  ' + n + ': not rostered'); return; }
  const lu = S.optimizeHitterLineup(byTeam[t].filter(p => p.type === 'H'));
  const slot = Object.keys(lu).find(k => (lu[k].rawName || lu[k].name) === n);
  console.log('  ' + n.padEnd(12) + (slot ? 'STARTS in ' + slot : 'still benched') + '  (' + t.slice(0, 20) + ')');
});

// Marginal values now?
console.log('');
const budget = S.tfIpBudget();
const den = S.calcSGPDenoms(Object.keys(byTeam).map(t => S.tfTeamStats(byTeam[t], budget)));
const all = S.tfAllMarginals(byTeam, den, budget);
['Aaron Judge', 'Juan Soto'].forEach(n => {
  const t = Object.keys(byTeam).find(x => byTeam[x].some(p => (p.rawName || p.name) === n));
  if (!t) return;
  const p = byTeam[t].find(q => (q.rawName || q.name) === n);
  console.log('  ' + n.padEnd(12) + ' marginal $' + (all[t][p.fgId || p.name] || 0).toFixed(1));
});

console.log('');
console.log = () => {};
const vm0 = S.calculateAllValues(Object.keys(byTeam).map(t => byTeam[t]));
console.log = L;
const vals = Object.keys(vm0).map(k => vm0[k].projectedValue || 0);
console.log('Y0 ANCHOR CHECK: sum $' + vals.reduce((a, b) => a + b, 0).toFixed(0) +
            ' | max $' + Math.max.apply(null, vals).toFixed(1) +
            ' | at $1 floor ' + vals.filter(v => v <= 1.001).length + '/' + vals.length);
```

- [ ] **Step 2: Run and check**

```bash
node "<scratchpad>/verify_lineup.js"
```

Sanity checks — if any fails, STOP and report:
- **Judge and Soto now START.** That is the whole point of the change.
- **Their marginal is no longer $0.** They should carry real positive marginal value.
- **Shared slots are the minority.** Most teams field healthy full-timers; a large number of
  `_2` keys means `PA_PER_SLOT` is set too high and is manufacturing phantom playing time.
- **Y0 total still sums to ~$4800.** The pool is fixed by construction; if it moved, the
  change leaked somewhere it should not have.

- [ ] **Step 3: Record the before/after for the commit message.** No commit for the harness.

---

### Task 4: Update MODEL.md

**Files:**
- Modify: `MODEL.md` §3 (the "hitting needs no volume cap" claim), §6 (knobs), §8 (limitation now resolved)

- [ ] **Step 1: Correct the §3 claim**

In `MODEL.md` §3, find the sentence stating hitting needs no volume cap (one hitter per
active slot) and replace that clause with:

```markdown
Hitting now uses a PA budget per active slot (`PA_PER_SLOT` × proration): the primary
occupant contributes his full projection, and when injury or part-time usage leaves the
slot short by more than `PA_MIN_SHARE`, a second eligible bat absorbs the remainder as a
scaled clone. This mirrors the pitching side's innings budget. The earlier "one hitter per
active slot" rule silently discarded injured stars — Aaron Judge and Juan Soto were being
dropped from their lineups entirely.
```

- [ ] **Step 2: Add the knobs to §6**

```markdown
| `PA_PER_SLOT` | shared.js | 650 | full-season PA one lineup slot absorbs (prorated for RoS) |
| `PA_FULL_RATE` | shared.js | 50 | PA below which a hitter's rate is ramped down as a partial sample |
| `PA_MIN_SHARE` | shared.js | 30 | shortfall below which a slot is not supplemented |
```

- [ ] **Step 3: Move the §8 limitation to resolved**

Replace the `optimizeHitterLineup is volume-biased` limitation in §8 with a short resolved
note recording what it was and where the fix lives:

```markdown
- ~~`optimizeHitterLineup` volume bias~~ — **RESOLVED.** It ranked by `pa × (obp+slg)`, so
  injured stars were benched behind healthy mediocrities (Judge .971 OPS/97 PA behind
  Rafaela .711/213 PA) and dropped from team aggregation entirely. Two defects: misranking
  (~$13.7) and the either/or slot assumption (~$25.4). Fixed by rate-first ranking plus
  slot supplementation — see §3 and the `PA_*` knobs in §6.
```

- [ ] **Step 4: Commit**

```bash
git add MODEL.md
git commit -m "docs(model): PA-budget lineup replaces one-hitter-per-slot"
```

---

## Definition of done

- `test.html` reports **147 passed, 0 failed**.
- Judge and Soto start for their teams and carry non-zero marginal value.
- Shared slots are a minority of the 144 league-wide slots.
- Y0 values still sum to ~$4800.
- MODEL.md §3, §6, §8 updated.

## Risk

This changes team aggregation, so it moves **every Y0 value** and therefore the SGP
denominators, dynasty values, and every page. That is intended — teams with injured stars
were being undercounted. Verify the anchors in §2 (hitShare ≈ 50%, top hitter, ~35% at the
$1 floor) and expect modest movement, not upheaval. Report before/after rather than
asserting "no change".
