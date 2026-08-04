# Archetype Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (user preference: inline execution) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `targets.html`'s value-sorted candidate slicing with generation **by reason** — every proposal arrives with an explicit "why" for both sides.

**Source spec:** `docs/superpowers/specs/2026-08-02-trade-finder-redesign.md` (Phase 2). Fix 1 (option-valued contracts) and Fix 2 (marginal-value engine) have shipped, plus the PA-budget lineup and Y1 replacement corrections. MODEL.md §8's do-not-ship warning is lifted.

**The defect being fixed:** [targets.html:617-673](../../targets.html) slices `myOffers` to the top 4 and `theirChips` to the top 5 **by absolute value**, then a value-matching fairness filter forces symmetry. That explores 20 of ~1,764 possible 1-for-1s — 1.1% of the space, all of it the priciest slice — so star-for-star is the only reachable outcome.

**Architecture:** New pure matchers in `tradefinder.js` emit candidate *pairs* carrying `{archetype, reason, myPlayers, theirPlayers}`. `targets.html` feeds each pair through the **existing** `evaluateCandidates` (fairness pre-filter → `simulateTrade` → utility gate), which is correct and stays untouched — it has simply been starved of sane input.

**Baseline:** `test.html` reports **173 passed, 0 failed**. Keep failed at 0. Counts below are approximate — verify the invariant, update the numbers to observed reality.

**Note on commits:** Commit locally after each task. NEVER `git push`.

---

## Blocking prerequisite discovered while planning

**`tfGain` is semantically wrong for cross-team use.** It reads `marginalsB[key]`, but a
player is not in the other team's marginals map, so that term is always `0` and the
function returns `−marginalsA[key]`. Its existing test passes only because it is handed a
hand-built map containing the player. Every archetype needs "what would he be worth to
*them*", so Task 1 must add a real primitive before any matcher is written.

---

### Task 1: Cross-team marginal value

**Files:** Modify `tradefinder.js`, `test.html`.

- [ ] **Step 1:** Append to `tradefinder.js`:

```js
// What a player would ADD to a roster he is not currently on: re-optimize that
// roster with him inserted and score the delta. This is the primitive every
// archetype needs — tfGain() below only compares within already-computed maps
// and cannot answer it.
function tfMarginalOn(player, roster, denoms, ipBudget) {
  var budget = ipBudget || tfIpBudget();
  var base   = tfTeamStats(roster, budget);
  var withHim = roster.concat([player]);
  return tfMarginalZ(tfTeamStats(withHim, budget), base, denoms) * TF_PTS_DOLLARS;
}

// How much MORE a player is worth on targetRoster than to his current owner.
// Positive = the trade motivation exists.
function tfCrossGain(player, ownerMarginals, targetRoster, denoms, ipBudget) {
  return tfMarginalOn(player, targetRoster, denoms, ipBudget)
       - ((ownerMarginals || {})[tfKey(player)] || 0);
}
```

- [ ] **Step 2:** Tests (before `// ── Summary ──`):

```js
    // ── Cross-team marginal ──────────────────────────────────────────────────
    section('Cross-team value');
    (function () {
      function ch(n, pa, obp, slg, hr, r) {
        return { name: n, fgId: n, type: 'H', positions: ['c'],
                 proj: { pa: pa, ab: pa * 0.9, obp: obp, slg: slg, hr: hr, r: r } };
      }
      var star = ch('star', 500, 0.400, 0.550, 30, 90);
      // Thin roster: no catcher at all — the star fills a hole.
      var thin = [];
      for (var i = 0; i < 3; i++) thin.push({ name: 'of' + i, fgId: 'of' + i, type: 'H',
        positions: ['of'], proj: { pa: 500, ab: 450, obp: 0.330, slg: 0.430, hr: 15, r: 60 } });
      // Deep roster: already has two better catchers.
      var deep = [ch('c1', 550, 0.410, 0.570, 33, 95), ch('c2', 540, 0.405, 0.560, 32, 93)].concat(thin);

      var addThin = tfMarginalOn(star, thin, tfDen, 400);
      var addDeep = tfMarginalOn(star, deep, tfDen, 400);
      assert(addThin > 0, 'tfMarginalOn: a star adds positive value to a roster with a hole');
      assert(addThin > addDeep,
        'tfMarginalOn: worth MORE to the team with the hole than to the deep team');

      // Cross-gain: blocked on the deep team, valuable on the thin one.
      var deepMarg = tfRosterMarginals(deep, tfDen, 400);
      assert(tfCrossGain(ch('c1', 550, 0.410, 0.570, 33, 95), deepMarg, thin, tfDen, 400) > 0,
        'tfCrossGain: positive when the target roster values him more than his owner');
    })();
```

- [ ] **Step 3:** Verify green. **Step 4:** Commit
`feat(trade): cross-team marginal value primitive`.

---

### Task 2: Generator context + logjam↔hole matcher

**Files:** Modify `tradefinder.js`, `test.html`.

- [ ] **Step 1:** Append to `tradefinder.js`:

```js
// Everything the matchers need, computed ONCE per page load.
// rostersByTeam: { team: [players] }; valueMap: Y0 values (projValue);
// dynastyMap: from calculateDynastyValues (carries holdHorizon).
function tfBuildContext(rostersByTeam, valueMap, dynastyMap, denoms, ipBudget) {
  var budget = ipBudget || tfIpBudget();
  var marginals = tfAllMarginals(rostersByTeam, denoms, budget);
  return {
    rostersByTeam: rostersByTeam,
    valueMap: valueMap || {},
    dynastyMap: dynastyMap || {},
    denoms: denoms,
    ipBudget: budget,
    marginals: marginals,
    needGaps: tfNeedGaps(rostersByTeam, marginals),
  };
}

function tfDollars(n) { return '$' + Math.round(n); }

// ARCHETYPE 1 — Logjam ↔ Hole.
// I have a bat stranded behind better ones; they would start him. Reciprocally
// for one of theirs. This is the archetype the old top-4 × top-5 slicing could
// never reach, because a blocked player is by definition NOT near the top of a
// value-sorted list.
function tfLogjamCandidates(ctx, myTeam, theirTeam) {
  var out = [];
  var myMarg = ctx.marginals[myTeam] || {}, thMarg = ctx.marginals[theirTeam] || {};
  var myRoster = ctx.rostersByTeam[myTeam] || [], thRoster = ctx.rostersByTeam[theirTeam] || [];

  function surplusAssets(roster, ownMarg, otherRoster) {
    return roster.filter(function (p) { return p.type === 'H' && p.proj; })
      .map(function (p) {
        return { p: p,
                 blocked: tfBlockedness(p, ownMarg, ctx.valueMap),
                 gain: tfCrossGain(p, ownMarg, otherRoster, ctx.denoms, ctx.ipBudget) };
      })
      .filter(function (x) { return x.blocked >= TF_BLOCK_MIN && x.gain >= TF_GAIN_MIN; })
      .sort(function (a, b) { return b.gain - a.gain; })
      .slice(0, 4);
  }

  var mine  = surplusAssets(myRoster, myMarg, thRoster);
  var yours = surplusAssets(thRoster, thMarg, myRoster);

  mine.forEach(function (a) {
    yours.forEach(function (b) {
      out.push({
        archetype: 'logjam',
        myPlayers: [a.p], theirPlayers: [b.p],
        reason: (a.p.rawName || a.p.name) + ' is stranded on your bench (' +
                tfDollars(a.blocked) + ' of value you cannot field) and worth ' +
                tfDollars(a.gain) + ' more to them; ' + (b.p.rawName || b.p.name) +
                ' is the mirror image — ' + tfDollars(b.gain) + ' more useful to you.',
      });
    });
  });
  return out;
}
```

- [ ] **Step 2:** Tests:

```js
    // ── Archetype: logjam ↔ hole ─────────────────────────────────────────────
    section('Archetypes');
    (function () {
      function ch(n, pa, obp, slg, hr, r, pos) {
        return { name: n, fgId: n, type: 'H', positions: [pos || 'c'],
                 proj: { pa: pa, ab: pa * 0.9, obp: obp, slg: slg, hr: hr, r: r } };
      }
      // A: three good catchers (one must sit), no outfielder depth.
      // B: three good outfielders, one weak catcher.
      var A = [ch('a-c1',550,0.400,0.550,30,90), ch('a-c2',540,0.395,0.545,29,88),
               ch('a-c3',530,0.390,0.540,28,86), ch('a-of',500,0.300,0.360,5,40,'of')];
      var B = [ch('b-of1',550,0.400,0.550,30,90,'of'), ch('b-of2',540,0.395,0.545,29,88,'of'),
               ch('b-of3',530,0.390,0.540,28,86,'of'), ch('b-c',500,0.300,0.360,5,40)];
      var rost = { A: A, B: B };
      var vm = {}; A.concat(B).forEach(function (p) { vm[p.fgId] = { projectedValue: 25 }; });
      var ctx = tfBuildContext(rost, vm, {}, tfDen, 400);
      var cands = tfLogjamCandidates(ctx, 'A', 'B');
      assert(cands.length > 0, 'tfLogjamCandidates: finds a catcher-for-outfielder swap');
      assert(cands.every(function (c) { return c.archetype === 'logjam' && c.reason.length > 20; }),
        'tfLogjamCandidates: every candidate carries an archetype and a reason');
      assert(cands.every(function (c) { return c.myPlayers.length && c.theirPlayers.length; }),
        'tfLogjamCandidates: both sides are populated');
      // Two identical rosters have no logjam motivation.
      var same = tfBuildContext({ A: A, B: A.map(function (p) {
        return Object.assign({}, p, { fgId: 'x-' + p.fgId, name: 'x-' + p.name }); }) },
        vm, {}, tfDen, 400);
      assertEqual(tfLogjamCandidates(same, 'A', 'B').length, 0,
        'tfLogjamCandidates: mirror-image rosters produce no candidates');
    })();
```

**If the mirror-image assertion fails**, the fixture's two rosters are not actually
symmetric under the optimizer — print `ctx.marginals` for both and confirm before
weakening the assertion.

- [ ] **Step 3:** Verify green. **Step 4:** Commit
`feat(trade): generator context + logjam/hole archetype`.

---

### Task 3: Rental / salary-dump matcher

**Files:** Modify `tradefinder.js`, `test.html`.

- [ ] **Step 1:** Append:

```js
// ARCHETYPE 2 — Rental / salary dump.
// Their productive player on a bad contract (holdHorizon 0) is one they were
// going to cut in October for nothing. Trading him beats cutting: an in-season
// cut costs half his salary in dead money, a trade costs nothing and returns an
// asset. I take the full salary for the stretch run and cut free at season's end.
// GATE: holdHorizon === 0 alone is NOT enough — roughly 60% of contracts resolve
// there and most are $1-3 fringe (MODEL.md §4). Require real Y0 production.
var TF_RENTAL_MIN_VALUE = 8;   // $ of Y0 value before a rental is worth pursuing

function tfRentalCandidates(ctx, myTeam, theirTeam, myStatus, theirStatus) {
  if (myStatus === 'rebuilder') return [];        // rentals are for teams trying to win now
  if (theirStatus === 'contender') return [];     // contenders do not sell their production
  var out = [];
  var myMarg = ctx.marginals[myTeam] || {};
  var myRoster = ctx.rostersByTeam[myTeam] || [];
  var thRoster = ctx.rostersByTeam[theirTeam] || [];

  var rentals = thRoster.filter(function (q) {
    if (!q.proj) return false;
    var d = ctx.dynastyMap[tfKey(q)];
    if (!d || d.holdHorizon !== 0) return false;
    var v = (ctx.valueMap[tfKey(q)] || {}).projectedValue || 0;
    if (v < TF_RENTAL_MIN_VALUE) return false;                    // skip fringe H0
    return tfMarginalOn(q, myRoster, ctx.denoms, ctx.ipBudget) > 0;  // he must actually help me
  }).sort(function (a, b) {
    return ((ctx.valueMap[tfKey(b)] || {}).projectedValue || 0)
         - ((ctx.valueMap[tfKey(a)] || {}).projectedValue || 0);
  }).slice(0, 3);

  // What I send: a future asset I am not using now — low current marginal value,
  // positive dynasty surplus.
  var chips = myRoster.filter(function (p) {
    if (!p.proj) return false;
    var d = ctx.dynastyMap[tfKey(p)];
    if (!d || (d.dynastySurplus || 0) <= 0) return false;
    return (myMarg[tfKey(p)] || 0) < TF_GAIN_MIN;
  }).sort(function (a, b) {
    return ((ctx.dynastyMap[tfKey(b)] || {}).dynastySurplus || 0)
         - ((ctx.dynastyMap[tfKey(a)] || {}).dynastySurplus || 0);
  }).slice(0, 3);

  rentals.forEach(function (q) {
    chips.forEach(function (p) {
      var sal = q.salary || 0;
      out.push({
        archetype: 'rental',
        myPlayers: [p], theirPlayers: [q],
        reason: (q.rawName || q.name) + ' is a rental for you — you cut him free in ' +
                'October, so his ' + tfDollars(sal) + ' salary is a stretch-run cost only. ' +
                'They were losing him for nothing: cutting him in-season costs them ' +
                tfDollars(sal / 2) + ' in dead money, while trading him costs nothing and ' +
                'returns ' + (p.rawName || p.name) + ', who you are not using now.',
      });
    });
  });
  return out;
}
```

- [ ] **Step 2:** Tests:

```js
    // ── Archetype: rental / salary dump ──────────────────────────────────────
    (function () {
      function pl(n, sal, val, horizon, surplus) {
        return { name: n, fgId: n, type: 'H', positions: ['of'], salary: sal,
                 proj: { pa: 500, ab: 450, obp: 0.360, slg: 0.480, hr: 22, r: 70 },
                 _val: val, _h: horizon, _s: surplus };
      }
      var theirGuy = pl('overpaid', 30, 20, 0, -12);      // productive, bad contract
      var theirScrub = pl('fringe', 2, 3, 0, -1);          // H0 but worthless — must be skipped
      var myChip  = pl('prospect', 3, 1, 2, 18);           // future asset, unused now
      var rost = { ME: [myChip], THEM: [theirGuy, theirScrub] };
      var vm = {}, dm = {};
      [theirGuy, theirScrub, myChip].forEach(function (p) {
        vm[p.fgId] = { projectedValue: p._val };
        dm[p.fgId] = { holdHorizon: p._h, dynastySurplus: p._s };
      });
      var ctx = tfBuildContext(rost, vm, dm, tfDen, 400);
      var c = tfRentalCandidates(ctx, 'ME', 'THEM', 'contender', 'rebuilder');
      assert(c.length > 0, 'tfRentalCandidates: finds the productive bad contract');
      assert(c.every(function (x) { return x.theirPlayers[0].name === 'overpaid'; }),
        'tfRentalCandidates: skips the $2 fringe H0 player (value gate)');
      assert(c[0].reason.indexOf('dead money') > -1,
        'tfRentalCandidates: reason states the seller-side motivation');
      assertEqual(tfRentalCandidates(ctx, 'ME', 'THEM', 'rebuilder', 'rebuilder').length, 0,
        'tfRentalCandidates: a rebuilder does not rent');
      assertEqual(tfRentalCandidates(ctx, 'ME', 'THEM', 'contender', 'contender').length, 0,
        'tfRentalCandidates: a contender does not sell its production');
    })();
```

- [ ] **Step 3:** Verify green. **Step 4:** Commit
`feat(trade): rental / salary-dump archetype`.

---

### Task 4: Buy-now↔sell-future, consolidation, and the dispatcher

**Files:** Modify `tradefinder.js`, `test.html`.

- [ ] **Step 1:** Append:

```js
// ARCHETYPE 3 — Buy-now ↔ sell-future. Same idea the old rel='buy'/'sell' logic
// had, but fed MARGINAL value: I send future surplus I cannot field this year,
// they send current production they cannot use while rebuilding.
function tfWindowCandidates(ctx, myTeam, theirTeam, myStatus, theirStatus) {
  if (myStatus === theirStatus) return [];
  var out = [];
  var myMarg = ctx.marginals[myTeam] || {}, thMarg = ctx.marginals[theirTeam] || {};
  var myRoster = ctx.rostersByTeam[myTeam] || [], thRoster = ctx.rostersByTeam[theirTeam] || [];
  var buying = myStatus !== 'rebuilder' && theirStatus === 'rebuilder';
  var selling = myStatus === 'rebuilder' && theirStatus !== 'rebuilder';
  if (!buying && !selling) return [];

  function futureAssets(roster, marg) {
    return roster.filter(function (p) {
      var d = ctx.dynastyMap[tfKey(p)];
      return p.proj && d && (d.dynastySurplus || 0) > 0 && (marg[tfKey(p)] || 0) < TF_GAIN_MIN;
    }).sort(function (a, b) {
      return ((ctx.dynastyMap[tfKey(b)] || {}).dynastySurplus || 0)
           - ((ctx.dynastyMap[tfKey(a)] || {}).dynastySurplus || 0);
    }).slice(0, 3);
  }
  function nowAssets(roster, otherRoster) {
    return roster.filter(function (p) { return p.proj; })
      .map(function (p) { return { p: p, add: tfMarginalOn(p, otherRoster, ctx.denoms, ctx.ipBudget) }; })
      .filter(function (x) { return x.add >= TF_GAIN_MIN; })
      .sort(function (a, b) { return b.add - a.add; })
      .slice(0, 3);
  }

  var sendFuture = buying ? futureAssets(myRoster, myMarg) : futureAssets(thRoster, thMarg);
  var sendNow    = buying ? nowAssets(thRoster, myRoster) : nowAssets(myRoster, thRoster);

  sendFuture.forEach(function (f) {
    sendNow.forEach(function (n) {
      out.push({
        archetype: buying ? 'buy-now' : 'sell-future',
        myPlayers:   buying ? [f] : [n.p],
        theirPlayers: buying ? [n.p] : [f],
        reason: buying
          ? 'They are rebuilding and cannot use ' + (n.p.rawName || n.p.name) + ' now (worth ' +
            tfDollars(n.add) + ' to your lineup); you send future surplus you are not fielding.'
          : 'You are rebuilding: ' + (n.p.rawName || n.p.name) + ' is production you cannot ' +
            'cash in, and they will pay in future value.',
      });
    });
  });
  return out;
}

// ARCHETYPE 4 — Consolidation. Two of my usable-but-not-elite pieces for one of
// their better ones, when I am deep enough to spare the roster spot. The existing
// CONSOL_PREM in targets.html prices the bulkier side; this only proposes it.
function tfConsolidationCandidates(ctx, myTeam, theirTeam) {
  var out = [];
  var myMarg = ctx.marginals[myTeam] || {}, thMarg = ctx.marginals[theirTeam] || {};
  var myRoster = ctx.rostersByTeam[myTeam] || [], thRoster = ctx.rostersByTeam[theirTeam] || [];
  var spares = myRoster.filter(function (p) {
      return p.proj && (myMarg[tfKey(p)] || 0) > 0 &&
             tfBlockedness(p, myMarg, ctx.valueMap) >= TF_BLOCK_MIN;
    }).sort(function (a, b) {
      return tfBlockedness(b, myMarg, ctx.valueMap) - tfBlockedness(a, myMarg, ctx.valueMap);
    }).slice(0, 4);
  var targets = thRoster.filter(function (p) { return p.proj; })
    .map(function (p) { return { p: p, add: tfMarginalOn(p, myRoster, ctx.denoms, ctx.ipBudget) }; })
    .filter(function (x) { return x.add >= TF_GAIN_MIN * 2; })
    .sort(function (a, b) { return b.add - a.add; }).slice(0, 2);

  targets.forEach(function (t) {
    for (var i = 0; i < spares.length; i++) {
      for (var j = i + 1; j < spares.length; j++) {
        out.push({
          archetype: 'consolidation',
          myPlayers: [spares[i], spares[j]], theirPlayers: [t.p],
          reason: 'You are deep enough to spare two bench pieces; ' +
                  (t.p.rawName || t.p.name) + ' would add ' + tfDollars(t.add) +
                  ' to your lineup and frees a roster spot.',
        });
      }
    }
  });
  return out;
}

// Dispatcher — all archetypes for one opponent, de-duplicated by player pairing.
function tfGenerateCandidates(ctx, myTeam, theirTeam, myStatus, theirStatus) {
  var all = []
    .concat(tfLogjamCandidates(ctx, myTeam, theirTeam))
    .concat(tfRentalCandidates(ctx, myTeam, theirTeam, myStatus, theirStatus))
    .concat(tfWindowCandidates(ctx, myTeam, theirTeam, myStatus, theirStatus))
    .concat(tfConsolidationCandidates(ctx, myTeam, theirTeam));
  var seen = {}, out = [];
  all.forEach(function (c) {
    var k = c.myPlayers.map(tfKey).sort().join('|') + '/' +
            c.theirPlayers.map(tfKey).sort().join('|');
    if (seen[k]) return;
    seen[k] = 1; out.push(c);
  });
  return out;
}
```

- [ ] **Step 2:** Tests — dispatcher shape and dedup:

```js
    // ── Dispatcher ───────────────────────────────────────────────────────────
    (function () {
      function ch(n, pa, obp, slg, pos) {
        return { name: n, fgId: n, type: 'H', positions: [pos || 'c'], salary: 5,
                 proj: { pa: pa, ab: pa * 0.9, obp: obp, slg: slg, hr: 20, r: 65 } };
      }
      var A = [ch('a1',550,0.400,0.550), ch('a2',540,0.395,0.545), ch('a3',530,0.390,0.540),
               ch('a4',500,0.300,0.360,'of')];
      var B = [ch('b1',550,0.400,0.550,'of'), ch('b2',540,0.395,0.545,'of'),
               ch('b3',530,0.390,0.540,'of'), ch('b4',500,0.300,0.360)];
      var vm = {}, dm = {};
      A.concat(B).forEach(function (p) { vm[p.fgId] = { projectedValue: 25 };
                                         dm[p.fgId] = { holdHorizon: 2, dynastySurplus: 5 }; });
      var ctx = tfBuildContext({ A: A, B: B }, vm, dm, tfDen, 400);
      var cands = tfGenerateCandidates(ctx, 'A', 'B', 'contender', 'fringe');
      assert(cands.length > 0, 'tfGenerateCandidates: produces candidates');
      assert(cands.every(function (c) { return c.archetype && c.reason && c.myPlayers && c.theirPlayers; }),
        'tfGenerateCandidates: every candidate is fully formed');
      var keys = cands.map(function (c) {
        return c.myPlayers.map(tfKey).sort().join('|') + '/' + c.theirPlayers.map(tfKey).sort().join('|'); });
      assertEqual(keys.length, new Set(keys).size, 'tfGenerateCandidates: no duplicate pairings');
    })();
```

- [ ] **Step 3:** Verify green. **Step 4:** Commit
`feat(trade): window + consolidation archetypes and dispatcher`.

---

### Task 5: Wire into `targets.html`

**Files:** Modify `targets.html`.

- [ ] **Step 1: Load the module.** Add `<script src="tradefinder.js"></script>` after the
`shared.js` tag.

- [ ] **Step 2: Build the context once**, after `valueMap` and the team map exist (near the
existing `calculateDynastyValues` / `calculateAllValues` call around line 250). The
denominators must come from the same optimized team stats the valuation used:

```js
    var tfCtx = null;
    try {
      var tfBudget  = tfIpBudget();
      var tfStatsArr = teamNames.map(function (t) { return tfTeamStats(teamMap[t], tfBudget); });
      tfCtx = tfBuildContext(teamMap, valueMap, valueMap, calcSGPDenoms(tfStatsArr), tfBudget);
    } catch (e) { console.warn('[targets] archetype context unavailable:', e); }
```

**Note:** `valueMap` here is whatever `calculateAllValues`/`calculateDynastyValues`
returned — it carries both `projectedValue` and (in dynasty mode) `holdHorizon` /
`dynastySurplus`, so it serves as both `valueMap` and `dynastyMap`. If the page is in
non-dynasty mode there is no `holdHorizon`, and `tfRentalCandidates` correctly yields
nothing.

- [ ] **Step 3: Add the generator mode.** Add a button/mode alongside the existing Offer
and Acquire modes labelled **"Find trades"**. Its handler:

```js
    function runFindMode(resultsEl) {
      if (!tfCtx) {
        var w = document.createElement('div'); w.className = 'no-trades-msg';
        w.textContent = 'Trade generator unavailable — marginal values could not be computed.';
        resultsEl.appendChild(w); return;
      }
      var myStatus = teamStatusOf(myTeamName);
      var found = 0;
      teamCards.forEach(function (tc) {
        var cands = tfGenerateCandidates(tfCtx, myTeamName, tc.name,
                                         myStatus, teamStatusOf(tc.name));
        if (!cands.length) return;
        var options = [];
        cands.forEach(function (c) {
          if (options.length >= 3) return;
          var res = evaluateCandidates(tc.name, [c.myPlayers], [c.theirPlayers]);
          res.forEach(function (o) {
            o.archetype = c.archetype;
            o.reason    = c.reason;
            options.push(o);
          });
        });
        if (!options.length) return;
        found++;
        resultsEl.appendChild(makeTradeCard(tc.name, tc.weakCats, options.slice(0, 3), null, false));
      });
      if (!found) {
        var m = document.createElement('div'); m.className = 'no-trades-msg';
        m.textContent = 'No archetype trades cleared both sides right now. That is a normal ' +
          'result — every proposal must pass the fairness filter, a full standings simulation, ' +
          'and both teams’ utility gates.';
        resultsEl.appendChild(m);
      }
    }
```

- [ ] **Step 4: Render the badge and reason.** In `makeTradeCard`, where each option is
rendered, add before the existing benefit lines:

```js
        if (o.archetype) {
          var badge = document.createElement('span');
          badge.className = 'badge badge-arch';
          badge.textContent = o.archetype;
          optEl.appendChild(badge);
        }
        if (o.reason) {
          var why = document.createElement('div');
          why.className = 'trade-reason';
          why.textContent = o.reason;      // textContent — never innerHTML with player data
          optEl.appendChild(why);
        }
```

(`optEl` is whatever element the existing code builds per option — match the surrounding
variable name rather than introducing a new one.)

Add CSS near the other badge rules:

```css
    .badge-arch { background: #ede7f6; color: #4527a0; text-transform: uppercase;
                  font-size: 0.68rem; letter-spacing: 0.04em; }
    .trade-reason { font-size: 0.84rem; color: #555; margin: 4px 0 6px; line-height: 1.45; }
```

- [ ] **Step 5: Verify in the browser.** Serve the repo, hard-refresh `targets.html`
(force `fetch('/tradefinder.js', {cache:'reload'})` first — stale JS has bitten twice).
Confirm: the mode runs without console errors, proposals show a badge and a readable
reason, and the reason text names real players.

**If `proj_pitching.csv` fails to load in the in-app browser**, that is the ~400KB
fetch-proxy cap, not a page bug — verify in a real browser or fall back to reading the
generated candidates via a Node harness.

- [ ] **Step 6:** Commit `feat(trade): archetype generator mode in targets.html`.

---

### Task 6: Live sanity check

**Files:** `<scratchpad>/verify_archetypes.js` (throwaway).

- [ ] Build the context from real data (same sandbox pattern as
`<scratchpad>/verify_marginal.js`, remembering `var __CATS = CATS;` for const extraction)
and print, for each of the 11 opponents: candidate count by archetype, plus the top
proposal's reason string.

Sanity checks — if any fails, STOP and report:
1. **Every archetype fires at least once** across the league. If one never fires, its gate
   is too tight (or the data genuinely lacks that situation — distinguish before tuning).
2. **Rentals name productive players**, not $1-3 fringe. The `TF_RENTAL_MIN_VALUE` gate
   exists precisely because ~60% of contracts sit at `holdHorizon === 0`.
3. **No proposal offers Juan Soto or Aaron Judge as a "blocked" logjam asset.** That was
   the bug the PA-budget fix removed; its reappearance means the lineup regressed.
4. **Reason strings read like something you would send another owner** — that is the whole
   point of the feature.
5. Total generation time under ~2s for all 11 opponents.

---

### Task 7: MODEL.md

- [ ] **§5:** replace the candidate-generation description — generation is now by
archetype (logjam/hole, rental, buy-now/sell-future, consolidation), each carrying a
reason; the fairness filter, `simulateTrade`, and the utility gate are unchanged
downstream.
- [ ] **§6 knobs:** add `TF_RENTAL_MIN_VALUE` (8).
- [ ] **§8:** note that `tfGain` is retained for within-map comparisons but that
`tfCrossGain` is required for cross-team questions — `tfGain` silently returns 0 for the
target side when the player is not in that map.
- [ ] Commit `docs(model): archetype trade generation`.

---

## Definition of done

- Suite green (~183 assertions; verify empirically).
- All four archetypes fire on real data; rentals name productive players.
- `targets.html` "Find trades" mode renders badges and reasons with no console errors.
- MODEL.md §5, §6, §8 updated.

## Out of scope

- Removing the old top-4 × top-5 card view. Leave it until the generator has been used
  in anger; deleting the fallback in the same pass removes the comparison.
- Multi-team trades. Ottoneu trades are two-sided.
- Re-tuning `TF_BLOCK_MIN` / `TF_NEED_MIN` / `TF_GAIN_MIN` — ship at $5 and adjust from
  observed output rather than in advance.
