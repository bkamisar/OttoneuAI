/* hotboard.js — pure logic for the Hot FA Board.
 * Depends on normalizeName() from shared.js (load shared.js first).
 * All thresholds here are the tunable knobs from the design spec:
 *   docs/superpowers/specs/2026-07-19-hot-fa-board-design.md
 */

// ── Sample gates: minimum workload to appear in the default (non-marginal) view.
var HOT_MIN_PA = { 7: 12, 15: 25, 30: 45 };   // hitters, by window
var HOT_MIN_GS = { 7: 1,  15: 2,  30: 3  };   // starters: starts
var HOT_MIN_G  = { 7: 3,  15: 5,  30: 8  };   // relievers: appearances

// role = SP if starts are at least half of appearances (and he started at least once).
function hotClassifyRole(g, gs) {
  g = g || 0; gs = gs || 0;
  return (gs > 0 && gs * 2 >= g) ? 'SP' : 'RP';
}

// kind: 'H' (hitter), 'SP', or 'RP'. win: 7|15|30. line: a per-window stat object.
// (param is `win`, not `window`, to avoid shadowing the browser global.)
function hotMeetsThreshold(kind, win, line) {
  if (!line) return false;
  if (kind === 'H')  return (line.pa || 0) >= (HOT_MIN_PA[win] || 0);
  if (kind === 'SP') return (line.gs || 0) >= (HOT_MIN_GS[win] || 0);
  if (kind === 'RP') return (line.g  || 0) >= (HOT_MIN_G[win]  || 0);
  return false;
}

// ── HotScore: equal-weight z-score across the four scoring cats, normalized
//    within a pool (hitters / SP / RP each get their own pool).
// Which categories drive HotScore, and direction (+1 higher-better, -1 lower-better).
var HOT_CATS = {
  H: [{ k: 'obp', d: 1 }, { k: 'slg', d: 1 }, { k: 'hr', d: 1 }, { k: 'r', d: 1 }],
  P: [{ k: 'so', d: 1 }, { k: 'hr9', d: -1 }, { k: 'era', d: -1 }, { k: 'whip', d: -1 }]
};

// mean + stdev per category across a pool of stat lines. std guarded to never be 0.
function hotPoolStats(lines, keys) {
  var stats = {};
  keys.forEach(function (c) {
    var vals = lines.map(function (l) { return +l[c] || 0; });
    var n = vals.length || 1;
    var mean = vals.reduce(function (a, b) { return a + b; }, 0) / n;
    var variance = vals.reduce(function (a, b) { return a + (b - mean) * (b - mean); }, 0) / n;
    stats[c] = { mean: mean, std: Math.sqrt(variance) || 1 };
  });
  return stats;
}

// kind: 'H' for hitters, 'P' for pitchers (SP and RP each get their OWN pool passed in).
function hotScoreFor(line, poolStats, kind) {
  var cats = HOT_CATS[kind === 'H' ? 'H' : 'P'];
  var score = 0;
  cats.forEach(function (c) {
    var s = poolStats[c.k];
    if (!s) return;
    score += c.d * (((+line[c.k] || 0) - s.mean) / s.std);
  });
  return score;
}

// ── Breakout badge: recent rate clearly beats the Steamer projection.
var HOT_BREAKOUT_OPS  = 0.075;  // hitter recent OPS over projected OPS
var HOT_BREAKOUT_KPCT = 0.03;   // pitcher recent K% over projected K% (+3 pts)

// kind: 'H' or 'P'. recent = per-window line; proj = projection line (may be null).
function hotBreakoutBadge(kind, recent, proj) {
  if (!recent || !proj) return false;
  if (kind === 'H') {
    var recOps  = (+recent.obp || 0) + (+recent.slg || 0);
    var projOps = (+proj.obp  || 0) + (+proj.slg  || 0);
    return (recOps - projOps) >= HOT_BREAKOUT_OPS;
  }
  var eraWhipBetter = (+recent.era || 99) < (+proj.era || 0) &&
                      (+recent.whip || 99) < (+proj.whip || 0);
  var recKpct  = recent.bf ? (+recent.so || 0) / recent.bf : 0;
  var projKpct = (proj.kpct != null) ? +proj.kpct : 0;   // 0 if projection has no K%
  var kBetter  = projKpct > 0 && recKpct >= projKpct + HOT_BREAKOUT_KPCT;
  return eraWhipBetter || kBetter;
}

// ── Free-agent matching against the parsed league roster.
// Build a lookup of rostered players: normalized name -> true.
function hotRosteredSet(rosterRows) {
  var set = {};
  (rosterRows || []).forEach(function (p) {
    if (p && p.name) set[normalizeName(p.name)] = true;
  });
  return set;
}

// A StatsAPI player is a free agent if his normalized name is not in the rostered set.
function hotIsFreeAgent(name, rosteredSet) {
  return !rosteredSet[normalizeName(name || '')];
}
