# Standings Finish Odds Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Finish Odds" panel to `standings.html` giving each team's % chance to finish 1st/2nd/3rd/top 3 (this season and next season), with data-driven paths to 1st and to the top 3.

**Architecture:** A new pure-function module `standingsim.js` runs a seeded team-level Monte Carlo: each run adds luck + projection-error noise to every team's projected category stats, blends with current actuals via the existing `blendStats` (this season) or uses the projection whole (next season), and ranks with the existing `buildStandings`. `standings.html` builds the inputs and renders the panel. Spec: `docs/superpowers/specs/2026-09-19-standings-odds-design.md`.

**Tech Stack:** Plain browser JS (no build, no modules — globals across `<script>` tags), existing `test.html` harness, Python `http.server` preview named `test` in `.claude/launch.json`.

---

## Context the implementer needs

- `shared.js` globals used here: `CATS` (`["OBP","SLG","HR","R","ERA","WHIP","HR9","SO"]`), `LOWER_BETTER` (Set of ERA/WHIP/HR9), `IP_MAX` (1500), `PA_PER_SLOT` (650), `blendStats(curr, proj)`, `buildStandings(teams)` (input `[{name, stats}]`, output sorted by `points` desc, each with `ranks[cat]` = category points, 12 best), `optimizeHitterLineup`, `selectPitchers`, `computeTeamStats` (returns `OBP SLG HR R ERA WHIP HR9 SO _ip _totPA _totAB _pitchingValid`), `matchPlayers`, `attachYearProjections`, `loadData`, `hasRows`, `cloneForYear` (top-level after Task 1). `standingsim.js` adds `SIM_*` constants and `sim*` functions as new globals.
- Browser caches `.js` files aggressively (MODEL.md invariant #7). The test-run procedure below force-refreshes them.
- Rendering convention: `textContent` / `createElement` only. Never `innerHTML` with data.
- Commits: local only, never push. End each message with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Running the tests (used by every task)

1. Start the preview if not running: `mcp__Claude_Browser__preview_start` with `{ "name": "test" }`.
2. In that tab, run (javascript_tool):
   ```js
   Promise.all(['shared.js','standingsim.js','test.html'].map(f => fetch(f, {cache:'reload'})))
     .then(() => location.replace('test.html?v=' + Date.now())); 'reloading'
   ```
3. Then run:
   ```js
   document.getElementById('summary').textContent + ' || ' +
     ((document.body.innerText.match(/✗[^\n]*/g) || ['no failures']).join(' | '))
   ```
Baseline before this plan: `216 passed, 0 failed`.

## File map

| File | Change | Responsibility |
|---|---|---|
| `standingsim.js` | Create | Engine: RNG, noise model, one-run draw, place spans, path accumulation, `simulateStandings` |
| `test.html` | Modify | Load `standingsim.js`; three new test sections |
| `shared.js` | Modify | Hoist `yearProjP` + `cloneForYear` to top level (no behavior change) |
| `standings.html` | Modify | `projectTeam` helper (shared by table and odds), odds inputs, Finish Odds panel, toggle |
| `MODEL.md` | Modify | New §3b; knob-table rows |

---

### Task 1: Hoist `cloneForYear` to top level

**Files:**
- Modify: `shared.js:749-776`

- [ ] **Step 1: Move the two helpers out of `calculateDynastyValues`**

Replace this block (currently starting at `shared.js:749`):

```js
// Computes dynasty value by running the SGP model across up to three projection
// years and combining with weighted discounting.
// weights: { y1: 0.90, y2: 0.81 }  (defaults; pass null to use Y0 only)
// Players with no Y1/Y2 projection simply contribute 0 for that year.
function calculateDynastyValues(allRosters, weights, extraPlayers) {
  const w1 = weights ? (weights.y1 || 0) : 0;
  const w2 = weights ? (weights.y2 || 0) : 0;

  // Helper: clone rosters swapping proj → a different year's projection.
  // fbKey (optional) is a fallback year used when the primary year is missing:
  // Y2 projection files cover only ~half the league (almost no pitchers), so a
  // player with a Y1 line but no Y2 line reuses Y1 — the w2 weight already
  // discounts it. Without this, every ace contributed $0 for Y2 AND the fixed
  // pool spread over half as many players, inflating everyone who remained.
  // Also forward projP from the year-specific pitching field so two-way players
  // (Ohtani) get the correct pitching projection for each dynasty year, not Y0's.
  function yearProjP(p, yearKey, fbKey) {
    if (p[yearKey + '_P'] != null) return p[yearKey + '_P'];
    if (fbKey && p[fbKey + '_P'] != null) return p[fbKey + '_P'];
    return p[yearKey + '_P'] !== undefined ? p[yearKey + '_P'] : p.projP;
  }
  function cloneForYear(rosters, yearKey, fbKey) {
    return rosters.map(r => r.map(p => ({
      ...p,
      proj:  p[yearKey] || (fbKey ? p[fbKey] : null) || null,
      projP: yearProjP(p, yearKey, fbKey),
    })));
  }
```

with:

```js
// Clone rosters swapping proj → a different year's projection. Top-level so
// the standings odds simulator's Next Season mode reuses the exact cloning the
// dynasty values use (including the two-way pitching line) instead of a copy.
// fbKey (optional) is a fallback year used when the primary year is missing:
// Y2 projection files cover only ~half the league (almost no pitchers), so a
// player with a Y1 line but no Y2 line reuses Y1 — the w2 weight already
// discounts it. Without this, every ace contributed $0 for Y2 AND the fixed
// pool spread over half as many players, inflating everyone who remained.
// Also forward projP from the year-specific pitching field so two-way players
// (Ohtani) get the correct pitching projection for each dynasty year, not Y0's.
function yearProjP(p, yearKey, fbKey) {
  if (p[yearKey + '_P'] != null) return p[yearKey + '_P'];
  if (fbKey && p[fbKey + '_P'] != null) return p[fbKey + '_P'];
  return p[yearKey + '_P'] !== undefined ? p[yearKey + '_P'] : p.projP;
}
function cloneForYear(rosters, yearKey, fbKey) {
  return rosters.map(r => r.map(p => ({
    ...p,
    proj:  p[yearKey] || (fbKey ? p[fbKey] : null) || null,
    projP: yearProjP(p, yearKey, fbKey),
  })));
}

// Computes dynasty value by running the SGP model across up to three projection
// years and combining with weighted discounting.
// weights: { y1: 0.90, y2: 0.81 }  (defaults; pass null to use Y0 only)
// Players with no Y1/Y2 projection simply contribute 0 for that year.
function calculateDynastyValues(allRosters, weights, extraPlayers) {
  const w1 = weights ? (weights.y1 || 0) : 0;
  const w2 = weights ? (weights.y2 || 0) : 0;
```

`cloneExtras` stays inside `calculateDynastyValues`; it now calls the top-level `yearProjP`.

- [ ] **Step 2: Run the suite** (see "Running the tests")

Expected: `216 passed, 0 failed || no failures` — pure refactor.

- [ ] **Step 3: Commit**

```bash
git add shared.js
git commit -m "refactor(shared): hoist cloneForYear to top level for reuse

The standings odds simulator's Next Season mode needs the same Y1 roster
cloning the dynasty values use, including the two-way pitching line.
Moving the helper out of calculateDynastyValues lets it reuse that logic
instead of copying it. No behavior change.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Engine primitives — RNG, playing-time period, luck SDs

**Files:**
- Create: `standingsim.js`
- Modify: `test.html:20` (script tag) and `test.html` before `// ── Summary`

- [ ] **Step 1: Load the module and add the primitives tests**

In `test.html`, after `<script src="tradefinder.js"></script>` add:

```html
  <script src="standingsim.js"></script>
```

Immediately before the line `    // ── Summary ──────────────────────────────────────────────────────────────`, add:

```js
    // ── Standings finish odds (standingsim.js) ───────────────────────────────
    // Shared fixtures for the three standings-sim sections.
    const SIM_AVG = { OBP: .330, SLG: .420, HR: 230, R: 850, ERA: 3.90, WHIP: 1.22, HR9: 1.15, SO: 1300 };
    function simAvg(extra) { return Object.assign({}, SIM_AVG, extra || {}); }
    function simTeam(name, s) {
      return { name: name, curr: null, proj: {
        OBP: s.OBP, SLG: s.SLG, HR: s.HR, R: s.R, ERA: s.ERA, WHIP: s.WHIP, HR9: s.HR9, SO: s.SO,
        _ip: 1400, _totPA: 6000, _totAB: 5340, _pitchingValid: true } };
    }

    section('Standings sim — primitives');
    (function () {
      try {
        const r1 = simRng(42), r2 = simRng(42);
        assertEqual([r1.normal(), r1.normal(), r1.uni()], [r2.normal(), r2.normal(), r2.uni()],
          'simRng: same seed → same sequence');
        const r3 = simRng(7); let s = 0, s2 = 0; const N = 20000;
        for (let i = 0; i < N; i++) { const z = r3.normal(); s += z; s2 += z * z; }
        assert(Math.abs(s / N) < 0.03 && Math.abs(s2 / N - 1) < 0.05, 'simRng: normals have mean≈0, var≈1',
          'mean ' + (s / N).toFixed(3) + ' var ' + (s2 / N).toFixed(3));

        const proj = { OBP: .330, SLG: .420, HR: 230, R: 850, ERA: 3.9, WHIP: 1.22, HR9: 1.15, SO: 1300,
          _ip: 1400, _totPA: 6000, _totAB: 5340 };
        const full = simPeriod(null, proj, 'full');
        assertEqual([full.pa, full.ab, full.ip, full.ipScale], [6000, 5340, 1400, 1],
          'simPeriod full: the whole projection is the period');
        const ros = simPeriod({ ip: 1300 }, Object.assign({}, proj, { _ip: 300 }), 'ros');
        assert(Math.abs(ros.ip - 200) < 1e-9 && Math.abs(ros.ipScale - 200 / 300) < 1e-9,
          'simPeriod ros: innings capped at IP_MAX − thrown, as blendStats does', 'ip ' + ros.ip);

        const zero = simLuckSD({ OBP: .33, SLG: .42, HR: 0, R: 0, ERA: 4, WHIP: 1.2, HR9: 1.1, SO: 0 },
          { pa: 0, ab: 0, ip: 0, ipScale: 0 });
        assert(CATS.every(c => zero[c] === 0), 'simLuckSD: no playing time → zero luck everywhere (no NaN)',
          JSON.stringify(zero));
        const big = simLuckSD(proj, full);
        const small = simLuckSD(Object.assign({}, proj, { HR: 23 }), { pa: 600, ab: 534, ip: 140, ipScale: 1 });
        assert(small.HR < big.HR && small.OBP > big.OBP,
          'simLuckSD: counting luck grows with volume, rate luck shrinks with it');
      } catch (e) { assert(false, 'standings sim primitives threw', e.message); }
    })();
```

- [ ] **Step 2: Run the suite to see it fail**

Expected: `216 passed, 1 failed || ✗ standings sim primitives threw: simRng is not defined`.

- [ ] **Step 3: Create `standingsim.js` with the primitives**

```js
// ── STANDINGS FINISH ODDS ─────────────────────────────────────────────────────
// Monte Carlo odds of each team's final standings place, plus data-driven
// "paths" up the table. Spec: docs/superpowers/specs/2026-09-19-standings-odds-
// design.md. Model notes: MODEL.md §3b.
//
// Team-level simulation. Each run adds noise — luck plus projection error — to
// every team's projected category stats for the simulated period, then either
// blends them with current actuals through blendStats ('ros' mode) or uses them
// as the whole season ('full' mode), and ranks with buildStandings.
// Depends on shared.js: CATS, LOWER_BETTER, IP_MAX, blendStats, buildStandings.

// Luck: sampling variance over the playing time being simulated.
const SIM_LUCK = {
  D_HR: 1.0,          // team HR count variance / mean (≈ Poisson)
  D_R: 2.0,           // runs cluster within innings → overdispersed
  D_SO: 1.0,
  SLG_AB_SD: 0.88,    // SD of total bases per AB at a ~.420 SLG
  AB_PER_PA: 0.89,    // fallback when a projection carries no _totAB
  ERA_IP_SD: 0.9,     // SD of runs allowed per inning
  WHIP_IP_SD: 1.15,   // SD of baserunners per inning
};

// Projection error: a one-SD FULL-SEASON team miss. Counting categories are a
// fraction of the period's projected count; rate categories are absolute.
const SIM_PROJ_ERR = { HR: 0.10, R: 0.06, SO: 0.07, OBP: 0.008, SLG: 0.015, ERA: 0.30, WHIP: 0.035, HR9: 0.12 };
const SIM_ERR_RHO = 0.6;                          // share of a side's error that is team-wide
const SIM_ERROR_MULT = { ros: 0.75, full: 1.5 };  // RoS has absorbed 5 months of data; a full year adds injuries and churn
const SIM_DEFAULT_RUNS = 10000;
const SIM_PATH_MIN_ODDS = 0.01;   // below this, too few runs to describe a path honestly
const SIM_PATH_MIN_DELTA = 0.3;   // category-point moves smaller than this aren't reported
const SIM_HIT_CATS = { OBP: true, SLG: true, HR: true, R: true };

// Seeded RNG: mulberry32 uniforms + Box–Muller normals. The engine never uses
// Math.random, so a given seed and data set always give the same odds.
function simRng(seed) {
  let a = seed >>> 0;
  let spare = null;
  function uni() {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  function normal() {
    if (spare !== null) { const s = spare; spare = null; return s; }
    let u = 0;
    while (u === 0) u = uni();
    const v = uni();
    const r = Math.sqrt(-2 * Math.log(u));
    spare = r * Math.sin(2 * Math.PI * v);
    return r * Math.cos(2 * Math.PI * v);
  }
  return { uni: uni, normal: normal };
}

// The playing time the noise is sized on — only what actually reaches the
// final line. In 'ros' mode pitching is capped exactly as blendStats caps it
// (IP_MAX − innings already thrown), so luck is never sized on innings that
// won't count. ipScale is the fraction of projected innings that survive.
function simPeriod(curr, proj, mode) {
  const projIP = proj._ip || 0;
  const ip = (mode === 'ros' && curr)
    ? Math.min(projIP, Math.max(0, IP_MAX - (curr.ip || 0)))
    : projIP;
  const pa = proj._totPA || 0;
  return {
    pa: pa,
    ab: proj._totAB || pa * SIM_LUCK.AB_PER_PA,
    ip: ip,
    ipScale: projIP > 0 ? ip / projIP : 0,
  };
}

// Luck SD of each category's value over the period. Counting stats grow with
// volume (√count); rate stats shrink with it (1/√sample).
function simLuckSD(proj, period) {
  const L = SIM_LUCK;
  const pa = period.pa, ab = period.ab, ip = period.ip;
  const obp = Math.min(1, Math.max(0, proj.OBP || 0));
  const soEff = Math.max(0, (proj.SO || 0) * period.ipScale);
  return {
    HR:   Math.sqrt(L.D_HR * Math.max(0, proj.HR || 0)),
    R:    Math.sqrt(L.D_R  * Math.max(0, proj.R  || 0)),
    OBP:  pa > 0 ? Math.sqrt(obp * (1 - obp) / pa) : 0,
    SLG:  ab > 0 ? L.SLG_AB_SD / Math.sqrt(ab) : 0,
    SO:   Math.sqrt(L.D_SO * soEff),
    ERA:  ip > 0 ? 9 * L.ERA_IP_SD / Math.sqrt(ip) : 0,
    WHIP: ip > 0 ? L.WHIP_IP_SD / Math.sqrt(ip) : 0,
    HR9:  ip > 0 ? Math.sqrt(9 * Math.max(0, proj.HR9 || 0) / ip) : 0,
  };
}
```

- [ ] **Step 4: Run the suite**

Expected: `222 passed, 0 failed || no failures` (6 new assertions).

- [ ] **Step 5: Commit**

```bash
git add standingsim.js test.html
git commit -m "feat(standingsim): seeded RNG and luck model for finish odds

First piece of the standings odds simulator: a seeded mulberry32/Box-
Muller RNG (so the same data always gives the same odds), the playing-
time period each team's noise is sized on (innings capped exactly as
blendStats caps them), and per-category luck SDs.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `simulateStandings` — odds, ties and paths

**Files:**
- Modify: `standingsim.js` (append)
- Modify: `test.html` (two sections, directly after the primitives section from Task 2)

- [ ] **Step 1: Write the odds and paths tests**

Directly after the `Standings sim — primitives` IIFE, add:

```js
    section('Standings sim — odds');
    (function () {
      try {
        // Four teams strictly ordered in every category → totals 32/24/16/8.
        const ordered = [0, 1, 2, 3].map(i => simTeam('T' + i, simAvg({
          OBP: .350 - i * .01, SLG: .450 - i * .01, HR: 260 - i * 10, R: 900 - i * 20,
          ERA: 3.5 + i * .2, WHIP: 1.15 + i * .03, HR9: 1.0 + i * .05, SO: 1400 - i * 50 })));
        const det = simulateStandings(ordered, { mode: 'full', n: 50, seed: 1, luckMult: 0, errorMult: 0 });
        const expected = buildStandings(ordered.map(t => ({ name: t.name, stats: t.proj })));
        assert(expected.every((t, idx) => det.teams[t.name].place[idx] === 1),
          'zero noise reproduces buildStandings exactly');
        assertEqual(det.baseline.map(t => t.name), expected.map(t => t.name), 'baseline matches buildStandings order');

        // Twelve identical teams.
        const same = [];
        for (let i = 0; i < 12; i++) same.push(simTeam('S' + i, simAvg()));
        const sym = simulateStandings(same, { mode: 'full', n: 6000, seed: 3 });
        const rowOk = same.every(t => Math.abs(sym.teams[t.name].place.reduce((a, p) => a + p, 0) - 1) < 1e-9);
        let colOk = true;
        for (let k = 0; k < 12; k++) {
          colOk = colOk && Math.abs(same.reduce((a, t) => a + sym.teams[t.name].place[k], 0) - 1) < 1e-9;
        }
        assert(rowOk && colOk, 'conservation: each team and each place sums to 100%');
        const firsts = same.map(t => sym.teams[t.name].place[0]);
        assert(firsts.every(p => Math.abs(p - 1 / 12) < 0.025), 'symmetry: identical teams each win ≈1/12',
          firsts.map(p => p.toFixed(3)).join(' '));
        assert(same.every(t => {
          const x = sym.teams[t.name];
          return Math.abs(x.top3 - (x.place[0] + x.place[1] + x.place[2])) < 1e-12;
        }), 'top3 = p1 + p2 + p3');

        // One team far better in every category.
        const dom = same.slice(1).concat([simTeam('Dom', simAvg({
          OBP: .380, SLG: .500, HR: 330, R: 1050, ERA: 2.9, WHIP: 1.02, HR9: .80, SO: 1700 }))]);
        const d = simulateStandings(dom, { mode: 'full', n: 2000, seed: 5 });
        assert(d.teams.Dom.place[0] > 0.99, 'dominant team wins ~100%', d.teams.Dom.place[0].toFixed(3));

        // Two teams each winning four categories → 12–12 → half credit each.
        const tA = simTeam('A', simAvg({ OBP: .340, SLG: .430, HR: 240, R: 870, ERA: 4.2, WHIP: 1.30, HR9: 1.3, SO: 1200 }));
        const tB = simTeam('B', simAvg({ OBP: .320, SLG: .410, HR: 220, R: 830, ERA: 3.6, WHIP: 1.14, HR9: 1.0, SO: 1400 }));
        const tie = simulateStandings([tA, tB], { mode: 'full', n: 10, seed: 1, luckMult: 0, errorMult: 0 });
        assert(tie.teams.A.place[0] === 0.5 && tie.teams.B.place[0] === 0.5, 'tied totals split place credit',
          JSON.stringify(tie.teams.A.place));

        // Season over: nothing left to play, so odds collapse onto current standings.
        function done(name, c) {
          return { name: name, curr: Object.assign({ games: 162, ip: IP_MAX }, c),
            proj: { OBP: .330, SLG: .420, HR: 0, R: 0, ERA: 4.0, WHIP: 1.2, HR9: 1.1, SO: 0,
                    _ip: 50, _totPA: 0, _totAB: 0, _pitchingValid: true } };
        }
        const fin = simulateStandings([
          done('Up',   { r: 900, hr: 250, obp: .340, slg: .430, k: 1400, hr9: 1.0, era: 3.6, whip: 1.15 }),
          done('Down', { r: 850, hr: 230, obp: .320, slg: .410, k: 1300, hr9: 1.2, era: 4.0, whip: 1.25 }),
        ], { mode: 'ros', n: 500, seed: 9 });
        assert(fin.teams.Up.place[0] === 1, 'season over: odds collapse to current standings', fin.teams.Up.place[0]);

        const again = simulateStandings(same, { mode: 'full', n: 6000, seed: 3 });
        assertEqual(again.teams.S0.place, sym.teams.S0.place, 'same seed → identical odds');
      } catch (e) { assert(false, 'standings sim odds threw', e.message); }
    })();

    section('Standings sim — paths');
    (function () {
      try {
        // A wins OBP/SLG/R/ERA by a mile and HR by a hair; B wins WHIP/HR9/SO by
        // a mile. A leads 13–11; flipping HR ties it 12–12. HR is B's only route.
        const A = simTeam('A', simAvg({ OBP: .350, SLG: .470, HR: 201, R: 1000, ERA: 3.0, WHIP: 1.40, HR9: 1.6, SO: 1000 }));
        const B = simTeam('B', simAvg({ OBP: .300, SLG: .370, HR: 200, R: 600,  ERA: 4.5, WHIP: 1.10, HR9: 0.8, SO: 1400 }));
        const res = simulateStandings([A, B], { mode: 'full', n: 4000, seed: 11, errorMult: 0 });
        const pB = res.teams.B.paths.first;
        assert(pB && pB.gains.length > 0 && pB.gains[0].cat === 'HR', 'path to 1st names the one flippable category',
          JSON.stringify(pB));
        assert(pB && pB.rivals.some(r => r.team === 'A' && r.cat === 'HR'),
          'path to 1st shows the leader giving ground there');
        assert(pB && Math.abs(pB.odds - res.teams.B.place[0]) < 1e-9, 'path-to-1st odds equal P(1st)');
        assertEqual(res.teams.A.paths.first, null, 'the baseline leader has no path-to-1st');

        // Twelve-team league with one hopeless team.
        const pack = [];
        for (let i = 0; i < 11; i++) pack.push(simTeam('P' + i, simAvg()));
        pack.push(simTeam('Weak', simAvg({ OBP: .290, SLG: .360, HR: 150, R: 650, ERA: 5.0, WHIP: 1.45, HR9: 1.6, SO: 1000 })));
        const w = simulateStandings(pack, { mode: 'full', n: 3000, seed: 13 });
        assert(w.teams.Weak.place[0] < SIM_PATH_MIN_ODDS && w.teams.Weak.paths.first === null,
          'below 1% odds → no path to 1st');
        assert(w.teams.Weak.paths.top3 === null, 'below 1% odds → no path to top 3');
        const inTop3 = w.baseline.slice(0, 3).map(t => t.name);
        assert(inTop3.every(nm => w.teams[nm].paths.top3 === null), 'baseline top-3 teams have no path-to-top-3');
      } catch (e) { assert(false, 'standings sim paths threw', e.message); }
    })();
```

- [ ] **Step 2: Run the suite to see them fail**

Expected: `222 passed, 2 failed || ✗ standings sim odds threw: simulateStandings is not defined | ✗ standings sim paths threw: simulateStandings is not defined`.

- [ ] **Step 3: Append the engine to `standingsim.js`**

```js
// One simulated line for a team's period: projection + luck + projection error.
// Projection error is correlated within a side: one team-wide draw per side
// (hitting / pitching) carries SIM_ERR_RHO of the variance, signed so a
// positive draw is better in every category of that side.
function simDrawStats(proj, period, luck, errMult, luckMult, rng) {
  const out = Object.assign({}, proj);
  const E = SIM_PROJ_ERR;
  const a = Math.sqrt(SIM_ERR_RHO), b = Math.sqrt(1 - SIM_ERR_RHO);
  const zSide = { H: rng.normal(), P: rng.normal() };
  const soEff = Math.max(0, (proj.SO || 0) * period.ipScale);
  const errScale = {
    HR: E.HR * Math.max(0, proj.HR || 0),
    R:  E.R  * Math.max(0, proj.R  || 0),
    SO: E.SO * soEff,
    OBP: E.OBP, SLG: E.SLG, ERA: E.ERA, WHIP: E.WHIP, HR9: E.HR9,
  };
  CATS.forEach(cat => {
    const side = SIM_HIT_CATS[cat] ? 'H' : 'P';
    const zCat = rng.normal(), zLuck = rng.normal();   // always drawn: keeps the RNG stream aligned
    if (side === 'P' && proj._pitchingValid === false) return;
    const better = LOWER_BETTER.has(cat) ? -1 : 1;
    let delta = errMult * errScale[cat] * (a * zSide[side] + b * zCat) * better
              + luckMult * luck[cat] * zLuck;
    // blendStats multiplies the projected SO by ipScale; pre-divide so the
    // noise lands at its intended size on the innings that count.
    if (cat === 'SO') delta = period.ipScale > 0 ? delta / period.ipScale : 0;
    const v = (proj[cat] || 0) + delta;
    out[cat] = Number.isFinite(v) ? v : (proj[cat] || 0);
  });
  out.HR = Math.max(0, out.HR || 0);
  out.R  = Math.max(0, out.R  || 0);
  out.SO = Math.max(0, out.SO || 0);
  out.OBP = Math.min(1, Math.max(0, out.OBP || 0));
  out.SLG  = Math.max(0, out.SLG  || 0);
  out.ERA  = Math.max(0, out.ERA  || 0);
  out.WHIP = Math.max(0, out.WHIP || 0);
  out.HR9  = Math.max(0, out.HR9  || 0);
  return out;
}

// Finishing-place spans with ties on total points. `standings` is
// buildStandings output (sorted by points desc). A team tied across places
// lo..hi gets 1/(hi−lo+1) credit for each of them, so every team's odds and
// every place's odds still sum to 1.
function simPlaceSpans(standings) {
  const spans = {};
  let i = 0;
  while (i < standings.length) {
    let j = i;
    while (j + 1 < standings.length && standings[j + 1].points === standings[i].points) j++;
    for (let k = i; k <= j; k++) spans[standings[k].name] = { lo: i, hi: j };
    i = j + 1;
  }
  return spans;
}

function simNewAcc(names) {
  const sum = {};
  names.forEach(nm => { sum[nm] = {}; CATS.forEach(c => { sum[nm][c] = 0; }); });
  return { w: 0, sum: sum };
}

// Adds one run's category-point changes vs the baseline, for every team,
// weighted by how much credit the condition earned in this run.
function simAccumulate(acc, w, ranks, baseRanks) {
  acc.w += w;
  for (const team in acc.sum) {
    const s = acc.sum[team], r = ranks[team], r0 = baseRanks[team];
    CATS.forEach(cat => { s[cat] += w * ((r[cat] || 0) - (r0[cat] || 0)); });
  }
}

// Mean category-point moves in the runs where the condition held. null when
// the condition is too rare to average honestly.
function simPath(acc, team, rival, n) {
  if (!acc || acc.w / n < SIM_PATH_MIN_ODDS) return null;
  const mean = (t, cat) => acc.sum[t][cat] / acc.w;
  const gains = CATS.map(cat => ({ cat: cat, delta: mean(team, cat) }))
    .filter(g => g.delta >= SIM_PATH_MIN_DELTA)
    .sort((x, y) => y.delta - x.delta)
    .slice(0, 3);
  const rivals = rival
    ? CATS.map(cat => ({ team: rival, cat: cat, delta: mean(rival, cat) }))
        .filter(r => r.delta <= -SIM_PATH_MIN_DELTA)
        .sort((x, y) => x.delta - y.delta)
        .slice(0, 3)
    : [];
  return { odds: acc.w / n, gains: gains, rivals: rivals };
}

// teams: [{ name, curr (parseCurrStandings row or null), proj (computeTeamStats shape) }]
// opts:  { mode: 'ros'|'full', n, seed, errorMult, luckMult }
function simulateStandings(teams, opts) {
  opts = opts || {};
  const mode = opts.mode === 'full' ? 'full' : 'ros';
  const n = opts.n || SIM_DEFAULT_RUNS;
  const rng = simRng(opts.seed == null ? 1 : opts.seed);
  const errMult  = opts.errorMult != null ? opts.errorMult : SIM_ERROR_MULT[mode];
  const luckMult = opts.luckMult  != null ? opts.luckMult  : 1;
  const names = teams.map(t => t.name);
  const T = names.length;
  if (!T) return { n: n, mode: mode, baseline: [], teams: {} };

  function finalize(t, stats) {
    return (mode === 'ros' && t.curr) ? blendStats(t.curr, stats) : stats;
  }
  const prep = teams.map(t => {
    const period = simPeriod(t.curr, t.proj, mode);
    return { t: t, period: period, luck: simLuckSD(t.proj, period) };
  });

  // Zero-noise pass: the "most likely" standings the paths are measured from.
  const baseline = buildStandings(teams.map(t => ({ name: t.name, stats: finalize(t, t.proj) })));
  const baseRanks = {};
  baseline.forEach(t => { baseRanks[t.name] = t.ranks; });
  const leader = baseline[0].name;
  const baseTop3 = baseline.slice(0, 3).map(t => t.name);

  const place = {}, ptsSum = {}, accFirst = {}, accTop3 = {}, displaced = {};
  names.forEach(nm => {
    place[nm] = new Array(T).fill(0);
    ptsSum[nm] = 0;
    displaced[nm] = {};
    if (nm !== leader) accFirst[nm] = simNewAcc(names);
    if (baseTop3.indexOf(nm) === -1) accTop3[nm] = simNewAcc(names);
  });

  for (let run = 0; run < n; run++) {
    const st = buildStandings(prep.map(p => ({
      name: p.t.name,
      stats: finalize(p.t, simDrawStats(p.t.proj, p.period, p.luck, errMult, luckMult, rng)),
    })));
    const spans = simPlaceSpans(st);
    const ranks = {};
    st.forEach(t => { ranks[t.name] = t.ranks; ptsSum[t.name] += t.points; });

    const top3Credit = {};
    names.forEach(nm => {
      const s = spans[nm], share = 1 / (s.hi - s.lo + 1);
      for (let k = s.lo; k <= s.hi; k++) place[nm][k] += share;
      top3Credit[nm] = Math.max(0, Math.min(s.hi, 2) - s.lo + 1) * share;
    });
    names.forEach(nm => {
      const s = spans[nm];
      const wFirst = s.lo === 0 ? 1 / (s.hi - s.lo + 1) : 0;
      if (wFirst > 0 && accFirst[nm]) simAccumulate(accFirst[nm], wFirst, ranks, baseRanks);
      const w3 = top3Credit[nm];
      if (w3 > 0 && accTop3[nm]) {
        simAccumulate(accTop3[nm], w3, ranks, baseRanks);
        baseTop3.forEach(x => { displaced[nm][x] = (displaced[nm][x] || 0) + w3 * (1 - top3Credit[x]); });
      }
    });
  }

  const result = { n: n, mode: mode, baseline: baseline, teams: {} };
  names.forEach(nm => {
    const p = place[nm].map(c => c / n);
    // For the top-3 path, the rival is the baseline top-3 team this team most
    // often pushes out.
    let rival3 = null, most = 0;
    baseTop3.forEach(x => { const v = displaced[nm][x] || 0; if (v > most) { most = v; rival3 = x; } });
    result.teams[nm] = {
      place: p,
      top3: p[0] + (p[1] || 0) + (p[2] || 0),
      avgPts: ptsSum[nm] / n,
      paths: {
        first: accFirst[nm] ? simPath(accFirst[nm], nm, leader, n) : null,
        top3:  accTop3[nm]  ? simPath(accTop3[nm],  nm, rival3, n) : null,
      },
    };
  });
  return result;
}
```

- [ ] **Step 4: Run the suite**

Expected: `238 passed, 0 failed || no failures` (222 + 9 odds + 7 paths).

- [ ] **Step 5: Commit**

```bash
git add standingsim.js test.html
git commit -m "feat(standingsim): simulate finish odds with tie splits and paths

simulateStandings runs the seeded Monte Carlo: correlated projection
error plus luck per category, blended with actuals via blendStats (this
season) or used whole (next season), ranked with buildStandings. Ties on
total points split place credit so every row and column sums to 100%.

Paths up the table are conditional averages over the runs where a team
reaches 1st or the top 3: its biggest category-point gains vs the most
likely standings, and where the leader (or the top-3 team it most often
displaces) gives ground. Below 1% odds there is no path -- too few runs
to average honestly.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: This Season odds panel on `standings.html`

**Files:**
- Modify: `standings.html` (CSS block, markup lines 69-72, `render()` lines 161-166, page script)

- [ ] **Step 1: Add CSS** — inside `<style>`, after the `.data-stamp .stale .ds-val` rule:

```css
    .odds-toggle { display: flex; gap: 8px; margin: 0 0 10px; }
    .odds-row { cursor: pointer; }
    .odds-detail td { background: #f8fafe; text-align: left; font-size: 0.82rem; color: #444; padding: 8px 14px; }
    .odds-detail .path-line { margin: 2px 0; }
    .odds-note { font-size: 0.75rem; color: #888; margin-top: 8px; }
```

- [ ] **Step 2: Add the container and script** — replace:

```html
  <div class="tbl-wrap" id="tblWrap"></div>
  <div id="mgrWrap"></div>

  <script src="shared.js"></script>
```

with:

```html
  <div class="tbl-wrap" id="tblWrap"></div>
  <div id="oddsWrap"></div>
  <div id="mgrWrap"></div>

  <script src="shared.js"></script>
  <script src="standingsim.js"></script>
```

- [ ] **Step 3: Share team projection between the table and the odds**

Replace in `render()`:

```js
      var projStatsArr = teamNames.map(function(name) {
        var players  = teamMap[name];
        var lineup   = optimizeHitterLineup(players.filter(function(p) { return p.type === 'H'; }));
        var pitPool  = selectPitchers(players.filter(function(p) { return p.type === 'P'; }));
        return { name: name, stats: computeTeamStats(lineup, pitPool) };
      });
```

with:

```js
      var projStatsArr = teamNames.map(function(name) {
        return { name: name, stats: projectTeam(teamMap[name]) };
      });
```

- [ ] **Step 4: Add the odds code** — insert directly before `    (async function() {` at the bottom of the page script:

```js
    // ── Finish odds (standingsim.js) ─────────────────────────────────────────
    var ODDS_SEED  = 20260919;  // fixed: a given data set gives the same odds on every reload
    var oddsMode   = null;      // 'ros' | 'full'
    var oddsInputs = {};        // mode → simulateStandings team inputs
    var oddsCache  = {};        // mode → result (the table's mode buttons don't re-simulate)

    // One team's projected stat line. The Rest-of-Season table and the odds
    // simulator must build it identically, or the simulation's most likely
    // finish drifts from the table above it. Budgets default to the prorated
    // rest-of-season ones; Next Season passes full-season budgets.
    function projectTeam(players, paBudget, ipBudget) {
      var lineup  = optimizeHitterLineup(players.filter(function(p) { return p.type === 'H'; }), paBudget);
      var pitPool = selectPitchers(players.filter(function(p) { return p.type === 'P'; }), ipBudget);
      return computeTeamStats(lineup, pitPool);
    }

    function buildOddsInputs() {
      var inputs    = {};
      var roster    = loadData('ottoneu_roster');
      var projHit   = loadData('ottoneu_proj_hitting');
      var projPitch = loadData('ottoneu_proj_pitching');
      var currData  = loadData('ottoneu_curr_standings');
      if (!hasRows(roster) || !hasRows(projHit) || !hasRows(projPitch)) return inputs;

      var merged  = matchPlayers(roster, projHit, projPitch);
      var teamMap = {};
      merged.forEach(function(p) { (teamMap[p.team] = teamMap[p.team] || []).push(p); });
      var names = Object.keys(teamMap).filter(function(t) { return t !== 'Free Agent'; });

      if (hasRows(currData)) {
        var currByName = {};
        currData.forEach(function(row) { currByName[row.name.trim()] = row; });
        inputs.ros = names.map(function(name) {
          return { name: name, curr: currByName[name.trim()] || null, proj: projectTeam(teamMap[name]) };
        });
      }
      return inputs;
    }

    function fmtOdds(p) {
      if (p <= 0) return '—';
      if (p >= 1) return '100%';
      if (p > 0.99) return '>99%';
      if (p < 0.01) return '<1%';
      return Math.round(p * 100) + '%';
    }

    function pathText(goal, path) {
      if (!path) return 'Path to ' + goal + ': no realistic path (under 1% of simulations).';
      var odds  = (path.odds * 100).toFixed(1) + '%';
      var gains = path.gains.length
        ? path.gains.map(function(g) { return '+' + g.delta.toFixed(1) + ' pts ' + g.cat; }).join(', ')
        : 'no single category stands out';
      var s = 'Path to ' + goal + ' (' + odds + ' of runs): ' + gains + '.';
      if (path.rivals.length) {
        s += ' ' + path.rivals[0].team + ': ' +
          path.rivals.map(function(r) { return r.delta.toFixed(1) + ' pts ' + r.cat; }).join(', ') + '.';
      }
      return s;
    }

    function buildPathRow(name, t, leader, top3, numCols) {
      var tr = document.createElement('tr');
      tr.className = 'odds-detail';
      var td = document.createElement('td');
      td.colSpan = numCols;
      function line(text) {
        var d = document.createElement('div');
        d.className = 'path-line';
        d.textContent = text;
        td.appendChild(d);
      }
      line(name === leader ? 'Projected leader.' : pathText('1st', t.paths.first));
      if (top3.indexOf(name) === -1) line(pathText('top 3', t.paths.top3));
      tr.appendChild(td);
      return tr;
    }

    function renderOdds() {
      var wrap = document.getElementById('oddsWrap');
      while (wrap.firstChild) wrap.removeChild(wrap.firstChild);
      var modes = ['ros', 'full'].filter(function(m) { return oddsInputs[m] && oddsInputs[m].length; });
      if (!modes.length) return;
      if (modes.indexOf(oddsMode) === -1) oddsMode = modes[0];
      if (!oddsCache[oddsMode]) {
        oddsCache[oddsMode] = simulateStandings(oddsInputs[oddsMode],
          { mode: oddsMode, n: SIM_DEFAULT_RUNS, seed: ODDS_SEED });
      }
      var res    = oddsCache[oddsMode];
      var myTeam = loadData('ottoneu_my_team') || '';

      var section = document.createElement('div');
      section.className = 'mgr-section';
      var h2 = document.createElement('h2');
      h2.textContent = 'Finish Odds';
      var sub = document.createElement('p');
      sub.className = 'subtitle';
      sub.textContent = (oddsMode === 'ros'
        ? 'Chance of each final place, simulating the rest of this season on top of current standings.'
        : 'Chance of each final place over a full 2027 season on ZiPS Y1 projections.') +
        ' Click a team for its path up the table.';
      section.appendChild(h2);
      section.appendChild(sub);

      if (modes.length > 1) {
        var tog = document.createElement('div');
        tog.className = 'odds-toggle';
        modes.forEach(function(m) {
          var b = document.createElement('button');
          b.className = 'toggle-btn' + (m === oddsMode ? ' on' : '');
          b.textContent = m === 'ros' ? 'This Season' : 'Next Season';
          b.addEventListener('click', function() { oddsMode = m; renderOdds(); });
          tog.appendChild(b);
        });
        section.appendChild(tog);
      }

      var headers = ['#', 'Team', '1st', '2nd', '3rd', 'Top 3', 'Avg Pts'];
      var tbl = document.createElement('table');
      var thead = document.createElement('thead');
      var htr = document.createElement('tr');
      headers.forEach(function(h) { var th = document.createElement('th'); th.textContent = h; htr.appendChild(th); });
      thead.appendChild(htr);
      tbl.appendChild(thead);

      var leader = res.baseline.length ? res.baseline[0].name : '';
      var top3   = res.baseline.slice(0, 3).map(function(t) { return t.name; });
      var order  = Object.keys(res.teams).sort(function(a, b) {
        var ta = res.teams[a], tb = res.teams[b];
        return (tb.place[0] - ta.place[0]) || (tb.top3 - ta.top3) || (tb.avgPts - ta.avgPts);
      });

      var tbody = document.createElement('tbody');
      order.forEach(function(name, idx) {
        var t  = res.teams[name];
        var tr = document.createElement('tr');
        tr.className = 'odds-row' + (name === myTeam ? ' mine' : '');
        function td(text, cls) {
          var c = document.createElement('td');
          c.textContent = text;
          if (cls) c.className = cls;
          return c;
        }
        tr.appendChild(td(String(idx + 1), 'rank'));
        tr.appendChild(td(name));
        tr.appendChild(td(fmtOdds(t.place[0]), 'pts'));
        tr.appendChild(td(fmtOdds(t.place[1])));
        tr.appendChild(td(fmtOdds(t.place[2])));
        tr.appendChild(td(fmtOdds(t.top3)));
        tr.appendChild(td(t.avgPts.toFixed(1)));
        tr.addEventListener('click', function() {
          var next = tr.nextElementSibling;
          if (next && next.classList.contains('odds-detail')) { tbody.removeChild(next); return; }
          tbody.insertBefore(buildPathRow(name, t, leader, top3, headers.length), tr.nextSibling);
        });
        tbody.appendChild(tr);
      });
      tbl.appendChild(tbody);
      var tw = document.createElement('div');
      tw.className = 'tbl-wrap';
      tw.appendChild(tbl);
      section.appendChild(tw);

      var note = document.createElement('div');
      note.className = 'odds-note';
      note.textContent = res.n.toLocaleString() + ' simulated ' +
        (oddsMode === 'ros' ? 'finishes' : 'seasons') +
        '. Includes luck and projection error (assumed sizes, see MODEL.md §3b).' +
        (oddsMode === 'full'
          ? ' Uses current rosters as they stand; offseason cuts, auctions and trades are not modeled.'
          : '');
      section.appendChild(note);
      wrap.appendChild(section);
    }
```

- [ ] **Step 5: Kick it off after load** — replace:

```js
    (async function() {
      await autoLoadFromRepo();
      render();
    })();
```

with:

```js
    (async function() {
      await autoLoadFromRepo();
      render();
      // Simulate after the table has painted so it never waits on the odds.
      oddsInputs = buildOddsInputs();
      setTimeout(renderOdds, 0);
    })();
```

- [ ] **Step 6: Verify in the browser**

In the preview tab, run:
```js
Promise.all(['shared.js','standingsim.js','standings.html'].map(f => fetch(f, {cache:'reload'})))
  .then(() => location.replace('standings.html?v=' + Date.now())); 'reloading'
```
Then check (after ~2s):
```js
var rows = Array.from(document.querySelectorAll('#oddsWrap tbody tr.odds-row'));
JSON.stringify({ rows: rows.length,
  first: rows.slice(0, 4).map(r => r.innerText.replace(/\s+/g, ' ')),
  errors: document.getElementById('error').textContent })
```
Expected: 12 rows, no error text, top rows show plausible percentages. Then check the most-likely finish matches the table's Rest of Season mode:
```js
setMode('ros');
var tableOrder = Array.from(document.querySelectorAll('#tblWrap tbody tr')).map(r => r.children[1].textContent);
JSON.stringify({ tableTop3: tableOrder.slice(0, 3), simBaselineTop3: oddsCache.ros.baseline.slice(0, 3).map(t => t.name) })
```
Expected: the two top-3 lists are identical. Click a non-leader row and confirm a path line appears. Check `read_console_messages` with `onlyErrors: true` for exceptions from `standings.html`.

- [ ] **Step 7: Run the suite** — expected `0 failed`.

- [ ] **Step 8: Commit**

```bash
git add standings.html
git commit -m "feat(standings): Finish Odds panel for the rest of this season

Adds a panel under the standings table with each team's chance to finish
1st, 2nd, 3rd and top 3, simulated over the games left on top of current
standings. Clicking a team shows its path to 1st and to the top 3.

The table and the simulator now share one projectTeam helper, so the
simulation's most likely finish is exactly the Rest of Season table. The
simulation runs after the table paints and is cached, so the table's
mode buttons never re-simulate.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Next Season mode

**Files:**
- Modify: `standings.html` (`buildOddsInputs`)

- [ ] **Step 1: Add Y1 inputs** — in `buildOddsInputs`, replace the final `      return inputs;` with:

```js
      // Next Season: current rosters on ZiPS Y1, full-season budgets — the same
      // construction calculateAllValues uses for future years.
      var hitY1 = loadData('ottoneu_proj_hitting_y1');
      var pitY1 = loadData('ottoneu_proj_pitching_y1');
      if (hasRows(hitY1) || hasRows(pitY1)) {
        var y1 = attachYearProjections(merged, hitY1, pitY1, 'proj_y1');
        if (y1.some(function(p) { return p.proj_y1; })) {
          var y1Map = {};
          y1.forEach(function(p) { (y1Map[p.team] = y1Map[p.team] || []).push(p); });
          var y1Rosters = cloneForYear(names.map(function(nm) { return y1Map[nm] || []; }), 'proj_y1');
          inputs.full = names.map(function(name, i) {
            var withProj = y1Rosters[i].filter(function(p) { return p.proj; });
            return { name: name, curr: null, proj: projectTeam(withProj, PA_PER_SLOT, IP_MAX) };
          });
        }
      }
      return inputs;
```

- [ ] **Step 2: Verify in the browser** — reload as in Task 4 Step 6, then:
```js
var btns = Array.from(document.querySelectorAll('#oddsWrap .odds-toggle button')).map(b => b.textContent);
btns.length ? (document.querySelectorAll('#oddsWrap .odds-toggle button')[1].click(), 'clicked') : 'NO TOGGLE'
```
Then:
```js
JSON.stringify({ toggle: Array.from(document.querySelectorAll('#oddsWrap .odds-toggle button')).map(b => b.textContent + (b.classList.contains('on') ? '*' : '')),
  rows: document.querySelectorAll('#oddsWrap tr.odds-row').length,
  top: Array.from(document.querySelectorAll('#oddsWrap tr.odds-row')).slice(0, 3).map(r => r.innerText.replace(/\s+/g, ' ')),
  note: document.querySelector('#oddsWrap .odds-note').textContent })
```
Expected: toggle `["This Season", "Next Season*"]`, 12 rows, the note mentions current rosters, and next-season odds are clearly less lopsided than this season's. Console: no errors.

- [ ] **Step 3: Run the suite** — expected `0 failed`.

- [ ] **Step 4: Commit**

```bash
git add standings.html
git commit -m "feat(standings): Next Season mode for finish odds

Adds a This Season / Next Season toggle to the Finish Odds panel. Next
Season simulates a full 2027 season from current rosters on ZiPS Y1
projections, built with the same full-season budgets and Y1 roster
cloning the dynasty values use. The page says plainly that offseason
cuts, auctions and trades aren't modeled.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Document the model; real-data sanity check

**Files:**
- Modify: `MODEL.md` (insert before `## 4. Dynasty values`; knob table rows after the `TF_RENTAL_MIN_VALUE` row)

- [ ] **Step 1: Add §3b** — insert before the line `## 4. Dynasty values (\`calculateDynastyValues\`)`:

```markdown
## 3b. Standings finish odds (`standingsim.js`)

Seeded Monte Carlo (10,000 runs) behind the Finish Odds panel on
standings.html. Spec: `docs/superpowers/specs/2026-09-19-standings-odds-design.md`.

- **Team-level.** Each run adds noise to every team's projected category line
  for the simulated period, then `blendStats` (This Season) or the line as a
  whole season (Next Season), then `buildStandings`. The zero-noise pass is the
  baseline and equals the Rest of Season table — both are built by
  `projectTeam` in standings.html, and must stay that way.
- **Noise = luck + projection error.** Luck is sampling variance on the
  period's playing time (HR/R/K ≈ √count with dispersion, OBP/SLG/ERA/WHIP/HR9
  ≈ 1/√PA or IP). Pitching luck is sized on the innings that survive the IP cap,
  and the K noise is pre-divided by `ipScale` because `blendStats` multiplies
  the projected K by it. Projection error is a one-SD full-season team miss
  (`SIM_PROJ_ERR`), 60% of it shared across a team's hitting categories and
  60% across its pitching (`SIM_ERR_RHO`), scaled ×0.75 This Season (RoS
  projections have absorbed five months) and ×1.5 Next Season (injuries,
  churn).
- **These sizes are assumptions,** not fitted to league history. They are the
  main lever on how confident the odds look — Next Season especially.
- **Ties** on total points split place credit, so rows and columns sum to 1.
- **Paths** are conditional means over the runs where a team reaches 1st / the
  top 3: its category-point gains vs baseline, and the leader's (or the
  most-displaced top-3 team's) drops. Reported only at ≥1% odds and ≥0.3-point
  moves.
- **No recent-form tuning, deliberately.** 7/15/30-day results add little
  signal over a daily-updated RoS projection; blending them in adds noise.
- **Limitations:** PA/IP volume isn't randomized; Next Season uses current
  rosters (no cuts/auctions/trades) and ignores prospects without Y1 lines;
  standings.csv Games/IP are uniform across teams, so the season-elapsed
  weighting is identical for all.
```

- [ ] **Step 2: Add knob rows** — after the `| \`TF_RENTAL_MIN_VALUE\` | ...` row:

```markdown
| `SIM_PROJ_ERR` | standingsim.js | HR 10% / R 6% / SO 7% / OBP .008 / SLG .015 / ERA .30 / WHIP .035 / HR9 .12 | one-SD full-season team projection miss |
| `SIM_ERROR_MULT` | standingsim.js | ros 0.75 / full 1.5 | projection-error scale per odds mode |
| `SIM_ERR_RHO` | standingsim.js | 0.6 | share of a side's projection error that is team-wide |
| `SIM_LUCK` | standingsim.js | see file | sampling-variance constants |
| `SIM_PATH_MIN_ODDS`, `SIM_PATH_MIN_DELTA` | standingsim.js | 1% / 0.3 pts | thresholds for reporting a path |
```

- [ ] **Step 3: Real-data sanity check** — write this to the scratchpad as `simcheck.js` and run it with `node` from the repo root:

```js
const fs = require('fs'), vm = require('vm');
const sb = { console: { log() {}, warn() {}, error() {} }, window: { location: { hostname: '', pathname: '' } },
  localStorage: { getItem() { return null; }, setItem() {}, removeItem() {} } };
vm.createContext(sb);
vm.runInContext(fs.readFileSync('shared.js', 'utf8'), sb);
vm.runInContext(fs.readFileSync('standingsim.js', 'utf8'), sb);
const roster = sb.parseRosterCSV(fs.readFileSync('data/roster.csv', 'utf8'));
const ph = sb.parseHittingProjections(fs.readFileSync('data/proj_hitting.csv', 'utf8'));
const pp = sb.parsePitchingProjections(fs.readFileSync('data/proj_pitching.csv', 'utf8'));
const curr = sb.parseCurrStandings(fs.readFileSync('data/standings.csv', 'utf8'));
const merged = sb.matchPlayers(roster, ph, pp);
const tm = {}; merged.forEach(p => { (tm[p.team] = tm[p.team] || []).push(p); });
const names = Object.keys(tm).filter(t => t !== 'Free Agent');
const cb = {}; curr.forEach(r => { cb[r.name.trim()] = r; });
const teams = names.map(n => ({ name: n, curr: cb[n.trim()] || null,
  proj: sb.computeTeamStats(sb.optimizeHitterLineup(tm[n].filter(p => p.type === 'H')),
                            sb.selectPitchers(tm[n].filter(p => p.type === 'P'))) }));
const t0 = Date.now();
const res = sb.simulateStandings(teams, { mode: 'ros', n: 10000, seed: 20260919 });
console.log('ms', Date.now() - t0);
Object.keys(res.teams).sort((a, b) => res.teams[b].place[0] - res.teams[a].place[0]).forEach(n => {
  const t = res.teams[n];
  console.log(n.padEnd(30), (t.place[0] * 100).toFixed(1).padStart(6), (t.top3 * 100).toFixed(1).padStart(6),
    t.avgPts.toFixed(1).padStart(6), t.paths.first ? t.paths.first.gains.map(g => g.cat).join('/') : '');
});
```

Expected: runtime well under 2000 ms; probabilities sum sensibly; the baseline leader has the highest P(1st); teams far behind show 0.0.

- [ ] **Step 4: Run the suite** — expected `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add MODEL.md
git commit -m "docs(model): document the standings finish-odds simulator

New MODEL.md section 3b covering the team-level Monte Carlo, the luck
and projection-error noise model, why its sizes are assumptions, tie
splitting, how paths are derived, the deliberate choice not to tune on
recent form, and the limitations. Adds the simulator's constants to the
knob table.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```
