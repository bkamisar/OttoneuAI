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
