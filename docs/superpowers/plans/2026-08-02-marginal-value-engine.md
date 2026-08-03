# Marginal-Value Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure what a player is worth **to a specific roster** (does he crack the optimized lineup, and what is the drop-off behind him?), so the trade finder can find players who are blocked on one roster and needed on another.

**Architecture:** A new pure module `tradefinder.js` re-runs the existing `optimizeHitterLineup` / `selectPitchers` / `computeTeamStats` machinery with one player removed, and scores the delta in SGP-denominator units (category stdevs) converted to dollars at the same `$15/point` rate `targets.html` already uses. No UI and no `targets.html` changes in this plan.

**Tech stack:** Vanilla browser JS (no build). Unit tests in `test.html`. Live-data verification runs headlessly in Node (the in-app browser's fetch proxy caps responses ~400KB and `proj_pitching.csv` is 438KB, so browser verification of valuation pages is not possible here).

**Source spec:** [docs/superpowers/specs/2026-08-02-trade-finder-redesign.md](../specs/2026-08-02-trade-finder-redesign.md) — implements **Fix 2** only. Fix 1 shipped (commits a4d1e15…9c0ebab). The archetype generator is a later plan.

**Note on commits:** Commit locally after each task. NEVER `git push` — the user pushes via GitHub Desktop.

**Baseline:** `test.html` currently reports **127 passed, 0 failed**. Every task must keep failed at 0.

**Key constants already in `shared.js`:** `CATS` (8 categories), `LOWER_BETTER` (ERA/WHIP/HR9), `IP_MAX` 1500, `IP_MIN` 400, `rosProrationFactor()`, `calcSGPDenoms(teamStatsArr)`.

---

### Task 1: `tradefinder.js` — team stats + marginal delta

**Files:**
- Create: `tradefinder.js`
- Modify: `test.html` (add `<script src="tradefinder.js"></script>` after the `hotboard.js` tag; add a test block before `── Summary ──`)

- [ ] **Step 1: Create `tradefinder.js`**

```js
/* tradefinder.js — marginal value of a player TO A SPECIFIC ROSTER.
 *
 * The trade finder's core defect was ranking candidates by ABSOLUTE value.
 * A 6th outfielder who never cracks the 12 active slots has high absolute
 * value and near-zero value to his owner; to a team with a hole he is worth
 * full freight. That gap is where realistic trades live.
 *
 * Depends on shared.js (CATS, LOWER_BETTER, IP_MAX, IP_MIN,
 * optimizeHitterLineup, selectPitchers, computeTeamStats). Load shared.js first.
 */

// $ per standings point. Matches PTS_DOLLARS in targets.html — 1 category
// stdev ≈ 1 expected rank with 12 teams, so z-units convert at this rate.
var TF_PTS_DOLLARS = 15;

// Rest-of-season innings budget, honoring the 1,500 IP league cap (invariant #2).
function tfIpBudget() {
  return IP_MAX * Math.max(rosProrationFactor(), 0.1);
}

// Optimize a roster and return its category totals.
function tfTeamStats(roster, ipBudget, minValidIP) {
  var budget = ipBudget || tfIpBudget();
  var lineup = optimizeHitterLineup(roster.filter(function (p) { return p.type === 'H'; }));
  var pit    = selectPitchers(roster.filter(function (p) { return p.type === 'P'; }), budget);
  var floor  = (minValidIP != null) ? minValidIP : Math.min(IP_MIN, budget * 0.5);
  return computeTeamStats(lineup, pit, floor);
}

// Signed delta between a full roster and the same roster minus one player,
// expressed in SGP-denominator units (category stdevs). Category means cancel
// in the subtraction, so summing across categories is meaningful here even
// though an absolute team "z" would not be.
function tfMarginalZ(baseStats, cutStats, denoms) {
  var z = 0;
  CATS.forEach(function (c) {
    // computeTeamStats zeroes the pitching categories below the IP floor. If
    // removing a player flips that validity, the pitching deltas are phantom
    // (a 4.40 ERA "improving" to 0.00), so skip them rather than emit garbage.
    var isPit = (c === 'ERA' || c === 'WHIP' || c === 'HR9' || c === 'SO');
    if (isPit && baseStats._pitchingValid !== cutStats._pitchingValid) return;
    var d = denoms[c] || 1;
    var delta = ((baseStats[c] || 0) - (cutStats[c] || 0)) / d;
    z += LOWER_BETTER.has(c) ? -delta : delta;
  });
  return z;
}
```

- [ ] **Step 2: Wire into `test.html` and add the failing tests**

Add `<script src="tradefinder.js"></script>` immediately after the `hotboard.js` script tag. Then insert this block immediately before the `// ── Summary ──` comment:

```js
    // ── tradefinder: marginal delta ──────────────────────────────────────────
    section('Marginal value');
    var tfDen = { OBP: 0.010, SLG: 0.020, HR: 10, R: 40, ERA: 0.20, WHIP: 0.040, HR9: 0.10, SO: 80 };
    var tfBase = { OBP: 0.330, SLG: 0.430, HR: 200, R: 700, ERA: 3.80, WHIP: 1.200, HR9: 1.10, SO: 1300,
                   _pitchingValid: true };

    // Removing a hitter lowers HR/R → the player's marginal contribution is positive.
    var tfCutHitter = { OBP: 0.330, SLG: 0.430, HR: 180, R: 660, ERA: 3.80, WHIP: 1.200, HR9: 1.10, SO: 1300,
                        _pitchingValid: true };
    assert(tfMarginalZ(tfBase, tfCutHitter, tfDen) > 0, 'tfMarginalZ: removing a productive hitter → positive marginal');

    // A player whose removal changes nothing is worth nothing to that roster.
    assertEqual(tfMarginalZ(tfBase, tfBase, tfDen), 0, 'tfMarginalZ: blocked player (no change) → zero marginal');

    // ERA is lower-better: base 3.80 vs cut 4.00 means the player IMPROVED the
    // team ERA, so his marginal must be positive.
    var tfCutPitcher = { OBP: 0.330, SLG: 0.430, HR: 200, R: 700, ERA: 4.00, WHIP: 1.200, HR9: 1.10, SO: 1300,
                         _pitchingValid: true };
    assert(tfMarginalZ(tfBase, tfCutPitcher, tfDen) > 0, 'tfMarginalZ: lower-better ERA handled with correct sign');

    // A player who actively hurts the team scores negative.
    var tfCutBad = { OBP: 0.330, SLG: 0.430, HR: 210, R: 720, ERA: 3.80, WHIP: 1.200, HR9: 1.10, SO: 1300,
                     _pitchingValid: true };
    assert(tfMarginalZ(tfBase, tfCutBad, tfDen) < 0, 'tfMarginalZ: removing him IMPROVES the team → negative marginal');

    // Pitching-validity flip must not emit a phantom gain.
    var tfCutInvalid = { OBP: 0.330, SLG: 0.430, HR: 180, R: 660, ERA: 0, WHIP: 0, HR9: 0, SO: 0,
                         _pitchingValid: false };
    var tfZFlip = tfMarginalZ(tfBase, tfCutInvalid, tfDen);
    var tfZHitOnly = tfMarginalZ(
      { OBP: 0.330, SLG: 0.430, HR: 200, R: 700, _pitchingValid: true },
      { OBP: 0.330, SLG: 0.430, HR: 180, R: 660, _pitchingValid: true },
      tfDen);
    assert(Math.abs(tfZFlip - tfZHitOnly) < 1e-9,
      'tfMarginalZ: pitching-validity flip skips pitching cats, no phantom delta');
```

- [ ] **Step 3: Run tests to verify they fail**

Start the server (or reuse a running one):

```bash
python -m http.server 8000
```

Open `http://localhost:8000/test.html` and hard-refresh (Ctrl+Shift+R).
Expected: the run halts at the `── Marginal value ──` header with an empty summary —
`tfMarginalZ` is not yet defined, which throws a ReferenceError. (This is the same
failure shape Fix 1's Task 1 produced.)

**Note:** Step 1 already wrote the implementation, so if the script tag is in place these
will pass immediately. To see the genuine red, comment out the `tradefinder.js` script tag,
observe the halt, then restore it.

- [ ] **Step 4: Run tests to verify they pass**

Hard-refresh `http://localhost:8000/test.html`.
Expected: green summary reading **132 passed, 0 failed** (127 baseline + 5 new).

- [ ] **Step 5: Commit**

```bash
git add tradefinder.js test.html
git commit -m "feat(trade): marginal delta in SGP-denominator units"
```

---

### Task 2: Per-roster marginals and blockedness

**Files:**
- Modify: `tradefinder.js`
- Modify: `test.html`

- [ ] **Step 1: Add the functions**

Append to `tradefinder.js`:

```js
function tfKey(p) { return p.fgId || p.name; }

// Marginal DOLLARS for every player on one roster. Computes the team's baseline
// once, then re-optimizes with each player removed in turn.
// Returns { playerKey: dollars }.
function tfRosterMarginals(roster, denoms, ipBudget) {
  var budget = ipBudget || tfIpBudget();
  var base   = tfTeamStats(roster, budget);
  var out    = {};
  roster.forEach(function (p) {
    var key = tfKey(p);
    var without = roster.filter(function (q) { return tfKey(q) !== key; });
    out[key] = tfMarginalZ(base, tfTeamStats(without, budget), denoms) * TF_PTS_DOLLARS;
  });
  return out;
}

// Marginals for every team. rostersByTeam: { teamName: [players] }.
// Returns { teamName: { playerKey: dollars } }.
function tfAllMarginals(rostersByTeam, denoms, ipBudget) {
  var budget = ipBudget || tfIpBudget();
  var out = {};
  Object.keys(rostersByTeam).forEach(function (t) {
    out[t] = tfRosterMarginals(rostersByTeam[t], denoms, budget);
  });
  return out;
}

// Value stranded on the bench: what he is worth in the abstract minus what he
// is worth to the roster he is actually on. High = trade asset.
// NOTE: compares against projValue (Y0 dollars) because marginals are derived
// from Y0 production. Do NOT mix dynastyValue into this subtraction — the
// dynasty lens enters later, at the fairness/utility stage.
function tfBlockedness(player, ownerMarginals, valueMap) {
  var key = tfKey(player);
  var abs = (valueMap[key] && valueMap[key].projectedValue) || 0;
  return abs - (ownerMarginals[key] || 0);
}

// How much MORE a player is worth to team B than to his current team A.
// This is the quantity that makes a trade mutually attractive.
function tfGain(player, marginalsA, marginalsB) {
  var key = tfKey(player);
  return (marginalsB[key] || 0) - (marginalsA[key] || 0);
}
```

- [ ] **Step 2: Add the failing tests**

Insert before `// ── Summary ──` in `test.html`:

```js
    // Fixture roster: 3 clearly-better outfielders plus a blocked 4th.
    function tfHit(name, obp, slg, hr, r) {
      return { name: name, fgId: name, type: 'H', positions: ['of'],
               proj: { pa: 600, ab: 540, obp: obp, slg: slg, hr: hr, r: r } };
    }
    var tfStar1 = tfHit('Star One',   0.400, 0.560, 40, 100);
    var tfStar2 = tfHit('Star Two',   0.390, 0.550, 38, 98);
    var tfStar3 = tfHit('Star Three', 0.385, 0.545, 36, 96);
    var tfScrub = tfHit('Blocked Guy', 0.300, 0.350, 5, 30);
    // These players are OF-only, so they can fill just OF1-5 + UTIL = 6 slots
    // (C/1B/2B/SS/3B/MI require other eligibility and stay empty). 15 players
    // rank ahead of the scrub, so he is guaranteed not to start.
    var tfFill = [];
    for (var tfi = 0; tfi < 12; tfi++) tfFill.push(tfHit('Filler ' + tfi, 0.360, 0.480, 25, 80));
    var tfRoster = [tfStar1, tfStar2, tfStar3].concat(tfFill).concat([tfScrub]);
    var tfMarg = tfRosterMarginals(tfRoster, tfDen, 400);

    assert(tfMarg['Blocked Guy'] === 0,
      'tfRosterMarginals: player who never cracks the lineup has zero marginal');
    assert(tfMarg['Star One'] > 0,
      'tfRosterMarginals: a starter has positive marginal value');

    // Blockedness: the scrub strands whatever absolute value he carries.
    var tfVals = { 'Blocked Guy': { projectedValue: 12 }, 'Star One': { projectedValue: 40 } };
    assertEqual(tfBlockedness(tfScrub, tfMarg, tfVals), 12,
      'tfBlockedness: blocked player strands his full absolute value');
    assert(tfBlockedness(tfStar1, tfMarg, tfVals) < 40,
      'tfBlockedness: a starter strands less than his absolute value');

    // Gain: worth more to a team that would actually start him.
    var tfThin = { 'Blocked Guy': 9 };
    assertEqual(tfGain(tfScrub, tfMarg, tfThin), 9,
      'tfGain: blocked here, valuable there → positive gain');
```

- [ ] **Step 3: Run tests to verify they pass**

Hard-refresh `http://localhost:8000/test.html`.
Expected: **137 passed, 0 failed** (132 + 5 new).

If `tfMarg['Blocked Guy']` is not exactly 0, the scrub is somehow reaching the lineup —
check that `tfFill` produces 12 fillers (so 15 hitters outrank him for the 6 OF/UTIL slots)
and that `optimizeHitterLineup` ranks by `pa × (obp + slg)`, which the scrub's 0.300/0.350
line must lose on.

- [ ] **Step 4: Commit**

```bash
git add tradefinder.js test.html
git commit -m "feat(trade): per-roster marginals, blockedness, cross-team gain"
```

---

### Task 3: Need gaps (which lineup slots are holes)

**Files:**
- Modify: `tradefinder.js`
- Modify: `test.html`

- [ ] **Step 1: Add the functions**

Append to `tradefinder.js`:

```js
var TF_BLOCK_MIN = 5;   // $ stranded before a player counts as a surplus asset
var TF_NEED_MIN  = 5;   // $ below the league median before a slot counts as a hole
var TF_GAIN_MIN  = 5;   // $ a player must gain by moving before it is worth proposing

// Which player currently occupies each hitter slot, per team.
// Returns { teamName: { slotId: player } }.
function tfSlotOccupants(rostersByTeam) {
  var out = {};
  Object.keys(rostersByTeam).forEach(function (t) {
    out[t] = optimizeHitterLineup(rostersByTeam[t].filter(function (p) { return p.type === 'H'; }));
  });
  return out;
}

function tfMedian(arr) {
  if (!arr.length) return 0;
  var s = arr.slice().sort(function (a, b) { return a - b; });
  var m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

// A slot is a NEED when its occupant contributes materially less than the
// league-median occupant of that same slot. Self-relative — no external
// baseline required, same principle as the SGP denominators.
// Returns { teamName: { slotId: gapDollars } }, positive = hole.
function tfNeedGaps(rostersByTeam, allMarginals) {
  var occ = tfSlotOccupants(rostersByTeam);
  var teams = Object.keys(rostersByTeam);
  var slotIds = {};
  teams.forEach(function (t) { Object.keys(occ[t]).forEach(function (s) { slotIds[s] = 1; }); });

  var medians = {};
  Object.keys(slotIds).forEach(function (slot) {
    var vals = [];
    teams.forEach(function (t) {
      var p = occ[t][slot];
      if (p) vals.push((allMarginals[t] || {})[tfKey(p)] || 0);
    });
    medians[slot] = tfMedian(vals);
  });

  var out = {};
  teams.forEach(function (t) {
    out[t] = {};
    Object.keys(slotIds).forEach(function (slot) {
      var p = occ[t][slot];
      var mine = p ? ((allMarginals[t] || {})[tfKey(p)] || 0) : 0;
      out[t][slot] = medians[slot] - mine;   // empty slot → full median gap
    });
  });
  return out;
}
```

- [ ] **Step 2: Add the failing tests**

Insert before `// ── Summary ──` in `test.html`:

```js
    // Two identical teams plus one with a hole at catcher.
    function tfC(name, obp, slg, hr, r) {
      var p = tfHit(name, obp, slg, hr, r); p.positions = ['c']; return p;
    }
    function tfTeam(prefix, catcher) {
      var arr = [catcher];
      for (var i = 0; i < 12; i++) arr.push(tfHit(prefix + ' OF' + i, 0.360, 0.480, 25, 80));
      return arr;
    }
    var tfRostersByTeam = {
      Alpha: tfTeam('A', tfC('A C', 0.370, 0.500, 28, 85)),
      Bravo: tfTeam('B', tfC('B C', 0.370, 0.500, 28, 85)),
      Delta: tfTeam('D', tfC('D C', 0.270, 0.300, 2, 20)),   // the hole
    };
    var tfAll = tfAllMarginals(tfRostersByTeam, tfDen, 400);
    var tfGaps = tfNeedGaps(tfRostersByTeam, tfAll);

    assert(tfGaps.Delta.C > tfGaps.Alpha.C,
      'tfNeedGaps: the team with a weak catcher shows the larger gap at C');
    assert(Math.abs(tfGaps.Alpha.C) < 0.01,
      'tfNeedGaps: a median-strength slot shows ~zero gap');
    assert(typeof TF_BLOCK_MIN === 'number' && typeof TF_NEED_MIN === 'number' &&
           typeof TF_GAIN_MIN === 'number', 'tradefinder: tunable thresholds exported');
```

- [ ] **Step 3: Run tests to verify they pass**

Hard-refresh `http://localhost:8000/test.html`.
Expected: **140 passed, 0 failed** (137 + 3 new).

- [ ] **Step 4: Commit**

```bash
git add tradefinder.js test.html
git commit -m "feat(trade): slot-level need gaps vs league median"
```

---

### Task 4: Live-data verification and performance

The in-app browser cannot load `proj_pitching.csv` (438KB vs a ~400KB proxy cap), so this
runs in Node against the real CSVs. This is the same harness pattern Fix 1 used.

**Files:**
- Create: `scratchpad/verify_marginal.js` (throwaway — do NOT commit)

- [ ] **Step 1: Write the harness**

Create it in the session scratchpad directory (not the repo):

```js
const fs = require('fs'), vm = require('vm'), path = require('path');
const REPO = 'C:/Users/bkami/Documents/OttoneuAI';
const read = f => fs.readFileSync(path.join(REPO, f), 'utf8');
const store = {};
const sb = { console,
  localStorage: { getItem: k => (k in store ? store[k] : null),
                  setItem: (k, v) => { store[k] = String(v); },
                  removeItem: k => { delete store[k]; } },
  fetch: () => Promise.reject(new Error('no network')), setTimeout, clearTimeout };
sb.window = sb; sb.globalThis = sb; vm.createContext(sb);
const L = console.log; console.log = () => {};
vm.runInContext(read('shared.js'), sb, { filename: 'shared.js' });
vm.runInContext(read('tradefinder.js'), sb, { filename: 'tradefinder.js' });
const S = sb;
const roster = S.parseRosterCSV(read('data/roster.csv'));
const merged = S.matchPlayers(roster,
  S.parseHittingProjections(read('data/proj_hitting.csv')),
  S.parsePitchingProjections(read('data/proj_pitching.csv')));
console.log = L;

const byTeam = {};
merged.forEach(p => { if (p.team && p.team !== 'Free Agent') (byTeam[p.team] = byTeam[p.team] || []).push(p); });

// SGP denominators from the 12 optimized team stat lines.
const budget = S.tfIpBudget();
const statsArr = Object.keys(byTeam).map(t => S.tfTeamStats(byTeam[t], budget));
const denoms = S.calcSGPDenoms(statsArr);

const t0 = Date.now();
const all = S.tfAllMarginals(byTeam, denoms, budget);
const ms = Date.now() - t0;

let n = 0; Object.keys(all).forEach(t => { n += Object.keys(all[t]).length; });
console.log('PERFORMANCE: ' + n + ' marginals across ' + Object.keys(byTeam).length +
            ' teams in ' + ms + 'ms  (' + (ms / n).toFixed(2) + 'ms each)');

// Valuation for blockedness.
console.log = () => {};
const vm0 = S.calculateAllValues(Object.keys(byTeam).map(t => byTeam[t]));
console.log = L;
const byKey = {}; merged.forEach(p => { const k = p.fgId || p.name; if (k) byKey[k] = p; });

const rows = [];
Object.keys(byTeam).forEach(t => byTeam[t].forEach(p => {
  const k = p.fgId || p.name;
  rows.push({ name: p.rawName || p.name, team: t, type: p.type,
              marg: all[t][k] || 0,
              abs: (vm0[k] && vm0[k].projectedValue) || 0,
              blocked: S.tfBlockedness(p, all[t], vm0) });
}));

console.log('');
console.log('MOST BLOCKED (high absolute value, low value to their own roster):');
rows.filter(r => r.abs > 5).sort((a, b) => b.blocked - a.blocked).slice(0, 15)
  .forEach(r => console.log('  ' + r.name.padEnd(22) + ' ' + r.team.slice(0, 16).padEnd(17) +
    ' abs $' + r.abs.toFixed(1).padStart(5) + '  marginal $' + r.marg.toFixed(1).padStart(6) +
    '  stranded $' + r.blocked.toFixed(1)));

console.log('');
const zero = rows.filter(r => r.marg === 0).length;
console.log('players with ZERO marginal (do not crack the lineup): ' + zero + '/' + rows.length +
            ' = ' + (100 * zero / rows.length).toFixed(0) + '%');
```

- [ ] **Step 2: Run it and check the results**

```bash
node "<scratchpad>/verify_marginal.js"
```

Sanity checks — if any fails, STOP and report:
- **Performance under ~3s total.** If slower, switch `targets.html` (next plan) to compute
  marginals lazily per opponent card instead of eagerly for all 12 teams.
- **Zero-marginal share is substantial but not universal** — rosters carry ~43 players for
  12 hitter slots plus a capped pitching staff, so a large bench fraction scoring exactly 0
  is correct. If it is 0% or 100%, the removal loop or the lineup optimizer is wrong.
- **The most-blocked list reads plausibly** — it should be genuinely good players stuck
  behind better ones at the same position, not random scrubs. Scrubs have low absolute
  value so they cannot strand much.

- [ ] **Step 3: Record findings**

No commit (the harness stays in the scratchpad). Note the timing and the top blocked
players; the archetype generator plan will use them as fixtures.

---

### Task 5: Update MODEL.md

**Files:**
- Modify: `MODEL.md` §5 (trade finder), §6 (knob table)

- [ ] **Step 1: Add a marginal-value bullet to §5**

Insert at the top of the `## 5. Trade finder (targets.html)` bullet list:

```markdown
- **Marginal value (`tradefinder.js`).** A player's worth is measured AGAINST A
  SPECIFIC ROSTER: re-optimize the lineup with him removed and score the delta in
  SGP-denominator units, converted at `TF_PTS_DOLLARS` ($15/point, matching
  `PTS_DOLLARS`). `tfBlockedness` = absolute Y0 value − marginal value to his own
  team, so a blocked 6th outfielder reads as a trade asset. `tfNeedGaps` compares
  each lineup slot's occupant against the league-median occupant of that slot
  (self-relative, like the SGP denominators). Compare blockedness against
  **`projValue`, never `dynastyValue`** — marginals derive from Y0 production; the
  dynasty lens enters later at the fairness/utility stage.
```

- [ ] **Step 2: Add the knobs to the §6 table**

Append these rows to the tunable-knobs table in `MODEL.md` §6:

```markdown
| `TF_PTS_DOLLARS` | tradefinder.js | 15 | $ per standings point; keep in sync with `PTS_DOLLARS` |
| `TF_BLOCK_MIN` | tradefinder.js | 5 | $ stranded before a player is a surplus asset |
| `TF_NEED_MIN` | tradefinder.js | 5 | $ below median before a slot is a hole |
| `TF_GAIN_MIN` | tradefinder.js | 5 | $ a player must gain by moving to be worth proposing |
```

- [ ] **Step 3: Commit**

```bash
git add MODEL.md
git commit -m "docs(model): marginal-value engine in section 5 + tradefinder knobs"
```

---

## Definition of done

- `test.html` reports **140 passed, 0 failed**.
- `tradefinder.js` exists and is loaded by `test.html`.
- Node harness runs under ~3s with a plausible most-blocked list.
- MODEL.md §5 and §6 updated.
- `targets.html` is **untouched** — wiring happens in the generator plan.

## Out of scope (next plan)

- Archetype generation (logjam/hole, rental/salary-dump, buy-now/sell-future, consolidation).
- `targets.html` rewiring and reason display.
- **Rental gating:** `holdHorizon === 0` alone does NOT identify a rental target — ~half of
  the 324 H0 players are $1-3 fringe. The rental archetype must also require meaningful Y0
  value (see MODEL.md §4).
