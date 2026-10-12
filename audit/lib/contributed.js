// audit/lib/contributed.js
// v2 standings: how many final roto points a player's COUNTED stats were worth to
// the team (team points minus points with that line removed). No invented replacement.
const { scoreStandings } = require('./counterfactual');

function teamTotalsFromLines(lines) {
  return lines.reduce((t, c) => {
    if (!c || !c.line) return t;
    if (c.type === 'H') { t.pa += c.line.pa || 0; if (c.line.pitch) t.ip += c.line.pitch.ip || 0; } else t.ip += c.line.ip || 0;
    return t;
  }, { pa: 0, ip: 0 });
}

function removeLine(stats, ip, c, totals) {
  const s = { ...stats }; let tip = ip;
  const dropH = l => {
    const pa = l.pa || 0, rest = Math.max(1, totals.pa - pa);
    s.HR -= l.hr || 0; s.R -= l.r || 0;
    s.OBP = (stats.OBP * totals.pa - (l.obp || 0) * pa) / rest;
    s.SLG = (stats.SLG * totals.pa - (l.slg || 0) * pa) / rest;
  };
  const dropP = l => {
    const lip = l.ip || 0, restIP = Math.max(1, totals.ip - lip);
    for (const [k, f] of [['ERA', 'era'], ['WHIP', 'whip'], ['HR9', 'hr9']]) s[k] = (stats[k] * totals.ip - (l[f] || 0) * lip) / restIP;
    // Team IP is left as-is: a team that reached the 1,250-IP minimum would have
    // filled one pitcher's innings from its bench, so removal never trips that cliff.
    s.SO -= l.so || 0;
  };
  if (c.type === 'H') { dropH(c.line); if (c.line.pitch) dropP(c.line.pitch); } else if (c.type === 'P') dropP(c.line);
  return { stats: s, ip: tip };
}

function ptsContributed(engine, final, teamId, c, totals) {
  if (!c || !c.line) return 0;
  const pointsOf = teams => scoreStandings(engine, teams).find(t => t.teamId === teamId).points;
  const actual = pointsOf(final);
  const without = pointsOf(final.map(t => (t.teamId === teamId ? { teamId, ...removeLine(t.stats, t.ip, c, totals) } : t)));
  return actual - without;
}

// Did this move's net points decide a place? Uses real final points (half-point ties included).
function titleDeciding(finalWithPoints, teamId, net) {
  const s = [...finalWithPoints].sort((a, b) => b.points - a.points);
  const i = s.findIndex(t => t.teamId === teamId); if (i < 0 || !net) return null;
  const P = s[i].points;
  if (net > 0) {
    if (i === 0 && s[1] && net >= P - s[1].points) return 'won-title';
    if (i > 0 && i <= 2 && s[3] && net >= P - s[3].points) return 'made-podium';
  } else {
    if (i === 1 && -net >= s[0].points - P) return 'cost-title';
    if (i >= 3 && s[2] && -net >= s[2].points - P) return 'cost-podium';
  }
  return null;
}

// Roto points move in whole ranks, so a tiny line can be worth several points when it nudges a
// team past a close neighbour. A title-deciding verdict is a close call if it flips when any one
// contributor other than the main one is dropped, or if it clears the margin by under a point.
function isCloseCall(finalWithPoints, teamId, components) {
  const net = components.reduce((s, v) => s + v, 0);
  const verdict = titleDeciding(finalWithPoints, teamId, net);
  if (!verdict) return false;
  if (titleDeciding(finalWithPoints, teamId, net - Math.sign(net)) !== verdict) return true;
  const byWeight = components.map((v, i) => [v, i]).sort((a, b) => Math.abs(b[0]) - Math.abs(a[0]));
  return byWeight.slice(1).some(([v]) => v !== 0 && titleDeciding(finalWithPoints, teamId, net - v) !== verdict);
}

module.exports = { ptsContributed, titleDeciding, teamTotalsFromLines, isCloseCall };
