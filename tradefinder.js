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
  return abs - (ownerMarginals[key] || 0);
}

// How much MORE a player is worth to team B than to his current team A.
// This is the quantity that makes a trade mutually attractive.
function tfGain(player, marginalsA, marginalsB) {
  var key = tfKey(player);
  return (marginalsB[key] || 0) - (marginalsA[key] || 0);
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
