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
  // Clamp the realized side at 0. A hitter with empty PA drags team OBP/SLG, so
  // his marginal goes NEGATIVE — and `abs − negative` inflates rather than
  // measuring anything ("stranded $93" for a $25 player contributing −$68).
  // Blocked means "would help if he played"; a harmful player is a different
  // problem and callers must not treat him as a trade asset. Clamped here rather
  // than at each call site so every archetype inherits the correct semantics.
  return abs - Math.max(0, ownerMarginals[key] || 0);
}

// How much MORE a player is worth to team B than to his current team A.
// This is the quantity that makes a trade mutually attractive.
function tfGain(player, marginalsA, marginalsB) {
  var key = tfKey(player);
  return (marginalsB[key] || 0) - (marginalsA[key] || 0);
}

// What a player would ADD to a roster he is not currently on: re-optimize that
// roster with him inserted and score the delta. This is the primitive every
// archetype needs — tfGain() only compares within already-computed maps and
// CANNOT answer it (a player absent from marginalsB reads as 0 there).
function tfMarginalOn(player, roster, denoms, ipBudget) {
  var budget = ipBudget || tfIpBudget();
  var base    = tfTeamStats(roster, budget);
  var withHim = roster.concat([player]);
  return tfMarginalZ(tfTeamStats(withHim, budget), base, denoms) * TF_PTS_DOLLARS;
}

// How much MORE a player is worth on targetRoster than to his current owner.
// Positive = the trade motivation exists.
function tfCrossGain(player, ownerMarginals, targetRoster, denoms, ipBudget) {
  return tfMarginalOn(player, targetRoster, denoms, ipBudget)
       - ((ownerMarginals || {})[tfKey(player)] || 0);
}

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
  // Only PRIMARY slots are league-wide. Derived supplementation keys (C_2,
  // OF1_3) exist solely on injury-thinned rosters, so medianing them across
  // teams would show every healthy team a phantom `median − 0` need at a slot
  // it does not even have.
  var primaryIds = {};
  HITTER_SLOTS.forEach(function (s) { primaryIds[s.id] = 1; });
  var slotIds = {};
  teams.forEach(function (t) {
    Object.keys(occ[t]).forEach(function (s) { if (primaryIds[s]) slotIds[s] = 1; });
  });

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

// ── ARCHETYPE GENERATION ────────────────────────────────────────────────────
// Candidates are generated BY REASON, not by slicing a value-sorted list. The
// old approach took the top 4 of my roster and top 5 of theirs by absolute
// value — 20 of ~1,764 possible 1-for-1s, all from the priciest slice — so
// star-for-star was the only reachable outcome.

// Everything the matchers need, computed ONCE per page load.
// rostersByTeam: { team: [players] }; valueMap: Y0 values (projectedValue);
// dynastyMap: from calculateDynastyValues (carries holdHorizon/dynastySurplus).
function tfBuildContext(rostersByTeam, valueMap, dynastyMap, denoms, ipBudget) {
  var budget = ipBudget || tfIpBudget();
  var marginals = tfAllMarginals(rostersByTeam, denoms, budget);
  return {
    rostersByTeam: rostersByTeam,
    valueMap:  valueMap  || {},
    dynastyMap: dynastyMap || {},
    denoms: denoms,
    ipBudget: budget,
    marginals: marginals,
    needGaps: tfNeedGaps(rostersByTeam, marginals),
  };
}

function tfDollars(n) { return '$' + Math.round(n); }
function tfName(p) { return p.rawName || p.name; }

// ARCHETYPE 1 — Logjam <-> Hole.
// I have a bat stranded behind better ones; they would start him. Reciprocally
// for one of theirs. This is exactly what the old slicing could never reach: a
// blocked player is by definition NOT near the top of a value-sorted list.
function tfLogjamCandidates(ctx, myTeam, theirTeam) {
  var out = [];
  var myMarg = ctx.marginals[myTeam] || {}, thMarg = ctx.marginals[theirTeam] || {};
  var myRoster = ctx.rostersByTeam[myTeam] || [], thRoster = ctx.rostersByTeam[theirTeam] || [];

  function surplusAssets(roster, ownMarg, otherRoster) {
    return roster.filter(function (p) { return p.type === 'H' && p.proj; })
      .map(function (p) {
        var own = ownMarg[tfKey(p)] || 0;
        var addTo = tfMarginalOn(p, otherRoster, ctx.denoms, ctx.ipBudget);
        return { p: p, own: own, addTo: addTo,
                 blocked: tfBlockedness(p, ownMarg, ctx.valueMap),
                 gain: addTo - own };
      })
      .filter(function (x) {
        // BLOCKED means sitting on the bench contributing nothing, NOT actively
        // harmful. A hitter with empty PA drags team OBP/SLG, so his marginal is
        // negative — and since blockedness = value − marginal, a negative marginal
        // INFLATES it (a -$68 marginal reads as $93 "stranded"). Requiring own >= 0
        // keeps those out. Requiring addTo > 0 is the stronger gate: "worth more to
        // them" is meaningless if he is still a negative there, which is how two
        // mirror-image rosters used to generate a pointless symmetric swap.
        return x.own >= 0 && x.addTo > 0 &&
               x.blocked >= TF_BLOCK_MIN && x.gain >= TF_GAIN_MIN;
      })
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
        reason: tfName(a.p) + ' is stranded on your bench (' + tfDollars(a.blocked) +
                ' of value you cannot field) and worth ' + tfDollars(a.gain) +
                ' more to them; ' + tfName(b.p) + ' is the mirror image — ' +
                tfDollars(b.gain) + ' more useful to you.',
      });
    });
  });
  return out;
}

// ARCHETYPE 2 — Rental / salary dump.
// Their productive player on a bad contract (holdHorizon 0) is one they were
// going to lose in October for nothing. Trading him beats cutting him: an
// in-season cut costs half his salary in dead money, while a trade costs
// nothing and returns an asset. I take the full salary for the stretch run and
// cut free at season's end, so my future liability is genuinely zero.
// GATE: holdHorizon === 0 alone is NOT enough. Roughly 60% of contracts resolve
// there and about half of those are $1-3 fringe (MODEL.md §4) — "cut candidate"
// is not the same as "rental target". Require real Y0 production.
var TF_RENTAL_MIN_VALUE = 8;   // $ of Y0 value before a rental is worth pursuing

function tfRentalCandidates(ctx, myTeam, theirTeam, myStatus, theirStatus) {
  if (myStatus === 'rebuilder') return [];       // rentals are for teams trying to win now
  if (theirStatus === 'contender') return [];    // contenders do not sell their production
  var out = [];
  var myMarg   = ctx.marginals[myTeam] || {};
  var myRoster = ctx.rostersByTeam[myTeam] || [];
  var thRoster = ctx.rostersByTeam[theirTeam] || [];

  var rentals = thRoster.filter(function (q) {
    if (!q.proj) return false;
    var d = ctx.dynastyMap[tfKey(q)];
    if (!d || d.holdHorizon !== 0) return false;
    var v = (ctx.valueMap[tfKey(q)] || {}).projectedValue || 0;
    if (v < TF_RENTAL_MIN_VALUE) return false;                       // skip fringe H0
    return tfMarginalOn(q, myRoster, ctx.denoms, ctx.ipBudget) > 0;  // must actually help me
  }).sort(function (a, b) {
    return ((ctx.valueMap[tfKey(b)] || {}).projectedValue || 0)
         - ((ctx.valueMap[tfKey(a)] || {}).projectedValue || 0);
  }).slice(0, 3);

  // What I send: a future asset I am not fielding now — low current marginal
  // value, positive dynasty surplus.
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
        reason: tfName(q) + ' is a rental for you — you cut him free in October, so his ' +
                tfDollars(sal) + ' salary is a stretch-run cost only. They were losing him ' +
                'for nothing: cutting him in-season costs them ' + tfDollars(sal / 2) +
                ' in dead money, while trading him costs nothing and returns ' +
                tfName(p) + ', who you are not using now.',
      });
    });
  });
  return out;
}

// ARCHETYPE 3 — Buy-now <-> sell-future.
// The old rel='buy'/'sell' idea, but fed MARGINAL value: I send future surplus I
// cannot field this year, they send current production they cannot cash in while
// rebuilding. Requires a genuine status mismatch — two contenders have no window
// asymmetry to trade on.
function tfWindowCandidates(ctx, myTeam, theirTeam, myStatus, theirStatus) {
  if (myStatus === theirStatus) return [];
  var buying  = myStatus !== 'rebuilder' && theirStatus === 'rebuilder';
  var selling = myStatus === 'rebuilder' && theirStatus !== 'rebuilder';
  if (!buying && !selling) return [];

  var out = [];
  var myMarg = ctx.marginals[myTeam] || {}, thMarg = ctx.marginals[theirTeam] || {};
  var myRoster = ctx.rostersByTeam[myTeam] || [], thRoster = ctx.rostersByTeam[theirTeam] || [];

  // Future surplus not being fielded now.
  function futureAssets(roster, marg) {
    return roster.filter(function (p) {
      var d = ctx.dynastyMap[tfKey(p)];
      return p.proj && d && (d.dynastySurplus || 0) > 0 && (marg[tfKey(p)] || 0) < TF_GAIN_MIN;
    }).sort(function (a, b) {
      return ((ctx.dynastyMap[tfKey(b)] || {}).dynastySurplus || 0)
           - ((ctx.dynastyMap[tfKey(a)] || {}).dynastySurplus || 0);
    }).slice(0, 3);
  }
  // Production that would materially help the receiving roster.
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
        myPlayers:    buying ? [f] : [n.p],
        theirPlayers: buying ? [n.p] : [f],
        reason: buying
          ? 'They are rebuilding and cannot cash in ' + tfName(n.p) + ', who is worth ' +
            tfDollars(n.add) + ' to your lineup right now; you send future surplus in ' +
            tfName(f) + ', who is not in your lineup this year.'
          : 'You are rebuilding, so ' + tfName(n.p) + ' is production you cannot use — ' +
            tfDollars(n.add) + ' to their lineup — and they pay in ' + tfName(f) +
            ', future value you can hold.',
      });
    });
  });
  return out;
}

// ARCHETYPE 4 — Consolidation.
// Two of my usable-but-not-elite pieces for one clearly better player, when I am
// deep enough to spare the roster spot. targets.html's existing CONSOL_PREM
// (15% per extra player on the bulkier side) prices it; this only proposes it.
function tfConsolidationCandidates(ctx, myTeam, theirTeam) {
  var out = [];
  var myMarg = ctx.marginals[myTeam] || {};
  var myRoster = ctx.rostersByTeam[myTeam] || [], thRoster = ctx.rostersByTeam[theirTeam] || [];

  var spares = myRoster.filter(function (p) {
      // >= 0, not > 0: consolidation is precisely how you cash in DEPTH, and a
      // benched player sits at exactly 0. Excluding him would leave only
      // marginal starters, which is the opposite of the archetype. The >= 0 half
      // still keeps out actively harmful players.
      return p.proj && (myMarg[tfKey(p)] || 0) >= 0 &&
             tfBlockedness(p, myMarg, ctx.valueMap) >= TF_BLOCK_MIN;
    }).sort(function (a, b) {
      return tfBlockedness(b, myMarg, ctx.valueMap) - tfBlockedness(a, myMarg, ctx.valueMap);
    }).slice(0, 4);

  var targets = thRoster.filter(function (p) { return p.proj; })
    .map(function (p) { return { p: p, add: tfMarginalOn(p, myRoster, ctx.denoms, ctx.ipBudget) }; })
    .filter(function (x) { return x.add >= TF_GAIN_MIN * 2; })   // must be clearly better
    .sort(function (a, b) { return b.add - a.add; })
    .slice(0, 2);

  targets.forEach(function (t) {
    for (var i = 0; i < spares.length; i++) {
      for (var j = i + 1; j < spares.length; j++) {
        out.push({
          archetype: 'consolidation',
          myPlayers: [spares[i], spares[j]], theirPlayers: [t.p],
          reason: 'You are deep enough to spare ' + tfName(spares[i]) + ' and ' +
                  tfName(spares[j]) + '; ' + tfName(t.p) + ' would add ' +
                  tfDollars(t.add) + ' to your lineup and frees a roster spot.',
        });
      }
    }
  });
  return out;
}

// Dispatcher — every archetype for one opponent, de-duplicated by player pairing.
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
